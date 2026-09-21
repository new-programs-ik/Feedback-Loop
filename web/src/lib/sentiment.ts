/** The Class Sentiment Score — the website's mirror of the scoring contract.
 *
 *  The reference is `analysis/sentiment_score.py`; the Postgres function (migration 0015) and
 *  this file must produce exactly what it produces for every case in
 *  `supabase/fixtures/scoring_cases.json` (`sentiment.test.ts` pins that). This module is pure:
 *  no Next, no React, no database — it runs in the browser (what-if preview, popovers) and in
 *  Node (the tests) alike.
 *
 *  A configuration is a plain object (stored as JSON in `scoring_configs.config`):
 *    rating    "linear" (rating / scale) or "knee" (0 at floor, line_value at line, 100 at scale)
 *    approval  "cliff" (100 at/above the bar, else 0) or "graded" (0 at floor → 100 at bar)
 *    sample    "cliff" (100 when num_ratings ≥ target), "graded" (num_ratings / target) or "off"
 *    reach     "graded" (num_ratings / attended) or "off"
 *    track     "on" (0 at floor → 100 at line) or "off"
 *    weights   points per component; only INCLUDED components count, the rest are re-scaled
 *    guard     k > 0 blends few votes toward the course's typical vote/rating (shrinkage)
 *    min_votes band: fewer votes → no band; action: fewer votes → never an analysis;
 *              low_rating_line: under the band floor, a class rated below it is still read (Average)
 *    caps      hard lines: under rating_line or approval_bar (with ≥ min_votes.action votes)
 *              caps the band at Average; both missed caps it at Bad
 *    bands     lower edges of Excellent / Good / Average; the band reads the ROUNDED score
 *    missing   what a missing input does: "neutral" (excluded, re-scaled) or "zero"
 *    actions   band → analysis depth; "no_data" → what happens under the vote floor
 */

export type Band = "excellent" | "good" | "average" | "bad";
export type Action = "video" | "transcript" | "none" | "watch";
export type ComponentKey = "rating" | "approval" | "sample" | "reach" | "track";
export type MissingMode = "neutral" | "zero";

export type ScoreFlag =
  | "invalid_num_ratings"
  | "invalid_attended"
  | "invalid_yes_votes"
  | "invalid_no_votes"
  | "invalid_rating"
  | "no_rating"
  | "rating_zero"
  | "no_vote"
  | "votes_ne_responses"
  | "no_responses"
  | "zero_responses"
  | "no_attendance"
  | "reach_clamped"
  | "rating_vote_disagree"
  | "guarded"
  | "no_track"
  | "under_rating_line"
  | "under_approval_bar"
  | "thin_no_band"
  | "thin_provisional"
  | "escalated"
  | "thin_approval_not_counted"
  | "thin_under_rating_line"
  | "thin_low_rating_read";

export type ScoringConfig = {
  name?: string;
  rating: { mode: "linear" | "knee"; scale: number; floor: number; line: number; line_value: number };
  approval: { mode: "cliff" | "graded"; bar: number; floor: number };
  sample: { mode: "cliff" | "graded" | "off"; target: number };
  reach: { mode: "graded" | "off" };
  track: { mode: "on" | "off"; floor: number; line: number; min_classes?: number };
  weights: Record<ComponentKey, number>;
  guard: { k: number; prior?: string };
  min_votes: { band: number; action: number; low_rating_line?: number | null };
  caps: { rating_line: number | null; approval_bar: number | null };
  bands: { excellent: number; good: number; average: number };
  missing: { approval: MissingMode; reach: MissingMode; track?: MissingMode };
  actions: Record<Band | "no_data", Action>;
  /** Fewer than `min_answers` approval answers: a passing approval does not count, and the rating
   *  must clear `rating_line` on its own or the band is capped at Average. Optional, so every
   *  stored configuration written before this keeps working unchanged. */
  thin?: { min_answers: number | null; rating_line: number | null } | null;
};

/** Anything the sheet can hand us: numbers, numeric strings, blanks, nulls. */
export type ScoreInputs = {
  rating?: number | string | null;
  num_ratings?: number | string | null;
  attended?: number | string | null;
  yes_votes?: number | string | null;
  no_votes?: number | string | null;
  escalated?: boolean | null;
  track_avg?: number | string | null;
  /** The course's typical rating / approval %, for the small-sample guard. */
  prior_rating?: number | string | null;
  prior_approval?: number | string | null;
};

export type ScoreResult = {
  /** Rounded to two decimals; null when the row cannot be scored at all. */
  score: number | null;
  /** null = no band (too few voices, or unscorable). */
  band: Band | null;
  action: Action;
  /** A band shown from fewer votes than an analysis needs. */
  provisional: boolean;
  /** Each included component's 0–100 value (rounded); null = excluded (neutral). */
  components: Partial<Record<ComponentKey, number | null>>;
  weights_used: Partial<Record<ComponentKey, number>>;
  flags: ScoreFlag[];
  /** The rating / approval after the guard (what the components were computed from). */
  adjusted: { rating: number | null; approval: number | null };
};

/** Best → worst. */
export const BAND_ORDER: readonly Band[] = ["excellent", "good", "average", "bad"] as const;
const BAND_RANK: Record<Band, number> = { excellent: 0, good: 1, average: 2, bad: 3 };

/** The four fixed band colours (tokens live in globals.css; never used for anything else). */
export const BAND_META: Record<
  Band,
  { label: string; short: string; color: string; soft: string; text: string; description: string }
> = {
  excellent: {
    label: "Excellent",
    short: "Exc",
    color: "var(--band-excellent)",
    soft: "var(--band-excellent-soft)",
    text: "var(--band-excellent-text)",
    description: "clears every bar with room to spare",
  },
  good: {
    label: "Good",
    short: "Good",
    color: "var(--band-good)",
    soft: "var(--band-good-soft)",
    text: "var(--band-good-text)",
    description: "fine on both lines",
  },
  average: {
    label: "Average",
    short: "Avg",
    color: "var(--band-average)",
    soft: "var(--band-average-soft)",
    text: "var(--band-average-text)",
    description: "one line missed — worth a transcript read",
  },
  bad: {
    label: "Bad",
    short: "Bad",
    color: "var(--band-bad)",
    soft: "var(--band-bad-soft)",
    text: "var(--band-bad-text)",
    description: "both lines missed, or the score is under 60",
  },
};

/** What each action asks of a person, in the team's words. Keep in step with lib/labels.ts. */
export const ACTION_LABEL: Record<Action, string> = {
  video: "watch the recording",
  transcript: "read the transcript",
  none: "nothing needed",
  watch: "too few responses",
};

export const COMPONENT_LABEL: Record<ComponentKey, string> = {
  rating: "Rating",
  approval: "Approval",
  sample: "Responses",
  reach: "Rated / attended",
  track: "Track record",
};

/** Version 1 in the database: the manager's original method (60/30/6/4, pass/fail). Used as the
 *  fallback whenever no active configuration can be loaded. */
export const DEFAULT_CONFIG: ScoringConfig = {
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

// ── helpers ───────────────────────────────────────────────────────────────────
function num(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const f = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(f)) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  return f;
}

const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));

/** Round half up to two decimals, exactly as Python's `Decimal(str(v)).quantize(0.01, HALF_UP)`
 *  and Postgres `round(numeric, 2)` do: the decision is made on the shortest decimal
 *  representation of the number, so 0.125 rounds to 0.13 and 2.675 (really 2.67499…) to 2.67
 *  because Python's `str()` and JavaScript's `String()` both print "2.675". */
export function round2(v: number): number {
  if (!Number.isFinite(v)) return v;
  const s = String(v);
  if (/e/i.test(s)) return Math.round((v + Number.EPSILON) * 100) / 100; // never for a 0–100 score
  const neg = s.startsWith("-");
  const [intPart, fracPart = ""] = (neg ? s.slice(1) : s).split(".");
  if (fracPart.length <= 2) return v;
  let digits = (intPart + fracPart.slice(0, 2)).split("").map(Number);
  if (Number(fracPart[2]) >= 5) {
    // add one unit in the last place, carrying leftwards
    let i = digits.length - 1;
    while (i >= 0) {
      if (digits[i] < 9) {
        digits[i] += 1;
        break;
      }
      digits[i] = 0;
      i -= 1;
    }
    if (i < 0) digits = [1, ...digits];
  }
  const str = digits.join("");
  const whole = str.slice(0, -2) || "0";
  const out = Number(`${whole}.${str.slice(-2)}`);
  return neg ? -out : out;
}

/** The band for a (rounded) score under a configuration. Reads the stored two-decimal score,
 *  so what a PM sees is what drives the queue. */
export function bandOf(score: number, config: ScoringConfig = DEFAULT_CONFIG): Band {
  const b = config.bands;
  return score >= b.excellent ? "excellent" : score >= b.good ? "good" : score >= b.average ? "average" : "bad";
}

function noScore(flags: ScoreFlag[], escalated: boolean, cfg: ScoringConfig): ScoreResult {
  const action: Action = escalated ? "video" : cfg.actions.no_data;
  if (escalated) flags.push("escalated");
  return {
    score: null,
    band: null,
    action,
    provisional: false,
    components: {},
    weights_used: {},
    flags,
    adjusted: { rating: null, approval: null },
  };
}

/** Score one class. Mirrors `score()` in analysis/sentiment_score.py line for line — keep the
 *  arithmetic in the same order so the two agree to the last bit. */
export function scoreClass(inputs: ScoreInputs, cfg: ScoringConfig = DEFAULT_CONFIG): ScoreResult {
  const flags: ScoreFlag[] = [];
  const rating = num(inputs.rating);
  const n = num(inputs.num_ratings);
  const attended = num(inputs.attended);
  const yes = num(inputs.yes_votes);
  const no = num(inputs.no_votes);
  const escalated = Boolean(inputs.escalated);
  const track = num(inputs.track_avg);
  const priorRating = num(inputs.prior_rating);
  const priorApproval = num(inputs.prior_approval);
  const scale = Number(cfg.rating.scale);

  // ---- reject nonsense outright --------------------------------------------------------------
  const counts: [ScoreFlag, number | null][] = [
    ["invalid_num_ratings", n],
    ["invalid_attended", attended],
    ["invalid_yes_votes", yes],
    ["invalid_no_votes", no],
  ];
  for (const [flag, val] of counts) if (val != null && val < 0) flags.push(flag);
  if (rating != null && (rating < 0 || rating > scale)) flags.push("invalid_rating");
  if (flags.some((f) => f.startsWith("invalid_"))) return noScore(flags, escalated, cfg);
  if (rating == null) {
    flags.push("no_rating");
    return noScore(flags, escalated, cfg);
  }
  if (rating === 0) {
    flags.push("rating_zero");
    return noScore(flags, escalated, cfg);
  }

  // ---- derived inputs ------------------------------------------------------------------------
  let votes: number | null = yes != null && no != null ? yes + no : null;
  if (votes != null && votes <= 0) votes = null;
  const approval: number | null = votes ? (yes! / votes) * 100.0 : null;
  if (approval == null) flags.push("no_vote");
  if (votes != null && n != null && Math.abs(votes - n) > 0.5) flags.push("votes_ne_responses");
  if (n == null) flags.push("no_responses");
  else if (n === 0) flags.push("zero_responses");
  if (attended == null || attended === 0) flags.push("no_attendance");
  let reach: number | null = null;
  if (n != null && attended) {
    reach = (n / attended) * 100.0;
    if (reach > 100.0) {
      reach = 100.0;
      flags.push("reach_clamped");
    }
  }
  if (approval != null && rating >= 4.5 && approval < 50) flags.push("rating_vote_disagree");

  // ---- small-sample guard (shrinkage toward the course's typical values) ---------------------
  const k = Number(cfg.guard?.k ?? 0) || 0;
  let adjRating = rating;
  let adjApproval = approval;
  if (k > 0) {
    if (priorRating != null && n != null) adjRating = (n * rating + k * priorRating) / (n + k);
    if (approval != null && priorApproval != null && votes)
      adjApproval = ((yes! + (k * priorApproval) / 100.0) / (votes + k)) * 100.0;
    if (adjRating !== rating || adjApproval !== approval) flags.push("guarded");
  }

  // ---- components ------------------------------------------------------------------------------
  const comps: Record<ComponentKey, number | null> = { rating: null, approval: null, sample: null, reach: null, track: null };
  const r = cfg.rating;
  let ratingPts: number;
  if (r.mode === "knee") {
    const floor = Number(r.floor);
    const line = Number(r.line);
    const lv = Number(r.line_value);
    if (adjRating <= floor) ratingPts = 0.0;
    else if (adjRating <= line) ratingPts = ((adjRating - floor) / (line - floor)) * lv;
    else ratingPts = lv + ((adjRating - line) / (scale - line)) * (100.0 - lv);
  } else {
    ratingPts = (adjRating / scale) * 100.0;
  }
  comps.rating = clamp(ratingPts);

  const a = cfg.approval;
  if (adjApproval == null) comps.approval = cfg.missing.approval === "zero" ? 0.0 : null;
  else if (a.mode === "graded")
    comps.approval = clamp(((adjApproval - Number(a.floor)) / (Number(a.bar) - Number(a.floor))) * 100.0);
  else comps.approval = adjApproval >= Number(a.bar) ? 100.0 : 0.0;

  // Too few approval answers: approval may warn, never vouch. A failing approval from a small group
  // still counts, because those classes mostly had a real content problem when checked against the
  // recording. A passing one from the same small group no longer lifts the score.
  const thin = cfg.thin ?? null;
  const thinMin = thin?.min_answers != null ? Number(thin.min_answers) : null;
  const isThin = thinMin != null && votes != null && votes < thinMin;
  if (isThin && adjApproval != null && adjApproval >= Number(a.bar)) {
    comps.approval = null;
    flags.push("thin_approval_not_counted");
  }

  const s = cfg.sample;
  if (s.mode === "off") comps.sample = null;
  else if (n == null) comps.sample = 0.0;
  else if (s.mode === "graded") comps.sample = clamp((n / Number(s.target)) * 100.0);
  else comps.sample = n >= Number(s.target) ? 100.0 : 0.0;

  if (cfg.reach.mode === "off") comps.reach = null;
  else if (reach == null) comps.reach = cfg.missing.reach === "zero" ? 0.0 : null;
  else comps.reach = reach;

  const t = cfg.track;
  if (t.mode !== "on" || track == null) {
    comps.track = null;
    if (t.mode === "on" && track == null) flags.push("no_track");
  } else {
    comps.track = clamp(((track - Number(t.floor)) / (Number(t.line) - Number(t.floor))) * 100.0);
  }

  const weights = cfg.weights;
  const used: Partial<Record<ComponentKey, number>> = {};
  const order: ComponentKey[] = ["rating", "approval", "sample", "reach", "track"];
  for (const key of order) {
    const w = Number(weights?.[key] ?? 0);
    if (comps[key] != null && w > 0) used[key] = w;
  }
  let denom = 0;
  for (const key of order) if (used[key] != null) denom += used[key]!;
  let raw = 0.0;
  if (denom) {
    let acc = 0;
    for (const key of order) if (used[key] != null) acc += comps[key]! * used[key]!;
    raw = acc / denom;
  }
  const sc = round2(raw);

  // ---- band, caps, vote floor ------------------------------------------------------------------
  let band = bandOf(sc, cfg);

  const mv: ScoringConfig["min_votes"] = cfg.min_votes ?? { band: 0, action: 0 };
  const actionFloor = Number(mv.action ?? 0) || 0;
  const enoughForAction = (votes != null ? votes : n || 0) >= actionFloor;
  const caps = cfg.caps ?? { rating_line: null, approval_bar: null };
  let missed = 0;
  if (caps.rating_line != null && enoughForAction && adjRating < Number(caps.rating_line)) {
    missed += 1;
    flags.push("under_rating_line");
  }
  if (caps.approval_bar != null && enoughForAction && adjApproval != null && adjApproval < Number(caps.approval_bar)) {
    missed += 1;
    flags.push("under_approval_bar");
  }
  if (missed === 1) band = BAND_ORDER[Math.max(BAND_RANK[band], BAND_RANK.average)];
  else if (missed >= 2) band = "bad";

  // With approval untrustworthy the rating carries the decision alone. Below the line the class is
  // read. Caps at Average, never pushes to Bad, so video does not grow.
  if (isThin && thin?.rating_line != null && adjRating < Number(thin.rating_line)) {
    if (BAND_RANK[band] < BAND_RANK.average) band = "average";
    flags.push("thin_under_rating_line");
  }

  const voices = votes != null ? votes : n || 0;
  let provisional = false;
  let bandOut: Band | null;
  const lowLine = mv.low_rating_line != null ? Number(mv.low_rating_line) : null;
  const underBandFloor = voices < (Number(mv.band ?? 0) || 0);
  if (underBandFloor && lowLine != null && adjRating < lowLine) {
    // Too few responses to judge the class, but rated low enough that the transcript is read anyway.
    bandOut = "average";
    flags.push("thin_low_rating_read");
  } else if (underBandFloor) {
    bandOut = null;
    flags.push("thin_no_band");
  } else {
    bandOut = band;
    if (!enoughForAction && actionFloor) {
      provisional = true;
      flags.push("thin_provisional");
    }
  }

  let action: Action;
  if (escalated) {
    action = "video";
    flags.push("escalated");
  } else if (bandOut == null || provisional) {
    action = cfg.actions.no_data;
  } else {
    action = cfg.actions[bandOut];
  }

  const components: Partial<Record<ComponentKey, number | null>> = {};
  for (const key of order) components[key] = comps[key] == null ? null : round2(comps[key]!);

  return {
    score: sc,
    band: bandOut,
    action,
    provisional,
    components,
    weights_used: used,
    flags,
    adjusted: { rating: round2(adjRating), approval: adjApproval == null ? null : round2(adjApproval) },
  };
}

// ── words ────────────────────────────────────────────────────────────────────
/** Python's `format(v, ".0f")` — ties go to the even neighbour on exact halves. */
function fmt0(v: number): string {
  const f = Math.floor(v);
  if (v - f === 0.5) return String(f % 2 === 0 ? f : f + 1);
  return String(Math.round(v));
}
/** Python's `format(v, ".2f")` for the values a rating can take. */
function fmt2(v: number): string {
  const scaled = v * 100;
  const f = Math.floor(scaled);
  if (scaled - f === 0.5) return ((f % 2 === 0 ? f : f + 1) / 100).toFixed(2);
  return v.toFixed(2);
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** One plain-English sentence a PM can read out — the mirror of `reason()` in the reference:
 *  "Rated 4.31 · 7 of 16 would have the instructor back (44%) → Bad → video analysis." */
export function explainClass(inputs: ScoreInputs, result: ScoreResult, _config: ScoringConfig = DEFAULT_CONFIG): string {
  void _config;
  const rating = num(inputs.rating);
  const yes = num(inputs.yes_votes);
  const no = num(inputs.no_votes);
  if (result.band == null) {
    if (result.flags.includes("no_rating")) return "No rating recorded yet.";
    return "Too few responses yet to judge this class.";
  }
  const parts: string[] = [];
  if (rating != null) parts.push(`Rated ${fmt2(rating)}`);
  if (yes != null && no != null && yes + no > 0) {
    const pct = (yes / (yes + no)) * 100;
    parts.push(`${Math.trunc(yes)} of ${Math.trunc(yes + no)} would have the instructor back (${fmt0(pct)}%)`);
  }
  const band = capitalize(result.band);
  const tail = ACTION_LABEL[result.action];
  const prov = result.provisional ? " (based on very few responses)" : "";
  return parts.join(" · ") + ` → ${band}${prov} → ${tail}.`;
}

/** The stored flags as words — for rows that carry a score from the database but no inputs
 *  worth re-scoring (and for the drawer's "why" list). Order follows the flags. */
export const FLAG_WORDS: Record<ScoreFlag, string> = {
  thin_approval_not_counted: "too few learners answered the approval question for a yes to count",
  thin_under_rating_line: "too few approval answers to rely on, and the rating alone is below the line",
  thin_low_rating_read: "too few responses to judge, but rated below 4.3, so the transcript is read",
  invalid_num_ratings: "the response count is negative",
  invalid_attended: "the attendance is negative",
  invalid_yes_votes: "the count of yes answers is negative",
  invalid_no_votes: "the count of no answers is negative",
  invalid_rating: "the rating is outside 0–5",
  no_rating: "no rating recorded",
  rating_zero: "the rating is 0",
  no_vote: "no approval answer recorded",
  votes_ne_responses: "approval answers and responses do not add up",
  no_responses: "the response count is missing",
  zero_responses: "nobody responded",
  no_attendance: "attendance is missing",
  reach_clamped: "more learners rated than attended (capped at 100%)",
  rating_vote_disagree: "the rating and the instructor approval disagree",
  guarded: "few responses — blended with the course's typical values",
  no_track: "no track record yet (first classes)",
  under_rating_line: "rated below the line the team set",
  under_approval_bar: "instructor approval below the bar the team set",
  thin_no_band: "too few responses for a band",
  thin_provisional: "too few responses to be sure — provisional",
  escalated: "escalated by a PM",
};

/** Never a raw code on screen: an unknown flag is simply left out of the "why" list. */
export function flagsToWords(flags: readonly string[]): string[] {
  return flags.map((f) => FLAG_WORDS[f as ScoreFlag]).filter((w): w is string => Boolean(w));
}

/** Component rows for the popover / drawer: label, what was measured, and points earned. */
export type ComponentRow = {
  key: ComponentKey;
  label: string;
  detail: string;
  earned: number | null;
  weight: number;
  included: boolean;
};

export function componentRows(inputs: ScoreInputs, result: ScoreResult, cfg: ScoringConfig = DEFAULT_CONFIG): ComponentRow[] {
  const n = num(inputs.num_ratings);
  const attended = num(inputs.attended);
  const yes = num(inputs.yes_votes);
  const no = num(inputs.no_votes);
  const track = num(inputs.track_avg);
  const rating = result.adjusted.rating ?? num(inputs.rating);
  const votes = yes != null && no != null ? yes + no : null;
  const approval = result.adjusted.approval;
  const reach = n != null && attended ? Math.min(100, (n / attended) * 100) : null;
  const rows: ComponentRow[] = [];
  const order: ComponentKey[] = ["rating", "approval", "sample", "reach", "track"];
  for (const key of order) {
    const weight = Number(cfg.weights?.[key] ?? 0);
    if (weight <= 0) continue;
    const value = result.components[key];
    const included = value != null;
    const earned = included ? round2((value! / 100) * weight) : null;
    let detail = "—";
    switch (key) {
      case "rating":
        detail = rating != null ? `${fmt2(rating)} / ${cfg.rating.scale}` : "no rating";
        break;
      case "approval":
        detail =
          approval != null && votes
            ? `${Math.trunc(yes!)} of ${Math.trunc(votes)} · ${fmt0(approval)}% (bar ${cfg.approval.bar}%)`
            : "no vote";
        break;
      case "sample":
        detail = n != null ? `${n} rated (target ${cfg.sample.target})` : "responses unknown";
        break;
      case "reach":
        detail = reach != null ? `${n} of ${attended} · ${fmt0(reach)}%` : "attendance unknown";
        break;
      case "track":
        detail = track != null ? `${fmt2(track)} over earlier classes` : "no track record";
        break;
    }
    rows.push({ key, label: COMPONENT_LABEL[key], detail, earned, weight, included });
  }
  return rows;
}
