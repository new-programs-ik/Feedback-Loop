/** The words a programme manager sees for the codes the system stores.
 *
 *  Every enum and flag code the database or the AI engine produces is mapped here, once. Pages
 *  never print a raw code: `content_coverage_gap`, `draft_ready`, `analysis_started` and friends
 *  used to appear on screen exactly as stored. If a code is unknown, the fallback is a readable
 *  phrase, never the code itself. */

// ── the AI's findings ────────────────────────────────────────────────────────
/** Finding codes from the engine (FLAGS_LIVE ∪ FLAGS_ARS in engine.py) → what they mean. */
export const FINDING_LABEL: Record<string, string> = {
  pace: "Pace",
  clarity: "Clarity of explanation",
  structure: "Structure of the session",
  examples: "Examples and worked cases",
  correctness: "Correctness of the content",
  logistics: "Logistics and set-up",
  coverage: "Coverage of the planned material",
  coding_time: "Time given to hands-on coding",
  agenda_balance: "Balance across the agenda",
  concept_left: "A concept left unexplained",
  doubt_handling: "Handling of learner doubts",
  engagement: "Learner engagement",
  learner_gap: "A gap learners were left with",
  camera: "Camera",
  screen_share: "Screen sharing",
  slides_mismatch: "Slides not matching what was taught",
  problem_coverage: "Coverage of the assigned problems",
  time_balance: "Time balance across problems",
  solution_walkthrough: "Solution walkthrough",
  approach_reasoning: "Reasoning behind the approach",
  complexity_tradeoffs: "Complexity trade-offs",
  edge_cases: "Edge cases",
  common_mistakes: "Common mistakes",
  problem_deferred: "A problem deferred or skipped",
  content_coverage_gap: "Coverage of the planned material",
};

export function findingLabel(code: string | undefined | null): string {
  if (!code) return "Finding";
  return FINDING_LABEL[code] ?? code.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const SEVERITY_LABEL: Record<string, string> = {
  major: "Serious",
  moderate: "Worth fixing",
  minor: "Minor",
};
export const severityLabel = (s: string | undefined | null): string => SEVERITY_LABEL[s ?? ""] ?? "Noted";

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: "high confidence",
  medium: "fair confidence",
  low: "low confidence",
};
export const confidenceLabel = (c: string | undefined | null): string => CONFIDENCE_LABEL[c ?? ""] ?? "";

/** The re-teach call: yes / maybe / no, as a sentence. */
export const RECLASS_LABEL: Record<string, string> = {
  yes: "Re-teach recommended",
  maybe: "Consider re-teaching",
  no: "No re-teach needed",
};
export const reclassLabel = (r: string | undefined | null): string => RECLASS_LABEL[r ?? ""] ?? "Not decided";

// ── the class a PM analysed ──────────────────────────────────────────────────
/** classes.status → what is happening to the analysis. */
export const CLASS_STATUS_LABEL: Record<string, string> = {
  scheduled: "Starting",
  analyzing: "Being analysed",
  draft_ready: "Draft ready to review",
  approved: "Feedback approved",
  discarded: "Discarded",
  no_action: "No action needed",
  failed: "Did not finish",
};
export const classStatusLabel = (s: string | undefined | null): string => CLASS_STATUS_LABEL[s ?? ""] ?? "Unknown";

/** feedback.status → where the note is. */
export const FEEDBACK_STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  approved: "Approved",
  sent: "Sent to the instructor",
  discarded: "Discarded",
};

// ── the rated class in the queue ─────────────────────────────────────────────
/** class_ratings.review_status → what the team has done with the flag. */
export const REVIEW_STATUS_LABEL: Record<string, string> = {
  new: "New",
  notified: "Owner notified",
  confirmed: "Confirmed for analysis",
  analysis_started: "Analysis started",
  dismissed: "Dismissed",
};
export const reviewStatusLabel = (s: string | undefined | null): string => REVIEW_STATUS_LABEL[s ?? ""] ?? "New";

/** The action a band asks for, as the team says it. Mirrors ACTION_LABEL in lib/sentiment.ts. */
export const ACTION_WORDS: Record<string, string> = {
  video: "watch the recording",
  transcript: "read the transcript",
  none: "nothing needed",
  watch: "too few responses",
};
export const actionWords = (a: string | undefined | null): string => ACTION_WORDS[a ?? ""] ?? "nothing needed";

/** The agreed phrase for a class that fewer than six learners answered about. */
export const TOO_FEW = "too few responses";
