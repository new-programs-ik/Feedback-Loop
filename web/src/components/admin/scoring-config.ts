/** The scoring configuration contract — the JSON shape stored in `scoring_configs.config`.
 *
 *  Source of truth: analysis/sentiment_score.py (the docstring lists every switch) and the two
 *  fixture files in supabase/fixtures. This file holds the TYPE, the two presets the team talks
 *  about (the manager's original and the recommended "two lines + graded" candidate), the
 *  plain-English helper text the editor shows, and the pure helpers (normalise / validate /
 *  flatten / diff) that both the server actions and the client editor use. No React, no I/O. */

export type RatingMode = "linear" | "knee";
export type ApprovalMode = "cliff" | "graded";
export type SampleMode = "cliff" | "graded" | "off";
export type ReachMode = "graded" | "off";
export type TrackMode = "on" | "off";
export type MissingPolicy = "neutral" | "zero";
export type ActionKind = "video" | "transcript" | "none" | "watch";
export type Band = "excellent" | "good" | "average" | "bad";
export type Component = "rating" | "approval" | "sample" | "reach" | "track";

export const BANDS: readonly Band[] = ["excellent", "good", "average", "bad"] as const;
export const COMPONENTS: readonly Component[] = ["rating", "approval", "sample", "reach", "track"] as const;
export const ACTIONS: readonly ActionKind[] = ["video", "transcript", "none", "watch"] as const;

export type ScoringConfig = {
  name?: string;
  rating: { mode: RatingMode; scale: number; floor: number; line: number; line_value: number };
  approval: { mode: ApprovalMode; bar: number; floor: number };
  sample: { mode: SampleMode; target: number };
  reach: { mode: ReachMode };
  track: { mode: TrackMode; floor: number; line: number; min_classes: number };
  weights: Record<Component, number>;
  guard: { k: number; prior: "course" | "global" };
  min_votes: { band: number; action: number };
  caps: { rating_line: number | null; approval_bar: number | null };
  bands: { excellent: number; good: number; average: number };
  missing: { approval: MissingPolicy; reach: MissingPolicy; track: MissingPolicy };
  actions: { bad: ActionKind; average: ActionKind; good: ActionKind; excellent: ActionKind; no_data: ActionKind };
  /** Fewer than min_answers approval answers: a passing approval does not count, and the rating must
   *  clear rating_line on its own or the class is capped at Average. Absent = off. */
  thin?: { min_answers: number | null; rating_line: number | null };
};

/** C0 — the manager's method exactly as written (60/30/6/4, pass/fail). Mirrors
 *  supabase/fixtures/scoring_configs.json → "C0". */
export const MANAGER_ORIGINAL: ScoringConfig = {
  name: "Manager's original (60/30/6/4, pass/fail)",
  rating: { mode: "linear", scale: 5, floor: 3.55, line: 4.55, line_value: 75 },
  approval: { mode: "cliff", bar: 80, floor: 40 },
  sample: { mode: "cliff", target: 10 },
  reach: { mode: "graded" },
  track: { mode: "off", floor: 4.05, line: 4.55, min_classes: 3 },
  weights: { rating: 60, approval: 30, sample: 6, reach: 4, track: 0 },
  guard: { k: 0, prior: "course" },
  min_votes: { band: 0, action: 0 },
  caps: { rating_line: null, approval_bar: null },
  bands: { excellent: 90, good: 75, average: 60 },
  missing: { approval: "zero", reach: "zero", track: "neutral" },
  actions: { bad: "video", average: "transcript", good: "none", excellent: "none", no_data: "watch" },
};

/** C5 — the recommended candidate: the two lines the team already agreed (4.55 / 80%) as hard
 *  lines, everything else graded, a small-sample guard, and a vote floor. Mirrors "C5". */
export const TWO_LINES_GRADED: ScoringConfig = {
  name: "Two lines + graded score",
  rating: { mode: "knee", scale: 5, floor: 3.55, line: 4.55, line_value: 75 },
  approval: { mode: "graded", bar: 80, floor: 40 },
  sample: { mode: "off", target: 10 },
  reach: { mode: "off" },
  track: { mode: "on", floor: 4.05, line: 4.55, min_classes: 3 },
  weights: { rating: 60, approval: 25, sample: 0, reach: 0, track: 15 },
  guard: { k: 5, prior: "course" },
  min_votes: { band: 3, action: 5 },
  caps: { rating_line: 4.55, approval_bar: 80 },
  bands: { excellent: 90, good: 75, average: 60 },
  missing: { approval: "neutral", reach: "neutral", track: "neutral" },
  actions: { bad: "video", average: "transcript", good: "none", excellent: "none", no_data: "watch" },
};

export const PRESETS: { key: string; label: string; config: ScoringConfig }[] = [
  { key: "C0", label: "Manager's original", config: MANAGER_ORIGINAL },
  { key: "C5", label: "Two lines + graded (recommended)", config: TWO_LINES_GRADED },
];

// ── coercion ─────────────────────────────────────────────────────────────────
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function num(v: unknown, fallback: number): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return fallback;
}
function numOrNull(v: unknown, fallback: number | null): number | null {
  if (v === null) return null;
  if (v === undefined) return fallback;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    if (v.trim() === "") return null;
    if (Number.isFinite(Number(v))) return Number(v);
  }
  return fallback;
}
function pick<T extends string>(v: unknown, allowed: readonly T[], fallback: T): T {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

/** Turn whatever the database (or a form) holds into a complete config. Unknown keys are
 *  dropped, missing keys take the manager's-original default, numbers are coerced. */
export function normalizeConfig(raw: unknown, base: ScoringConfig = MANAGER_ORIGINAL): ScoringConfig {
  const r = isObj(raw) ? raw : {};
  const sub = (k: string) => (isObj(r[k]) ? (r[k] as Record<string, unknown>) : {});
  const rating = sub("rating"), approval = sub("approval"), sample = sub("sample"), reach = sub("reach");
  const track = sub("track"), weights = sub("weights"), guard = sub("guard"), mv = sub("min_votes");
  const caps = sub("caps"), bands = sub("bands"), missing = sub("missing"), actions = sub("actions");
  const thin = sub("thin");
  return {
    ...(typeof r.name === "string" ? { name: r.name } : base.name ? { name: base.name } : {}),
    rating: {
      mode: pick(rating.mode, ["linear", "knee"], base.rating.mode),
      scale: num(rating.scale, base.rating.scale),
      floor: num(rating.floor, base.rating.floor),
      line: num(rating.line, base.rating.line),
      line_value: num(rating.line_value, base.rating.line_value),
    },
    approval: {
      mode: pick(approval.mode, ["cliff", "graded"], base.approval.mode),
      bar: num(approval.bar, base.approval.bar),
      floor: num(approval.floor, base.approval.floor),
    },
    sample: { mode: pick(sample.mode, ["cliff", "graded", "off"], base.sample.mode), target: num(sample.target, base.sample.target) },
    reach: { mode: pick(reach.mode, ["graded", "off"], base.reach.mode) },
    track: {
      mode: pick(track.mode, ["on", "off"], base.track.mode),
      floor: num(track.floor, base.track.floor),
      line: num(track.line, base.track.line),
      min_classes: num(track.min_classes, base.track.min_classes),
    },
    weights: {
      rating: num(weights.rating, base.weights.rating),
      approval: num(weights.approval, base.weights.approval),
      sample: num(weights.sample, base.weights.sample),
      reach: num(weights.reach, base.weights.reach),
      track: num(weights.track, base.weights.track),
    },
    guard: { k: num(guard.k, base.guard.k), prior: pick(guard.prior, ["course", "global"], base.guard.prior) },
    min_votes: { band: num(mv.band, base.min_votes.band), action: num(mv.action, base.min_votes.action) },
    caps: {
      rating_line: numOrNull(caps.rating_line, base.caps.rating_line),
      approval_bar: numOrNull(caps.approval_bar, base.caps.approval_bar),
    },
    bands: {
      excellent: num(bands.excellent, base.bands.excellent),
      good: num(bands.good, base.bands.good),
      average: num(bands.average, base.bands.average),
    },
    missing: {
      approval: pick(missing.approval, ["neutral", "zero"], base.missing.approval),
      reach: pick(missing.reach, ["neutral", "zero"], base.missing.reach),
      track: pick(missing.track, ["neutral", "zero"], base.missing.track),
    },
    actions: {
      bad: pick(actions.bad, ACTIONS, base.actions.bad),
      average: pick(actions.average, ACTIONS, base.actions.average),
      good: pick(actions.good, ACTIONS, base.actions.good),
      excellent: pick(actions.excellent, ACTIONS, base.actions.excellent),
      no_data: pick(actions.no_data, ACTIONS, base.actions.no_data),
    },
    ...(isObj(r.thin)
      ? { thin: { min_answers: numOrNull(thin.min_answers, null), rating_line: numOrNull(thin.rating_line, null) } }
      : base.thin
        ? { thin: { ...base.thin } }
        : {}),
  };
}

/** Deep copy (configs are small; JSON round-trip is the simplest faithful clone). */
export const cloneConfig = (cfg: ScoringConfig): ScoringConfig => JSON.parse(JSON.stringify(cfg)) as ScoringConfig;

// ── validation ────────────────────────────────────────────────────────────────
/** Components the config actually uses (mode not off AND a positive weight). */
export function includedComponents(cfg: ScoringConfig): Component[] {
  const on: Record<Component, boolean> = {
    rating: true,
    approval: true,
    sample: cfg.sample.mode !== "off",
    reach: cfg.reach.mode !== "off",
    track: cfg.track.mode === "on",
  };
  return COMPONENTS.filter((c) => on[c] && cfg.weights[c] > 0);
}

export function weightSum(cfg: ScoringConfig): number {
  return includedComponents(cfg).reduce((a, c) => a + cfg.weights[c], 0);
}

/** Hard errors — the config cannot be saved or previewed with any of these. */
export function validateConfig(cfg: ScoringConfig): string[] {
  const errs: string[] = [];
  const r = cfg.rating;
  if (!(r.scale > 0)) errs.push("Rating scale must be above 0.");
  if (!(r.floor < r.line && r.line < r.scale)) errs.push("Rating floor < line < scale must hold (e.g. 3.55 < 4.55 < 5).");
  if (!(r.line_value > 0 && r.line_value < 100)) errs.push("Rating line value must be between 0 and 100.");
  if (!(cfg.approval.floor < cfg.approval.bar)) errs.push("Approval floor must be below the approval bar.");
  if (!(cfg.approval.bar > 0 && cfg.approval.bar <= 100)) errs.push("Approval bar must be between 1 and 100.");
  if (cfg.sample.mode !== "off" && !(cfg.sample.target > 0)) errs.push("Response target must be above 0.");
  if (cfg.track.mode === "on" && !(cfg.track.floor < cfg.track.line)) errs.push("Track-record floor must be below its line.");
  if (cfg.track.mode === "on" && !(cfg.track.min_classes >= 0)) errs.push("Track-record minimum classes cannot be negative.");
  if (!(cfg.guard.k >= 0)) errs.push("Guard k cannot be negative.");
  if (!(cfg.min_votes.band >= 0 && cfg.min_votes.action >= 0)) errs.push("Minimum votes cannot be negative.");
  const b = cfg.bands;
  if (!(b.excellent > b.good && b.good > b.average && b.average > 0 && b.excellent <= 100))
    errs.push("Band edges must descend: Excellent > Good > Average > 0 (and Excellent ≤ 100).");
  if (cfg.caps.rating_line != null && !(cfg.caps.rating_line > 0 && cfg.caps.rating_line <= r.scale))
    errs.push("The hard rating line must sit inside the rating scale.");
  if (cfg.caps.approval_bar != null && !(cfg.caps.approval_bar > 0 && cfg.caps.approval_bar <= 100))
    errs.push("The hard approval bar must be between 1 and 100.");
  if (cfg.thin?.min_answers != null && !(cfg.thin.min_answers >= 0))
    errs.push("The minimum approval answers cannot be negative.");
  if (cfg.thin?.rating_line != null && !(cfg.thin.rating_line > 0 && cfg.thin.rating_line <= r.scale))
    errs.push("The rating a thin class must clear has to sit inside the rating scale.");
  for (const c of COMPONENTS) if (!(cfg.weights[c] >= 0)) errs.push(`Weight for ${c} cannot be negative.`);
  if (includedComponents(cfg).length === 0) errs.push("At least one component needs a positive weight.");
  return errs;
}

// ── diff / display ────────────────────────────────────────────────────────────
export type FlatRow = { path: string; label: string; value: string };

const LABELS: Record<string, string> = {
  "rating.mode": "Rating · mode",
  "rating.scale": "Rating · scale",
  "rating.floor": "Rating · floor (0 points)",
  "rating.line": "Rating · line",
  "rating.line_value": "Rating · points at the line",
  "approval.mode": "Approval · mode",
  "approval.bar": "Approval · bar (100 points)",
  "approval.floor": "Approval · floor (0 points)",
  "sample.mode": "Responses · mode",
  "sample.target": "Responses · target",
  "reach.mode": "Reach · mode",
  "track.mode": "Track record · mode",
  "track.floor": "Track record · floor",
  "track.line": "Track record · line",
  "track.min_classes": "Track record · min classes",
  "weights.rating": "Weight · rating",
  "weights.approval": "Weight · approval",
  "weights.sample": "Weight · responses",
  "weights.reach": "Weight · reach",
  "weights.track": "Weight · track record",
  "guard.k": "Small-sample guard · k",
  "guard.prior": "Small-sample guard · prior",
  "min_votes.band": "Minimum votes · to show a band",
  "min_votes.action": "Minimum votes · to trigger an analysis",
  "caps.rating_line": "Hard line · rating",
  "caps.approval_bar": "Hard line · approval",
  "thin.min_answers": "Approval counts from · answers",
  "thin.rating_line": "Fewer answers · rating must clear",
  "bands.excellent": "Band edge · Excellent from",
  "bands.good": "Band edge · Good from",
  "bands.average": "Band edge · Average from",
  "missing.approval": "Missing approval →",
  "missing.reach": "Missing reach →",
  "missing.track": "Missing track record →",
  "actions.excellent": "Excellent →",
  "actions.good": "Good →",
  "actions.average": "Average →",
  "actions.bad": "Bad →",
  "actions.no_data": "Too few voices →",
};

const fmtVal = (v: unknown): string =>
  v === null || v === undefined ? "off" : typeof v === "number" ? String(v) : String(v);

/** Every setting as a (path, label, value) row in a fixed, readable order. */
export function flattenConfig(cfg: ScoringConfig): FlatRow[] {
  const c = cfg as unknown as Record<string, Record<string, unknown>>;
  return Object.keys(LABELS).map((path) => {
    const [a, b] = path.split(".");
    return { path, label: LABELS[path], value: fmtVal(c[a]?.[b]) };
  });
}

export type DiffRow = { path: string; label: string; before: string; after: string; changed: boolean };

/** Side-by-side rows for two configs; `changed` marks the ones that differ. */
export function diffConfigs(before: ScoringConfig, after: ScoringConfig): DiffRow[] {
  const a = flattenConfig(before);
  const b = flattenConfig(after);
  return a.map((row, i) => ({
    path: row.path,
    label: row.label,
    before: row.value,
    after: b[i].value,
    changed: row.value !== b[i].value,
  }));
}

/** Plain-English helper lines the editor prints under every control. */
export const FIELD_HELP = {
  ratingMode: "Linear: stars ÷ scale. Knee: 0 points at the floor, the line value at the line, 100 at the top — steeper below the line.",
  ratingScale: "The top of the star scale (5 for a 1–5 rating).",
  ratingFloor: "At or below this rating the class earns 0 rating points (knee mode only).",
  ratingLine: "The rating the team treats as the pass mark (4.55 today).",
  ratingLineValue: "How many of the 100 rating points a class exactly on the line earns (knee mode only).",
  approvalMode: "Cliff: all points at the bar, none below. Graded: points rise from the floor to the bar, so 79% is nearly as good as 80%.",
  approvalBar: "The share of voters who would have the instructor back that earns full approval points (80% today).",
  approvalFloor: "Below this approval the class earns 0 approval points (graded mode only).",
  sampleMode: "Cliff: full points at the target. Graded: points grow with responses up to the target. Off: responses do not score.",
  sampleTarget: "How many rated responses count as a full sample (10 today).",
  reachMode: "Graded: points = the share of attendees who rated. Off: reach does not score.",
  trackMode: "On: the instructor's average over earlier classes scores too. Off: only this class counts.",
  trackFloor: "Track-record average that earns 0 points.",
  trackLine: "Track-record average that earns 100 points.",
  trackMinClasses: "How many earlier classes an instructor needs before a track record counts (worker-side).",
  weights: "Points per component. Only components that are switched on count; the rest are re-scaled so the total still reads out of 100.",
  guardK: "0 = off. Otherwise a few votes are blended with k typical votes for the course, so three opinions cannot sink a class alone; once many have voted their own votes take over.",
  guardPrior: "Where the typical values come from — this course's own classes, or every course.",
  minVotesBand: "Fewer voices than this → no band is shown (“— · too few voices”).",
  minVotesAction: "Fewer voices than this → the class is watched, never analysed (unless a PM escalates).",
  capRating: "With enough votes, a class under this rating can never sit above Average — under both lines it is Bad.",
  capApproval: "With enough votes, a class under this approval can never sit above Average — under both lines it is Bad.",
  thinMinAnswers: "Below this many approval answers, a passing approval adds no points (a failing one still counts).",
  thinRatingLine: "Below that many approval answers, a class under this rating is capped at Average, so its transcript is read.",
  bands: "Lower edge of each band, read from the score rounded to two decimals. Everything under the Average edge is Bad.",
  missing: "Neutral: the component is left out and the others re-scaled (never a penalty). Zero: it scores 0.",
  actions: "What each band triggers in the queue. Too few voices uses the last row.",
} as const;
