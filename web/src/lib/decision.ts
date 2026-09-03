/** The team's which-analysis rule — THE single web-side source of truth.
 *
 *  MIRROR: ratings_module_build_kit/decision.py is the same rule for the sync worker.
 *  Edit both together; tests on both sides pin the boundary values.
 *
 *  Rule v1 (validated on 8 months of ratings data, Sep 2026 — see the Rating-Threshold study):
 *  escalation → video, always · rating ≥ 4.55 → none · < 5 ratings → watch ·
 *  ≥ 40% of attendees rated → video · under 40% → transcript.
 *
 *  Rule v2 (Sep 2026 — the Instructor-Approval study; analysis/approval_rule.py is the spec):
 *  two bars decide IF a class enters the queue — rated below 4.55, or fewer than 80% of the
 *  room would have the instructor back (either one, with at least 5 voices) — and the weighted
 *  Class Health Score (rating 60 / approval 30 / track record 10, each 100 at its bar and 0 at
 *  its floor) decides HOW URGENT and HOW DEEP: urgent (< 70) → video whatever the reach ·
 *  borderline (≥ 90) → transcript first · in between, the 40% reach bar decides as in v1.
 *  A missing vote or a missing track record scores 100 — a missing signal is never a penalty.
 */

export const GOOD = 4.55;
export const MIN_VOICES = 5;
export const PARTICIPATION_BAR = 40;

export const LINE = GOOD;
export const APPROVAL_BAR = 80;
export const REACH_BAR = PARTICIPATION_BAR;
export const R_FLOOR = 3.55;
export const A_FLOOR = 40;
export const T_FLOOR = 4.05;
export const T_MIN_CLASSES = 3;
export const WEIGHTS = { rating: 0.6, approval: 0.25, track: 0.15 } as const;
export const URGENT = 70;
export const BORDERLINE = 90;

export type Decision = "none" | "watch" | "transcript" | "video";
export type HealthBand = "urgent" | "look" | "borderline";
export type FlagReason = "rating" | "approval" | "escalated";

export const BAND_LABEL: Record<HealthBand, string> = {
  urgent: "Urgent",
  look: "Needs a look",
  borderline: "Borderline",
};

export function decide(
  rating: number | null | undefined,
  numRatings: number | null | undefined,
  attended: number | null | undefined,
  escalated = false,
): Decision {
  if (escalated) return "video";
  if (rating == null || Number.isNaN(rating)) return "watch";
  if (rating >= GOOD) return "none";
  if (numRatings == null || Number.isNaN(numRatings) || numRatings < MIN_VOICES) return "watch";
  if (!attended) return "watch";
  return (numRatings / attended) * 100 >= PARTICIPATION_BAR ? "video" : "transcript";
}

export function participationPct(
  numRatings: number | null | undefined,
  attended: number | null | undefined,
): number | null {
  if (numRatings == null || !attended) return null;
  return Math.round((numRatings / attended) * 100);
}

/** One-line human explanation per verdict (the queue chips and the form helper share these). */
export function explain(d: Decision, pct: number | null, numRatings: number | null): string {
  switch (d) {
    case "none":
      return `Rating is ${GOOD} or above — no analysis needed unless a PM asks.`;
    case "watch":
      return numRatings != null && numRatings < MIN_VOICES
        ? `Only ${numRatings} learner${numRatings === 1 ? "" : "s"} rated it — one or two opinions, not a class problem yet. Watch the next session.`
        : "Not enough data to judge yet — watch.";
    case "video":
      return `Below ${GOOD} and ${pct}% of attendees rated it (≥ ${PARTICIPATION_BAR}%) — a representative share of the room spoke and it was still low.`;
    case "transcript":
      return `Below ${GOOD} but only ${pct}% of attendees rated it (< ${PARTICIPATION_BAR}%) — too thin to trust yet; a transcript read is enough.`;
  }
}

// ── rule v2 ──────────────────────────────────────────────────────────────────
const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));

/** 0 at R_FLOOR, 100 at the line. */
export const scoreRating = (rating: number) => clamp((100 * (rating - R_FLOOR)) / (LINE - R_FLOOR));

/** 0 at A_FLOOR, 100 at the bar. No vote → 100 (no penalty). */
export const scoreApproval = (approval: number | null | undefined) =>
  approval == null ? 100 : clamp((100 * (approval - A_FLOOR)) / (APPROVAL_BAR - A_FLOOR));

/** 0 at T_FLOOR, 100 at the line. No track record → 100 (no penalty). */
export const scoreTrack = (trackAvg: number | null | undefined) =>
  trackAvg == null ? 100 : clamp((100 * (trackAvg - T_FLOOR)) / (LINE - T_FLOOR));

/** The Class Health Score, 0–100, unrounded. The band reads THIS value; the verdict and the DB
 *  carry it rounded to one decimal — so a stored 90.0 can sit in "look" (it was 89.99). */
export function healthScore(
  rating: number,
  approval: number | null | undefined,
  trackAvg: number | null | undefined,
): number {
  return (
    WEIGHTS.rating * scoreRating(rating) +
    WEIGHTS.approval * scoreApproval(approval) +
    WEIGHTS.track * scoreTrack(trackAvg)
  );
}

export function healthBand(score: number): HealthBand {
  return score < URGENT ? "urgent" : score < BORDERLINE ? "look" : "borderline";
}

/** yes/(yes+no) as a percent; null when either count is unknown or nobody voted. */
export function approvalPct(
  yesVotes: number | null | undefined,
  noVotes: number | null | undefined,
): number | null {
  if (yesVotes == null || noVotes == null || Number.isNaN(yesVotes) || Number.isNaN(noVotes)) return null;
  const votes = yesVotes + noVotes;
  return votes > 0 ? Math.round((yesVotes / votes) * 10000) / 100 : null;
}

/** "13 of 15 · 87%" — the vote as the queue prints it; null when nobody voted. */
export function voteLabel(
  yesVotes: number | null | undefined,
  noVotes: number | null | undefined,
): string | null {
  const pct = approvalPct(yesVotes, noVotes);
  if (pct == null) return null;
  return `${yesVotes} of ${yesVotes! + noVotes!} · ${Math.round(pct)}%`;
}

export type DecideV2Input = {
  rating: number | null | undefined;
  numRatings: number | null | undefined;
  attended: number | null | undefined;
  yesVotes?: number | null;
  noVotes?: number | null;
  trackAvg?: number | null;
  escalated?: boolean;
};

export type DecisionV2 = {
  decision: Decision;
  healthScore: number | null;
  healthBand: HealthBand | null;
  flagReasons: FlagReason[];
};

const num = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? null : v);

export function decideV2(i: DecideV2Input): DecisionV2 {
  const rating = num(i.rating);
  const escalated = i.escalated ?? false;
  if (rating == null) {
    return {
      decision: escalated ? "video" : "watch",
      healthScore: null,
      healthBand: null,
      flagReasons: escalated ? ["escalated"] : [],
    };
  }
  const approval = approvalPct(i.yesVotes, i.noVotes);
  const flagReasons: FlagReason[] = [];
  if (rating < GOOD) flagReasons.push("rating");
  if (approval != null && approval < APPROVAL_BAR) flagReasons.push("approval");
  if (escalated) flagReasons.push("escalated");
  const raw = healthScore(rating, approval, i.trackAvg);
  const band = healthBand(raw);
  const out = (decision: Decision, healthBand: HealthBand | null): DecisionV2 => ({
    decision,
    healthScore: Math.round(raw * 10) / 10,
    healthBand,
    flagReasons,
  });
  if (escalated) return out("video", band);
  if (flagReasons.length === 0) return out("none", null);
  const voices = num(i.numRatings);
  if (voices == null || voices < MIN_VOICES) return out("watch", null);
  if (band === "urgent") return out("video", band);
  if (band === "borderline") return out("transcript", band);
  if (!i.attended) return out("watch", null);
  return out((voices / i.attended) * 100 >= PARTICIPATION_BAR ? "video" : "transcript", band);
}

/** One plain-English sentence for a v2 verdict, e.g.
 *  "Rated 4.31 and only 67% would have the instructor back — urgent, video." */
export function explainV2(v: DecisionV2, i: DecideV2Input): string {
  const rating = num(i.rating);
  if (i.escalated) return "Escalation reported — video, whatever the numbers say.";
  if (rating == null) return "No rating yet — watch.";
  const approval = approvalPct(i.yesVotes, i.noVotes);
  const back = approval == null ? null : `${Math.round(approval)}% would have the instructor back`;
  const r = rating.toFixed(2);
  const voices = num(i.numRatings);
  const reach = participationPct(voices, i.attended);
  const lowRating = v.flagReasons.includes("rating");
  const lowApproval = v.flagReasons.includes("approval");

  if (v.decision === "none") {
    return back
      ? `Rated ${r} and ${back} — clears both bars, no analysis unless a PM asks.`
      : `Rated ${r} with no vote recorded — above the line, no analysis unless a PM asks.`;
  }
  if (v.decision === "watch") {
    if (voices != null && voices < MIN_VOICES)
      return `Only ${voices} learner${voices === 1 ? "" : "s"} rated it — too thin for either signal; watch the next session.`;
    if (voices == null) return "Fill in how many learners rated it — fewer than 5 is too thin for either signal.";
    return "Attendance is missing, so the reach can't be judged — watch.";
  }
  const why =
    lowRating && lowApproval
      ? `Rated ${r} and only ${Math.round(approval!)}% would have the instructor back`
      : lowRating
        ? back
          ? `Rated ${r}, though ${back}`
          : `Rated ${r} with no vote recorded`
        : `Rated ${r} but only ${Math.round(approval!)}% would have the instructor back`;
  const how =
    v.healthBand === "urgent"
      ? "urgent, video"
      : v.healthBand === "borderline"
        ? "borderline, transcript first"
        : `needs a look, ${v.decision}${reach != null ? ` (${reach}% of the room rated it)` : ""}`;
  return `${why} — ${how}.`;
}
