/** The team's which-analysis rule — THE single web-side source of truth.
 *
 *  MIRROR: ratings_module_build_kit/decision.py is the same rule for the sync worker.
 *  Edit both together; tests on both sides pin the boundary values.
 *
 *  Rule (validated on 8 months of ratings data, Sep 2026 — see the Rating-Threshold study):
 *  escalation → video, always · rating ≥ 4.55 → none · < 5 ratings → watch ·
 *  ≥ 40% of attendees rated → video · under 40% → transcript.
 */

export const GOOD = 4.55;
export const MIN_VOICES = 5;
export const PARTICIPATION_BAR = 40;

export type Decision = "none" | "watch" | "transcript" | "video";

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
