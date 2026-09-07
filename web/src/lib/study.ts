// The explicit extension lets `node --test` load this file without a bundler (study.test.ts).
import { scoreClass, type Band, type ScoreInputs, type ScoreResult, type ScoringConfig } from "./sentiment.ts";

/** The live study — the validation study (analysis/sentiment_*.py, Jan–Aug 2026) re-run in the
 *  browser's own arithmetic on whatever classes are in hand, so leadership can check the score
 *  without opening the PDF. Pure: no Next, no React, no database — `node --test` runs it.
 *
 *  Every measure mirrors the study's definition (analysis/sentiment_common.py `evaluate`):
 *    · votes = yes + no; approval = yes / votes; a class is "voiced" from 5 votes (VOICES)
 *    · "low" = rated under the 4.55 line or under the 80% approval bar — the two agreed lines
 *    · the next class = the same instructor's next class by date; a pair counts when both
 *      sides have 5+ votes; provisional bands are left out of the per-band shares
 *    · "false comfort" = a voiced low class shown Good or Excellent; "false alarm" = a voiced
 *      Bad class that clears both lines; "Bad above the line" = a Bad class rated 4.55+
 *  Scoring goes through `scoreClass` with the same inputs and course priors the app uses
 *  (class-score.ts `rowInputs` / `coursePriors`, repeated here so this file stays importable
 *  without the app's path aliases). Shares are percentages (0–100) throughout. */

export const RATING_LINE = 4.55;
export const APPROVAL_BAR = 80;
/** The study's voice floor for the two human signals and the next-class pairs. */
export const VOICES = 5;
/** Pairs a band needs before its next-class share is shown. */
export const MIN_PAIRS = 20;
export const BANDS: readonly Band[] = ["excellent", "good", "average", "bad"] as const;

/** The slice of a scored class row the study reads. `ScoredRating` satisfies it structurally;
 *  tests build these by hand. The stored verdict (`score`/`band`/`provisional`) is what the
 *  active version said — the cfg-less helpers read it; the cfg helpers re-score. */
export type StudyRow = {
  id: string;
  class_date: string;
  rating: number;
  num_ratings: number | null;
  attended: number | null;
  yes_votes: number | null;
  no_votes: number | null;
  approval_pct?: number | null;
  participation_pct?: number | null;
  escalated?: boolean | null;
  track_avg?: number | null;
  course_id?: string | null;
  course_label?: string | null;
  instructor_id?: string | null;
  instructor?: string | null;
  instructor_canonical?: string | null;
  topic?: string | null;
  session_kind?: string | null;
  /** "IND" / "US" when the cohort says so. */
  region?: string | null;
  score?: number | null;
  band?: Band | null;
  provisional?: boolean | null;
};

// ── row readers ───────────────────────────────────────────────────────────────
const num = (v: number | string | null | undefined): number | null => {
  if (v == null || v === "") return null;
  const f = typeof v === "number" ? v : Number(v);
  return Number.isNaN(f) ? null : f;
};

export const mean = (xs: number[]): number | null => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const pct = (part: number, whole: number): number | null => (whole > 0 ? (part / whole) * 100 : null);
const nums = (xs: (number | null | undefined)[]) => xs.filter((v): v is number => v != null && !Number.isNaN(v));

/** The voices behind a class: the vote count when a vote was recorded, else the rating count —
 *  the contract's own definition (sentiment.ts), which equals the study's `votes` wherever the
 *  sheet carries the Yes / No columns. */
export function voicesOf(r: StudyRow): number {
  const yes = num(r.yes_votes);
  const no = num(r.no_votes);
  if (yes != null || no != null) return (yes ?? 0) + (no ?? 0);
  return num(r.num_ratings) ?? 0;
}

/** yes / (yes + no) as a percentage; the stored approval when only that is known; null otherwise. */
export function approvalOf(r: StudyRow): number | null {
  const yes = num(r.yes_votes);
  const no = num(r.no_votes);
  if (yes != null && no != null && yes + no > 0) return (yes / (yes + no)) * 100;
  return num(r.approval_pct);
}

export const underLine = (r: StudyRow) => r.rating < RATING_LINE;
export const underBar = (r: StudyRow) => {
  const a = approvalOf(r);
  return a != null && a < APPROVAL_BAR;
};
/** The study's `low_next`: rated under the line or under the bar. */
export const isLow = (r: StudyRow) => underLine(r) || underBar(r);

/** Same key `byCourse` / `coursePriors` use: the course id, else the sheet's label. */
export const courseKeyOf = (r: StudyRow) => r.course_id ?? `label:${r.course_label ?? ""}`;

/** Same key `instructorKey` uses; null when the row names nobody. */
export function instructorKeyOf(r: StudyRow): string | null {
  if (r.instructor_id) return r.instructor_id;
  const name = (r.instructor_canonical || r.instructor || "").trim();
  return name ? `name:${name}` : null;
}

// ── scoring under a configuration ─────────────────────────────────────────────
export type Priors = { rating: number | null; approval: number | null };

/** The course's typical rating and pooled approval — the small-sample guard's prior — from
 *  the rows in hand. Mirrors class-score.ts `coursePriors`. */
export function priorsByCourse(rows: StudyRow[]): Map<string, Priors> {
  const acc = new Map<string, { ratings: number[]; yes: number; votes: number }>();
  for (const r of rows) {
    const key = courseKeyOf(r);
    const a = acc.get(key) ?? { ratings: [], yes: 0, votes: 0 };
    a.ratings.push(r.rating);
    const yes = num(r.yes_votes);
    const no = num(r.no_votes);
    if (yes != null && no != null) {
      a.yes += yes;
      a.votes += yes + no;
    }
    acc.set(key, a);
  }
  const out = new Map<string, Priors>();
  for (const [key, a] of acc) out.set(key, { rating: mean(a.ratings), approval: a.votes > 0 ? (a.yes / a.votes) * 100 : null });
  return out;
}

/** Mirrors class-score.ts `rowInputs`. */
export function inputsOf(r: StudyRow, priors?: Priors | null): ScoreInputs {
  return {
    rating: r.rating,
    num_ratings: r.num_ratings,
    attended: r.attended,
    yes_votes: r.yes_votes,
    no_votes: r.no_votes,
    escalated: Boolean(r.escalated),
    track_avg: r.track_avg ?? null,
    prior_rating: priors?.rating ?? null,
    prior_approval: priors?.approval ?? null,
  };
}

/** Every row scored under `cfg`, aligned with `rows`. */
export function scoreUnder(rows: StudyRow[], cfg: ScoringConfig): ScoreResult[] {
  const priors = priorsByCourse(rows);
  return rows.map((r) => scoreClass(inputsOf(r, priors.get(courseKeyOf(r))), cfg));
}

export type BandCounts = Record<Band, number>;
export const emptyBands = (): BandCounts => ({ excellent: 0, good: 0, average: 0, bad: 0 });

// ── the window ────────────────────────────────────────────────────────────────
const isoOf = (d: Date) => d.toISOString().slice(0, 10);
const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const monthLabel = (ym: string) => MONTH_SHORT[Number(ym.slice(5, 7)) - 1] ?? ym;
const dayLabel = (iso: string) => `${Number(iso.slice(8, 10))} ${monthLabel(iso)}`;

export type StudyWindow = { from: string; to: string; label: string; fullMonths: boolean; days: number; weeks: number };

/** The last `months` full calendar months before today — the study's own shape of window — or
 *  1 January → today while the year is still shorter than that. */
export function studyWindow(todayIso: string, months = 8): StudyWindow {
  const y = Number(todayIso.slice(0, 4));
  const m = Number(todayIso.slice(5, 7)); // 1–12
  const yearStart = `${y}-01-01`;
  const from = isoOf(new Date(Date.UTC(y, m - 1 - months, 1)));
  const to = isoOf(new Date(Date.UTC(y, m - 1, 0))); // the last day of the previous month
  const full = from >= yearStart;
  const win = full ? { from, to } : { from: yearStart, to: todayIso };
  const days = Math.round((+new Date(win.to + "T00:00:00Z") - +new Date(win.from + "T00:00:00Z")) / 86400000) + 1;
  const label = full
    ? `${monthLabel(win.from)}–${monthLabel(win.to)} ${win.to.slice(0, 4)}`
    : `${dayLabel(win.from)} – ${dayLabel(win.to)} ${win.to.slice(0, 4)}`;
  return { ...win, label, fullMonths: full, days, weeks: Math.max(1, days / 7) };
}

// ── Y3: does the band predict the next class? ─────────────────────────────────
export type BandRisk = {
  band: Band;
  /** Pairs whose first class carries a firm band under the configuration. */
  n: number;
  /** …of which the next class went wrong. */
  low: number;
  /** low / n as a percentage; null when there are too few pairs. */
  lowPct: number | null;
  tooFew: boolean;
};

export type NextClassRisk = {
  bands: BandRisk[];
  /** Every pair, whatever the band: the base rate a band has to beat. */
  baseline: { n: number; low: number; lowPct: number | null };
  pairs: number;
  minPairs: number;
};

/** For every class, the same instructor's NEXT class (by date); pairs with 5+ votes on both
 *  sides. Per band under `cfg`: the share of next classes that were low — rated under 4.55,
 *  under 80% approval, or Bad under the same configuration (the last is the spec's wording and
 *  in practice a subset of the first two). A band with fewer than `minPairs` pairs is marked
 *  "too few" and shows no share. */
export function nextClassRisk(
  rows: StudyRow[],
  cfg: ScoringConfig,
  opts: { minPairs?: number; voices?: number; results?: ScoreResult[] } = {},
): NextClassRisk {
  const minPairs = opts.minPairs ?? MIN_PAIRS;
  const voices = opts.voices ?? VOICES;
  const results = opts.results ?? scoreUnder(rows, cfg);
  const keys = rows.map(instructorKeyOf);
  const order = rows
    .map((_, i) => i)
    .filter((i) => keys[i] != null)
    .sort((a, b) => {
      const ka = keys[a]!;
      const kb = keys[b]!;
      if (ka !== kb) return ka < kb ? -1 : 1;
      const da = rows[a].class_date;
      const db = rows[b].class_date;
      if (da !== db) return da < db ? -1 : 1;
      const ta = (rows[a].topic ?? "").trim();
      const tb = (rows[b].topic ?? "").trim();
      if (ta !== tb) return ta < tb ? -1 : 1;
      return rows[a].id < rows[b].id ? -1 : rows[a].id > rows[b].id ? 1 : 0;
    });
  const pairs: [number, number][] = [];
  for (let k = 0; k + 1 < order.length; k++) {
    const i = order[k];
    const j = order[k + 1];
    if (keys[i] !== keys[j]) continue; // the last class of an instructor has no next class
    if (voicesOf(rows[i]) < voices || voicesOf(rows[j]) < voices) continue;
    pairs.push([i, j]);
  }
  const lowNext = (j: number) => isLow(rows[j]) || results[j].band === "bad";
  const acc: Record<Band, { n: number; low: number }> = { excellent: { n: 0, low: 0 }, good: { n: 0, low: 0 }, average: { n: 0, low: 0 }, bad: { n: 0, low: 0 } };
  let baseLow = 0;
  for (const [i, j] of pairs) {
    const low = lowNext(j);
    if (low) baseLow += 1;
    const x = results[i];
    if (x.band == null || x.provisional) continue;
    acc[x.band].n += 1;
    if (low) acc[x.band].low += 1;
  }
  const bands = BANDS.map((band) => {
    const a = acc[band];
    const tooFew = a.n < minPairs;
    return { band, n: a.n, low: a.low, lowPct: tooFew ? null : pct(a.low, a.n), tooFew };
  });
  return { bands, baseline: { n: pairs.length, low: baseLow, lowPct: pct(baseLow, pairs.length) }, pairs: pairs.length, minPairs };
}

// ── Y2: the two human signals ─────────────────────────────────────────────────
export type FalseComfort = {
  /** Classes with 5+ votes — the population. */
  voiced: number;
  /** Low classes (under 4.55 or under 80%) shown Good or Excellent, provisional bands included. */
  count: number;
  /** …with a firm band: the number the study quotes. */
  firm: number;
  /** …with a provisional band (few votes — watched, not acted on). */
  provisional: number;
  /** Of the count: how many missed the rating line (the rest missed the approval bar only). */
  byRating: number;
  byApproval: number;
  sharePct: number | null;
  firmSharePct: number | null;
};

/** Classes with 5+ votes that are low (under 4.55 or under 80% approval) yet show Good or
 *  Excellent under `cfg` — the "false comfort" the study vetoed above 5%. */
export function falseComfort(rows: StudyRow[], cfg: ScoringConfig, results: ScoreResult[] = scoreUnder(rows, cfg)): FalseComfort {
  let voiced = 0;
  let count = 0;
  let firm = 0;
  let byRating = 0;
  rows.forEach((r, i) => {
    if (voicesOf(r) < VOICES) return;
    voiced += 1;
    const x = results[i];
    if ((x.band === "good" || x.band === "excellent") && isLow(r)) {
      count += 1;
      if (!x.provisional) firm += 1;
      if (underLine(r)) byRating += 1;
    }
  });
  return { voiced, count, firm, provisional: count - firm, byRating, byApproval: count - byRating, sharePct: pct(count, voiced), firmSharePct: pct(firm, voiced) };
}

export type FalseAlarm = { voiced: number; count: number; sharePct: number | null };

/** Classes with 5+ votes shown Bad under `cfg` although they clear both lines. */
export function falseAlarm(rows: StudyRow[], cfg: ScoringConfig, results: ScoreResult[] = scoreUnder(rows, cfg)): FalseAlarm {
  let voiced = 0;
  let count = 0;
  rows.forEach((r, i) => {
    if (voicesOf(r) < VOICES) return;
    voiced += 1;
    const a = approvalOf(r);
    if (results[i].band === "bad" && !underLine(r) && a != null && a >= APPROVAL_BAR) count += 1;
  });
  return { voiced, count, sharePct: pct(count, voiced) };
}

export type BadAboveLine = { bad: number; count: number; sharePct: number | null };

/** Of every class shown Bad under `cfg`, how many were rated 4.55 or better. */
export function badAboveLine(rows: StudyRow[], cfg: ScoringConfig, results: ScoreResult[] = scoreUnder(rows, cfg)): BadAboveLine {
  let bad = 0;
  let count = 0;
  rows.forEach((r, i) => {
    if (results[i].band !== "bad") return;
    bad += 1;
    if (!underLine(r)) count += 1;
  });
  return { bad, count, sharePct: pct(count, bad) };
}

/** The three in-memory measures of the five-number table for one configuration, scored once. */
export function studyMeasures(rows: StudyRow[], cfg: ScoringConfig, opts: { minPairs?: number } = {}) {
  const results = scoreUnder(rows, cfg);
  const bands = emptyBands();
  let noBand = 0;
  let provisional = 0;
  for (const x of results) {
    if (x.band) bands[x.band] += 1;
    else noBand += 1;
    if (x.provisional) provisional += 1;
  }
  return {
    results,
    bands,
    noBand,
    provisional,
    comfort: falseComfort(rows, cfg, results),
    alarm: falseAlarm(rows, cfg, results),
    badAbove: badAboveLine(rows, cfg, results),
    risk: nextClassRisk(rows, cfg, { minPairs: opts.minPairs, results }),
  };
}
export type StudyMeasures = ReturnType<typeof studyMeasures>;

// ── drift: month by month ─────────────────────────────────────────────────────
export type MonthDrift = {
  month: string;
  label: string;
  n: number;
  avgRating: number | null;
  /** Share of classes rated under 4.55. */
  underLinePct: number | null;
  /** Share of classes with 5+ votes under the 80% bar. */
  underBarPct: number | null;
  avgAttended: number | null;
  /** Average share of the room that rated. */
  avgReach: number | null;
  avgScore: number | null;
  /** Share of banded classes shown Bad (the stored verdict). */
  badPct: number | null;
};

export function driftByMonth(rows: StudyRow[]): MonthDrift[] {
  const map = new Map<string, StudyRow[]>();
  for (const r of rows) {
    const k = r.class_date.slice(0, 7);
    map.set(k, [...(map.get(k) ?? []), r]);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, list]) => {
      const voiced = list.filter((r) => voicesOf(r) >= VOICES);
      const banded = list.filter((r) => r.band != null);
      return {
        month,
        label: monthLabel(month),
        n: list.length,
        avgRating: mean(list.map((r) => r.rating)),
        underLinePct: pct(list.filter(underLine).length, list.length),
        underBarPct: pct(voiced.filter(underBar).length, voiced.length),
        avgAttended: mean(nums(list.map((r) => r.attended))),
        avgReach: mean(nums(list.map((r) => r.participation_pct))),
        avgScore: mean(nums(list.map((r) => r.score))),
        badPct: pct(banded.filter((r) => r.band === "bad").length, banded.length),
      };
    });
}

// ── fairness: the same score for every kind of class ──────────────────────────
export type Slice = {
  key: string;
  label: string;
  n: number;
  avgScore: number | null;
  avgRating: number | null;
  avgAttended: number | null;
  /** Of banded classes (the stored verdict). */
  badPct: number | null;
  excellentPct: number | null;
};

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const weekdayOf = (iso: string) => WEEKDAYS[(new Date(iso + "T00:00:00Z").getUTCDay() + 6) % 7];

function sliceOf(key: string, label: string, list: StudyRow[]): Slice {
  const banded = list.filter((r) => r.band != null);
  return {
    key,
    label,
    n: list.length,
    avgScore: mean(nums(list.map((r) => r.score))),
    avgRating: mean(list.map((r) => r.rating)),
    avgAttended: mean(nums(list.map((r) => r.attended))),
    badPct: pct(banded.filter((r) => r.band === "bad").length, banded.length),
    excellentPct: pct(banded.filter((r) => r.band === "excellent").length, banded.length),
  };
}

function group(rows: StudyRow[], keyOf: (r: StudyRow) => string | null, order: string[], labelOf: (k: string) => string): Slice[] {
  const map = new Map<string, StudyRow[]>();
  for (const r of rows) {
    const k = keyOf(r);
    if (k == null) continue;
    map.set(k, [...(map.get(k) ?? []), r]);
  }
  const keys = [...map.keys()].sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || map.get(b)!.length - map.get(a)!.length;
  });
  return keys.map((k) => sliceOf(k, labelOf(k), map.get(k)!));
}

const KIND_LABEL: Record<string, string> = { "Live Class": "Live class", "Test Review": "Test review" };
const REGION_LABEL: Record<string, string> = { IND: "India", US: "US" };

/** Average score / rating / room size by live vs review, by region (only when the rows carry
 *  one) and by weekday. */
export function slices(rows: StudyRow[]): { kind: Slice[]; region: Slice[] | null; weekday: Slice[] } {
  const kind = group(rows, (r) => (r.session_kind === "Live Class" || r.session_kind === "Test Review" ? r.session_kind : "Other"), ["Live Class", "Test Review", "Other"], (k) => KIND_LABEL[k] ?? k);
  const hasRegion = rows.some((r) => r.region === "IND" || r.region === "US");
  const region = hasRegion ? group(rows, (r) => (r.region === "IND" || r.region === "US" ? r.region : null), ["IND", "US"], (k) => REGION_LABEL[k] ?? k) : null;
  const weekday = group(rows, (r) => weekdayOf(r.class_date), WEEKDAYS, (k) => k);
  return { kind, region, weekday };
}

// ── how many voices before a band is firm ─────────────────────────────────────
export const VOTE_BUCKETS = [
  { key: "0-2", label: "0–2 votes", lo: 0, hi: 2 },
  { key: "3-5", label: "3–5", lo: 3, hi: 5 },
  { key: "6-9", label: "6–9", lo: 6, hi: 9 },
  { key: "10+", label: "10+", lo: 10, hi: Infinity },
] as const;

export type VoteBucket = {
  key: string;
  label: string;
  n: number;
  counts: BandCounts & { none: number };
  provisional: number;
  provisionalPct: number | null;
  noBandPct: number | null;
};

export type TrustByVotes = {
  buckets: VoteBucket[];
  n: number;
  banded: number;
  provisional: number;
  /** Provisional bands as a share of every class. */
  provisionalPct: number | null;
  noBand: number;
  noBandPct: number | null;
};

/** The stored verdict by vote count: which bands a class with few voices can carry, and how
 *  many of those bands are provisional. */
export function trustByVotes(rows: StudyRow[]): TrustByVotes {
  const buckets: VoteBucket[] = VOTE_BUCKETS.map((b) => ({ key: b.key, label: b.label, n: 0, counts: { ...emptyBands(), none: 0 }, provisional: 0, provisionalPct: null, noBandPct: null }));
  let provisional = 0;
  let noBand = 0;
  for (const r of rows) {
    const v = voicesOf(r);
    const b = buckets[VOTE_BUCKETS.findIndex((x) => v >= x.lo && v <= x.hi)] ?? buckets[buckets.length - 1];
    b.n += 1;
    if (r.band) b.counts[r.band] += 1;
    else {
      b.counts.none += 1;
      noBand += 1;
    }
    if (r.provisional) {
      b.provisional += 1;
      provisional += 1;
    }
  }
  for (const b of buckets) {
    b.provisionalPct = pct(b.provisional, b.n);
    b.noBandPct = pct(b.counts.none, b.n);
  }
  return { buckets, n: rows.length, banded: rows.length - noBand, provisional, provisionalPct: pct(provisional, rows.length), noBand, noBandPct: pct(noBand, rows.length) };
}
