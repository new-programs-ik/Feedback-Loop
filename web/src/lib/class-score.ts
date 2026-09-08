import {
  componentRows,
  explainClass,
  scoreClass,
  type Action,
  type Band,
  type ComponentRow,
  type ScoreInputs,
  type ScoreResult,
  type ScoringConfig,
} from "@/lib/sentiment";
import type { ClassRating } from "@/lib/ratings";

/** Pure bridge between a `class_ratings` row and the score. The database scores every row
 *  (migration 0015); until those columns are populated the web mirror computes the same thing
 *  from the row's inputs with the active configuration, so every page shows a score either way. */

export type Priors = { rating: number | null; approval: number | null };

export type Scored = {
  score: number | null;
  band: Band | null;
  action: Action;
  provisional: boolean;
  flags: string[];
  /** true when the numbers came from the database, false when the mirror computed them. */
  stored: boolean;
  inputs: ScoreInputs;
  result: ScoreResult;
  reason: string;
  rows: ComponentRow[];
};

export function rowInputs(r: ClassRating, priors?: Priors | null): ScoreInputs {
  return {
    rating: r.rating,
    num_ratings: r.num_ratings,
    attended: r.attended,
    yes_votes: r.yes_votes,
    no_votes: r.no_votes,
    escalated: r.escalated,
    track_avg: r.track_avg,
    prior_rating: priors?.rating ?? null,
    prior_approval: priors?.approval ?? null,
  };
}

const hasStoredScore = (r: ClassRating) => r.sentiment_score != null || r.sentiment_band != null || r.scored_at != null;

export function scoreRow(r: ClassRating, cfg: ScoringConfig, priors?: Priors | null): Scored {
  const inputs = rowInputs(r, priors);
  const computed = scoreClass(inputs, cfg);
  if (hasStoredScore(r)) {
    // The database's verdict wins; the mirror only fills in the breakdown for the popover.
    const result: ScoreResult = {
      ...computed,
      score: r.sentiment_score,
      band: r.sentiment_band,
      action: r.sentiment_action ?? computed.action,
      provisional: r.sentiment_provisional ?? computed.provisional,
      flags: (r.sentiment_flags.length ? r.sentiment_flags : computed.flags) as ScoreResult["flags"],
    };
    return {
      score: result.score,
      band: result.band,
      action: result.action,
      provisional: result.provisional,
      flags: result.flags,
      stored: true,
      inputs,
      result,
      reason: explainClass(inputs, result, cfg),
      rows: componentRows(inputs, result, cfg),
    };
  }
  return {
    score: computed.score,
    band: computed.band,
    action: computed.action,
    provisional: computed.provisional,
    flags: computed.flags,
    stored: false,
    inputs,
    result: computed,
    reason: explainClass(inputs, computed, cfg),
    rows: componentRows(inputs, computed, cfg),
  };
}

/** The course's typical rating and pooled approval — the small-sample guard's prior — from
 *  whatever rows are in hand, keyed like `byCourse` (course id, else the sheet label). */
export function coursePriors(rows: ClassRating[]): Map<string, Priors> {
  const acc = new Map<string, { ratings: number[]; yes: number; votes: number }>();
  for (const r of rows) {
    const key = r.course_id ?? `label:${r.course_label}`;
    const a = acc.get(key) ?? { ratings: [], yes: 0, votes: 0 };
    a.ratings.push(r.rating);
    if (r.yes_votes != null && r.no_votes != null) {
      a.yes += r.yes_votes;
      a.votes += r.yes_votes + r.no_votes;
    }
    acc.set(key, a);
  }
  const out = new Map<string, Priors>();
  for (const [key, a] of acc) {
    out.set(key, {
      rating: a.ratings.length ? a.ratings.reduce((x, y) => x + y, 0) / a.ratings.length : null,
      approval: a.votes > 0 ? (a.yes / a.votes) * 100 : null,
    });
  }
  return out;
}

export const courseKey = (r: Pick<ClassRating, "course_id" | "course_label">) => r.course_id ?? `label:${r.course_label}`;

const ACTION_RANK: Record<Action, number> = { video: 0, transcript: 1, watch: 2, none: 3 };

/** Video first, then the lowest score, then the lowest rating. */
export function byUrgency(a: { row: ClassRating; scored: Scored }, b: { row: ClassRating; scored: Scored }) {
  return (
    ACTION_RANK[a.scored.action] - ACTION_RANK[b.scored.action] ||
    (a.scored.score ?? Infinity) - (b.scored.score ?? Infinity) ||
    a.row.rating - b.row.rating
  );
}

/** What an analysis costs the team: the rates from the costing study and the minutes a PM spends. */
export const ANALYSIS_COST = { video: 0.7, transcript: 0.51 } as const;
export const ANALYSIS_MINUTES = { video: 7, transcript: 3.5 } as const;

export function queueCost(videos: number, transcripts: number) {
  const usd = videos * ANALYSIS_COST.video + transcripts * ANALYSIS_COST.transcript;
  const minutes = videos * ANALYSIS_MINUTES.video + transcripts * ANALYSIS_MINUTES.transcript;
  const hours = minutes / 60;
  const time = minutes < 60 ? `~${Math.round(minutes)} min` : `~${hours.toFixed(hours >= 10 ? 0 : 1).replace(/\.0$/, "")} h`;
  return { usd, minutes, label: `${videos} ${videos === 1 ? "video" : "videos"} · ${transcripts} ${transcripts === 1 ? "transcript" : "transcripts"} ≈ $${usd.toFixed(2)} · ${time}` };
}
