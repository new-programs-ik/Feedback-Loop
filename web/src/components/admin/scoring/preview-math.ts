/** Pure preview arithmetic over a range of real classes: what a candidate config would do,
 *  compared with a baseline (the active version) and with what the queue does today. Shared by
 *  the live preview panel, the publish confirmation and the what-if page — no React here. */

import type { PreviewRow } from "@/lib/admin";
import type { ActionKind, Band, ScoringConfig } from "../scoring-config";
import { explainClass, scoreClass, type ScoreInputs, type ScoreResult } from "@/lib/sentiment";
import { COST_PER_ANALYSIS } from "./band-meta";

export type BandCounts = Record<Band | "no_data", number>;
export type ActionCounts = Record<ActionKind, number>;

export type ChangedRow = {
  row: PreviewRow;
  before: ScoreResult;
  after: ScoreResult;
  reason: string;
  direction: "up" | "down" | "action";
};

export type PreviewStats = {
  n: number;
  withBand: number;
  before: BandCounts;
  after: BandCounts;
  actionsBefore: ActionCounts;
  actionsAfter: ActionCounts;
  weeks: number;
  videosPerWeek: number;
  transcriptsPerWeek: number;
  analysesPerWeek: number;
  costPerWeek: number;
  videosPerWeekBefore: number;
  transcriptsPerWeekBefore: number;
  costPerWeekBefore: number;
  /** Analysed under today's queue rule, not under the candidate. */
  dropped: number;
  /** Not analysed today, would be under the candidate. */
  added: number;
  flips: number;
  flipShare: number | null;
  flips10: number;
  withBand10: number;
  flipShare10: number | null;
  changed: ChangedRow[];
  bandMoves: number;
  actionMoves: number;
};

const emptyBands = (): BandCounts => ({ excellent: 0, good: 0, average: 0, bad: 0, no_data: 0 });
const emptyActions = (): ActionCounts => ({ video: 0, transcript: 0, none: 0, watch: 0 });
const BAND_RANK: Record<Band, number> = { excellent: 0, good: 1, average: 2, bad: 3 };

export function inputsFor(row: PreviewRow, cfg: ScoringConfig, globalPrior: { rating: number | null; approval: number | null }): ScoreInputs {
  const useGlobal = cfg.guard.prior === "global";
  return {
    rating: row.rating,
    num_ratings: row.num_ratings,
    attended: row.attended,
    yes_votes: row.yes_votes,
    no_votes: row.no_votes,
    escalated: row.escalated,
    track_avg: row.track_avg,
    prior_rating: useGlobal ? globalPrior.rating : row.prior_rating,
    prior_approval: useGlobal ? globalPrior.approval : row.prior_approval,
  };
}

const analysed = (a: ActionKind | null | undefined) => a === "video" || a === "transcript";

export function computePreview(
  rows: PreviewRow[],
  config: ScoringConfig,
  baseline: ScoringConfig,
  globalPrior: { rating: number | null; approval: number | null },
  from: string,
  to: string,
): PreviewStats {
  const days = Math.max(1, Math.round((+new Date(to) - +new Date(from)) / 86400000) + 1);
  const weeks = Math.max(1, days / 7);
  const before = emptyBands();
  const after = emptyBands();
  const actionsBefore = emptyActions();
  const actionsAfter = emptyActions();
  let withBand = 0, flips = 0, flips10 = 0, withBand10 = 0, dropped = 0, added = 0, bandMoves = 0, actionMoves = 0;
  const changed: ChangedRow[] = [];

  for (const row of rows) {
    const inA = inputsFor(row, config, globalPrior);
    const inB = inputsFor(row, baseline, globalPrior);
    const resA = scoreClass(inA, config);
    const resB = scoreClass(inB, baseline);
    after[resA.band ?? "no_data"] += 1;
    before[resB.band ?? "no_data"] += 1;
    actionsAfter[resA.action] += 1;
    actionsBefore[resB.action] += 1;

    const today = row.current_action ?? resB.action;
    if (analysed(today) && !analysed(resA.action)) dropped += 1;
    if (!analysed(today) && analysed(resA.action)) added += 1;

    // "Flips on one vote" — the validation study's definition, shared with scoring_whatif_summary:
    // one "yes" becomes a "no", or one rater gives a point less (the average drops by 1/n); a flip
    // is either replay changing the band; the share is over EVERY class in the window.
    if (resA.band) withBand += 1;
    {
      const votes = (row.yes_votes ?? 0) + (row.no_votes ?? 0);
      const big = votes >= 10;
      if (big) withBand10 += 1;
      let flipped = false;
      if (row.yes_votes != null && row.no_votes != null && row.yes_votes >= 1) {
        const v = scoreClass({ ...inA, yes_votes: row.yes_votes - 1, no_votes: row.no_votes + 1 }, config);
        if (v.band !== resA.band) flipped = true;
      }
      const ratingNum = inA.rating == null || inA.rating === "" ? null : Number(inA.rating);
      const nRatings = row.num_ratings == null ? 0 : Number(row.num_ratings);
      if (!flipped && nRatings > 0 && ratingNum != null && Number.isFinite(ratingNum)) {
        const r = scoreClass({ ...inA, rating: Math.max(0, ratingNum - 1 / nRatings) }, config);
        if (r.band !== resA.band) flipped = true;
      }
      if (flipped) {
        flips += 1;
        if (big) flips10 += 1;
      }
    }

    const bandChanged = resA.band !== resB.band;
    const actionChanged = resA.action !== resB.action;
    if (bandChanged) bandMoves += 1;
    if (actionChanged) actionMoves += 1;
    if (bandChanged || actionChanged) {
      let direction: ChangedRow["direction"] = "action";
      if (bandChanged) {
        if (resA.band && resB.band) direction = BAND_RANK[resA.band] < BAND_RANK[resB.band] ? "up" : "down";
        else direction = resA.band ? "up" : "down";
      }
      changed.push({ row, before: resB, after: resA, reason: explainClass(inA, resA), direction });
    }
  }

  changed.sort((a, b) => (a.row.class_date < b.row.class_date ? 1 : a.row.class_date > b.row.class_date ? -1 : 0));
  const perWeek = (n: number) => n / weeks;
  return {
    n: rows.length,
    withBand,
    before,
    after,
    actionsBefore,
    actionsAfter,
    weeks,
    videosPerWeek: perWeek(actionsAfter.video),
    transcriptsPerWeek: perWeek(actionsAfter.transcript),
    analysesPerWeek: perWeek(actionsAfter.video + actionsAfter.transcript),
    costPerWeek: perWeek(actionsAfter.video * COST_PER_ANALYSIS.video + actionsAfter.transcript * COST_PER_ANALYSIS.transcript),
    videosPerWeekBefore: perWeek(actionsBefore.video),
    transcriptsPerWeekBefore: perWeek(actionsBefore.transcript),
    costPerWeekBefore: perWeek(actionsBefore.video * COST_PER_ANALYSIS.video + actionsBefore.transcript * COST_PER_ANALYSIS.transcript),
    dropped,
    added,
    flips,
    flipShare: rows.length ? flips / rows.length : null,
    flips10,
    withBand10,
    flipShare10: withBand10 ? flips10 / withBand10 : null,
    changed,
    bandMoves,
    actionMoves,
  };
}

export const fmt1 = (v: number) => (Math.round(v * 10) / 10).toFixed(1);
export const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
export const fmtMoney = (v: number) => `$${v.toFixed(2)}`;
