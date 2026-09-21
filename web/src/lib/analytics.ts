import "server-only";
import { cache } from "react";
import { createClient } from "@/lib/supabase/server";
import { approvalOf, fetchRatings, instructorKey, instructorName, latestRatedDate, type ClassRating } from "@/lib/ratings";
import { coursePriors, courseKey, scoreRow } from "@/lib/class-score";
import { getActiveConfig } from "@/lib/scoring";
import { bandOf, DEFAULT_CONFIG, type Action, type Band, type ComponentRow, type ScoringConfig } from "@/lib/sentiment";
import { hrefIn } from "@/lib/workspace-shared";
import { buildCurriculumMap, type CurriculumMap, type CurriculumOptions } from "@/lib/curriculum";

/** The drawer link for a class row: its course's classes page + `?class=`; unmapped rows fall
 *  back to the team queue, which opens the same drawer. */
export const drawerHref = (r: { id: string; course_slug: string | null }) =>
  r.course_slug ? `${hrefIn(r.course_slug, "/classes")}?class=${r.id}` : `${hrefIn("team", "/queue")}?class=${r.id}`;

/** Data helpers for the analytics pages (course workspaces + the team level).
 *
 *  Everything aggregates IN-PROCESS over `class_ratings` (`fetchRatings` selects `*`), so the
 *  pages work before and after the scoring / identity / cohort migrations land: stored scores
 *  win, rows the database has not scored yet are scored by the web mirror with the ACTIVE
 *  configuration (`scoreRow`), and cohorts / topics / identities use the resolved columns when
 *  present and the sheet's text otherwise. The rollup views (v_course_month_rollup,
 *  v_instructor_rollup, v_cohort_journey, v_topic_hotspots) can replace the aggregators here one
 *  by one without touching a page. ~350 rows a month, so a year is a few thousand rows. */

// ── types ─────────────────────────────────────────────────────────────────────
export type ScoredRating = ClassRating & {
  /** The Class Sentiment Score (stored, else mirrored) and its verdict. */
  score: number | null;
  band: Band | null;
  action: Action;
  provisional: boolean;
  scored_by: "db" | "mirror";
  /** The contract's one-sentence reason. */
  reason: string;
  /** The four inputs and what each earned — for the pill's popover. */
  breakdown: ComponentRow[];
  flags: string[];
};

export type BandCounts = { excellent: number; good: number; average: number; bad: number };

// ── small utilities ───────────────────────────────────────────────────────────
export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const today = () => iso(new Date());
export const addDays = (isoDate: string, n: number) => iso(new Date(+new Date(isoDate + "T00:00:00Z") + n * 86400000));
export const daysBetween = (a: string, b: string) => Math.round((+new Date(b) - +new Date(a)) / 86400000);
export const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
export function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
export const fmtScore = (v: number | null | undefined) => (v == null ? "—" : String(Math.round(v)));
export const fmtAvg = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
export const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
export const prettyDate = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });
export const prettyDateYear = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
export const prettyMonth = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, 1).toLocaleString("en-US", { month: "short" });
};
export const prettyMonthYear = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, 1).toLocaleString("en-US", { month: "short", year: "numeric" });
};
export const plural = (n: number, one: string, many = one + "s") => (n === 1 ? one : many);

/** Monday of the ISO week a date sits in. */
export function weekStart(isoDate: string): string {
  const d = new Date(isoDate + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return iso(d);
}

/** The equal-length window immediately before [from, to]. */
export function previousWindow(from: string, to: string) {
  const span = Math.max(1, daysBetween(from, to) + 1);
  return { from: addDays(from, -span), to: addDays(from, -1), span };
}

export function deltaOf(cur: number | null | undefined, prev: number | null | undefined): number | null {
  return cur == null || prev == null ? null : cur - prev;
}

// ── URL scope (the one filter bar) ────────────────────────────────────────────
export type RangePreset = "7d" | "30d" | "90d" | "month" | "custom";
export const RANGE_PRESETS: RangePreset[] = ["7d", "30d", "90d", "month", "custom"];

/** The date the presets count back from: today, or the last rated class when the sheet is
 *  behind (a "last 7 days" that ends after the data does is an empty page, not a filter). */
export function scopeAnchor(latest?: string | null): string {
  const t = today();
  return latest && /^\d{4}-\d{2}-\d{2}$/.test(latest) && latest < t ? latest : t;
}

export function rangeToDates(range: RangePreset, from?: string, to?: string, anchor?: string | null) {
  const t = scopeAnchor(anchor);
  switch (range) {
    case "7d":
      return { from: addDays(t, -7), to: t };
    case "30d":
      return { from: addDays(t, -30), to: t };
    case "90d":
      return { from: addDays(t, -90), to: t };
    case "month":
      return { from: `${t.slice(0, 7)}-01`, to: t };
    case "custom": {
      const f = from && /^\d{4}-\d{2}-\d{2}$/.test(from) ? from : addDays(t, -30);
      const tt = to && /^\d{4}-\d{2}-\d{2}$/.test(to) ? to : t;
      return f <= tt ? { from: f, to: tt } : { from: tt, to: f };
    }
  }
}

export type Scope = {
  range: RangePreset;
  from: string;
  to: string;
  /** Set when the presets end on the last rated class rather than today. */
  anchor?: string;
  cohort?: string;
  kind?: "live" | "review";
  instructor?: string;
  band?: Band;
};

export type SearchParams = Record<string, string | string[] | undefined>;
const BAND_SET = new Set<string>(["excellent", "good", "average", "bad"]);
export const one = (sp: SearchParams, k: string) => {
  const v = sp[k];
  return Array.isArray(v) ? v[0] : v;
};

export function readScope(sp: SearchParams, defaultRange: RangePreset = "90d", latest?: string | null): Scope {
  const range = (RANGE_PRESETS.includes(one(sp, "range") as RangePreset) ? one(sp, "range") : defaultRange) as RangePreset;
  const anchor = scopeAnchor(latest);
  const { from, to } = rangeToDates(range, one(sp, "from"), one(sp, "to"), anchor);
  const kind = one(sp, "kind");
  const band = one(sp, "band");
  return {
    range,
    from,
    to,
    anchor: anchor < today() ? anchor : undefined,
    cohort: one(sp, "cohort") || undefined,
    kind: kind === "live" || kind === "review" ? kind : undefined,
    instructor: one(sp, "instructor") || undefined,
    band: band && BAND_SET.has(band) ? (band as Band) : undefined,
  };
}

/** The scope with its presets anchored on the course's (or the team's) last rated class. */
export async function readScopeFor(sp: SearchParams, courseId?: string | null, defaultRange: RangePreset = "90d"): Promise<Scope> {
  return readScope(sp, defaultRange, await latestRatedDate(courseId ?? null));
}

/** Query string for the scope (only what differs from the defaults), plus extras. */
export function scopeQuery(s: Scope, defaultRange: RangePreset = "90d", extra?: Record<string, string | undefined>) {
  const p = new URLSearchParams();
  if (s.range !== defaultRange) p.set("range", s.range);
  if (s.range === "custom") {
    p.set("from", s.from);
    p.set("to", s.to);
  }
  if (s.cohort) p.set("cohort", s.cohort);
  if (s.kind) p.set("kind", s.kind);
  if (s.instructor) p.set("instructor", s.instructor);
  if (s.band) p.set("band", s.band);
  for (const [k, v] of Object.entries(extra ?? {})) if (v) p.set(k, v);
  const q = p.toString();
  return q ? `?${q}` : "";
}

/** Apply the scope's row filters (cohort · live/review · instructor · band). */
export function applyScope(rows: ScoredRating[], s: Scope, cohortNames?: Map<string, CohortRef>): ScoredRating[] {
  let out = rows;
  if (s.kind) out = out.filter((r) => (s.kind === "live" ? isLive(r) : isReview(r)));
  if (s.instructor) out = out.filter((r) => instructorKey(r) === s.instructor);
  if (s.band) out = out.filter((r) => r.band === s.band);
  if (s.cohort) out = out.filter((r) => cohortRefs(r, cohortNames).some((c) => c.key === s.cohort));
  return out;
}

export const isLive = (r: ClassRating) => r.session_kind === "Live Class";
export const isReview = (r: ClassRating) => r.session_kind === "Test Review";

// ── the scored feed ───────────────────────────────────────────────────────────
/** Score every row: the database's verdict wins; unscored rows go through the mirror with the
 *  active configuration and the course's priors (for the small-sample guard). */
export function scoreRows(rows: ClassRating[], cfg: ScoringConfig): ScoredRating[] {
  const priors = coursePriors(rows);
  return rows.map((r) => {
    const s = scoreRow(r, cfg, priors.get(courseKey(r)));
    return {
      ...r,
      score: s.score,
      band: s.band,
      action: s.action,
      provisional: s.provisional,
      scored_by: s.stored ? "db" : "mirror",
      reason: s.reason,
      breakdown: s.rows,
      flags: s.flags,
    };
  });
}

/** Every rated class in [from, to] (newest first), scored. */
export async function fetchScored(opts: { from: string; to: string; courseId?: string | null }): Promise<ScoredRating[]> {
  const [rows, active] = await Promise.all([fetchRatings(opts), getActiveConfig()]);
  return scoreRows(rows, active.config);
}

export { instructorKey, instructorName };

// ── scoring summaries ─────────────────────────────────────────────────────────
export const emptyCounts = (): BandCounts => ({ excellent: 0, good: 0, average: 0, bad: 0 });

export function bandCounts(rows: ScoredRating[]): BandCounts & { none: number } {
  const c = { ...emptyCounts(), none: 0 };
  for (const r of rows) {
    if (r.band) c[r.band] += 1;
    else c.none += 1;
  }
  return c;
}

export function avgScore(rows: ScoredRating[]): number | null {
  return mean(rows.map((r) => r.score).filter((v): v is number => v != null));
}

export function scoreSummary(rows: ScoredRating[]) {
  const counts = bandCounts(rows);
  const score = avgScore(rows);
  const scored = rows.length - counts.none;
  return {
    n: rows.length,
    scored,
    avgScore: score,
    band: score == null ? null : bandOf(Math.round(score)),
    counts,
    approval: approvalOf(rows),
    reach: mean(rows.map((r) => r.participation_pct).filter((v): v is number => v != null)),
    avgRating: mean(rows.map((r) => r.rating)),
    /** The typical room: learners attended per class. */
    avgAttended: mean(rows.map((r) => r.attended).filter((v): v is number => v != null)),
    /** Learners who rated, per class. */
    avgRated: mean(rows.map((r) => r.num_ratings).filter((v): v is number => v != null)),
    bad: counts.bad,
    average: counts.average,
    badShare: scored ? counts.bad / scored : null,
    lowShare: scored ? (counts.bad + counts.average) / scored : null,
    thin: counts.none,
    votes: rows.reduce((a, r) => a + (r.yes_votes ?? 0) + (r.no_votes ?? 0), 0),
  };
}
export type ScoreSummary = ReturnType<typeof scoreSummary>;

/** The effective analysis depth for a row: a PM override, else the band's action. */
export const effectiveAction = (r: ScoredRating): Action => r.decision_override ?? r.action;

/** Open queue = an analysis is due (video / transcript) and nobody has closed it. */
export function isOpenQueue(r: ScoredRating): boolean {
  const a = effectiveAction(r);
  const open = r.review_status === "new" || r.review_status === "notified" || r.review_status === "confirmed";
  return open && (a === "video" || a === "transcript");
}

export function queueCounts(rows: ScoredRating[]) {
  let video = 0;
  let transcript = 0;
  let oldest: string | null = null;
  for (const r of rows) {
    if (!isOpenQueue(r)) continue;
    if (effectiveAction(r) === "video") video += 1;
    else transcript += 1;
    if (!oldest || r.class_date < oldest) oldest = r.class_date;
  }
  return { video, transcript, total: video + transcript, oldest };
}

// ── time buckets ──────────────────────────────────────────────────────────────
export type WeekBucket = ScoreSummary & { week: string; label: string; rows: ScoredRating[] };

/** ISO weeks covering [from, to] (empty weeks included so lines keep their spacing). */
export function byWeek(rows: ScoredRating[], from: string, to: string): WeekBucket[] {
  const map = new Map<string, ScoredRating[]>();
  for (const r of rows) {
    const k = weekStart(r.class_date);
    map.set(k, [...(map.get(k) ?? []), r]);
  }
  const out: WeekBucket[] = [];
  for (let w = weekStart(from); w <= to; w = addDays(w, 7)) {
    const list = map.get(w) ?? [];
    out.push({ week: w, label: prettyDate(w), rows: list, ...scoreSummary(list) });
  }
  return out;
}

export type MonthBucket = ScoreSummary & { month: string; label: string; rows: ScoredRating[] };

export function byMonth(rows: ScoredRating[]): MonthBucket[] {
  const map = new Map<string, ScoredRating[]>();
  for (const r of rows) {
    const k = r.class_date.slice(0, 7);
    map.set(k, [...(map.get(k) ?? []), r]);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, list]) => ({ month, label: prettyMonth(month), rows: list, ...scoreSummary(list) }));
}

/** Per-day buckets (the calendar heatmap). */
export function byDay(rows: ScoredRating[]) {
  const map = new Map<string, ScoredRating[]>();
  for (const r of rows) map.set(r.class_date, [...(map.get(r.class_date) ?? []), r]);
  return [...map.entries()].map(([date, list]) => ({ date, value: avgScore(list), n: list.length }));
}

// ── courses ───────────────────────────────────────────────────────────────────
export type CourseAgg = ScoreSummary & { key: string; courseId: string | null; name: string; slug: string | null; rows: ScoredRating[] };

export function byCourse(rows: ScoredRating[]): CourseAgg[] {
  const map = new Map<string, { key: string; courseId: string | null; name: string; slug: string | null; rows: ScoredRating[] }>();
  for (const r of rows) {
    const key = courseKey(r);
    if (!map.has(key)) map.set(key, { key, courseId: r.course_id, name: r.course_name ?? r.course_label, slug: r.course_slug, rows: [] });
    map.get(key)!.rows.push(r);
  }
  return [...map.values()].map((c) => ({ ...c, ...scoreSummary(c.rows) }));
}

// ── instructors ───────────────────────────────────────────────────────────────
/** Read a portfolio id from the URL: a uuid, or `name:<raw>` (possibly still percent-encoded). */
export function parseInstructorId(id: string): { instructorId: string | null; name: string | null } {
  let v = id;
  try {
    v = decodeURIComponent(id);
  } catch {
    /* already decoded */
  }
  if (v.startsWith("name:")) return { instructorId: null, name: v.slice(5).trim() };
  return { instructorId: v, name: null };
}

export function rowsForInstructor(rows: ScoredRating[], id: { instructorId: string | null; name: string | null }) {
  if (id.instructorId) return rows.filter((r) => r.instructor_id === id.instructorId);
  const name = (id.name ?? "").toLowerCase();
  return rows.filter((r) => instructorName(r).toLowerCase() === name || r.instructor.trim().toLowerCase() === name);
}

export type InstructorAgg = ScoreSummary & {
  key: string;
  id: string | null;
  name: string;
  aliases: string[];
  courses: { id: string | null; name: string; slug: string | null }[];
  rows: ScoredRating[];
  lastClassDate: string;
  firstClassDate: string;
};

export function byInstructor(rows: ScoredRating[]): InstructorAgg[] {
  const map = new Map<string, ScoredRating[]>();
  for (const r of rows) {
    const k = instructorKey(r);
    map.set(k, [...(map.get(k) ?? []), r]);
  }
  return [...map.entries()].map(([key, list]) => {
    const name = instructorName(list[0]);
    const aliases = [...new Set(list.map((r) => r.instructor.trim()).filter((s) => s && s !== name))];
    const courses = new Map<string, { id: string | null; name: string; slug: string | null }>();
    for (const r of list) courses.set(courseKey(r), { id: r.course_id, name: r.course_name ?? r.course_label, slug: r.course_slug });
    const dates = list.map((r) => r.class_date).sort();
    return {
      key,
      id: list[0].instructor_id,
      name,
      aliases,
      courses: [...courses.values()],
      rows: list,
      lastClassDate: dates[dates.length - 1],
      firstClassDate: dates[0],
      ...scoreSummary(list),
    };
  });
}

/** The four boxes of the rating × approval plane, per class. */
export type Quadrant = "fine" | "polite" | "hard" | "fails";
export function quadrantOf(r: ScoredRating): Quadrant | null {
  if (r.approval_pct == null) return null;
  const lowRating = r.rating < 4.55;
  const under = r.approval_pct < 80;
  return !lowRating && !under ? "fine" : !lowRating && under ? "polite" : lowRating && !under ? "hard" : "fails";
}
export const QUADRANT_META: Record<Quadrant, { label: string; note: string }> = {
  fine: { label: "Fine on both", note: "Rated 4.55+ and 80%+ would have the instructor back." },
  polite: { label: "Polite rating", note: "Rated fine, yet the room would rather have someone else — an instructor question." },
  hard: { label: "Hard class, good teacher", note: "Rated low, instructor approved — start with the content, not the person." },
  fails: { label: "Fails both", note: "Rated low and the room would rather have someone else." },
};

// ── cohorts ───────────────────────────────────────────────────────────────────
export type CohortRef = {
  key: string;
  id: string | null;
  name: string;
  region: string | null;
  start: string | null;
  audience: string | null;
  cohortNo: number | null;
};

const JUNK = /placeholder|template|deprecated|\bdnu\b|\btest\b|dummy/i;
const MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec";
const START_RE = new RegExp(`((?:early|mid|late|end)[-\\s]?)?(${MONTHS})[\\s'-]*(\\d{4})`, "i");

const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

/** Parse the sheet's cohort text ("Applied Agentic AI - 2nd Mid-March 2026 : Cohort 2, India …")
 *  into one reference per cohort; junk labels are dropped. */
export function parseCohortText(text: string | null | undefined): CohortRef[] {
  if (!text) return [];
  const parts = text
    .split(/\s*(?:,|;|\||\/|\s&\s|\sand\s|\n)\s*/i)
    .map((s) => s.trim())
    .filter((s) => s && !JUNK.test(s));
  const out: CohortRef[] = [];
  for (const p of parts) {
    const region = /india|\bind\b/i.test(p) ? "IND" : /\bus\b|usa|united states/i.test(p) ? "US" : null;
    const m = START_RE.exec(p);
    const start = m ? `${m[1] ? m[1].replace(/[-\s]/g, "") + " " : ""}${m[2][0].toUpperCase()}${m[2].slice(1, 3).toLowerCase()} ${m[3]}` : null;
    const cm = /cohort\s*#?\s*(\d+)/i.exec(p);
    out.push({ key: `key:${slugify(p)}`, id: null, name: p, region, start, audience: region, cohortNo: cm ? Number(cm[1]) : null });
  }
  return out;
}

type CohortRow = {
  id: string;
  name: string;
  region?: string | null;
  start_month?: string | null;
  start_part?: string | null;
  audience?: string | null;
  cohort_no?: number | null;
  start_date?: string | null;
};

/** The course's cohort rows (select * — the enrichment columns may not exist yet). */
export const loadCohorts = cache(async (courseId: string | null): Promise<Map<string, CohortRef>> => {
  const supabase = await createClient();
  let q = supabase.from("cohorts").select("*");
  if (courseId) q = q.eq("course_id", courseId);
  const { data, error } = await q;
  const map = new Map<string, CohortRef>();
  if (error) return map;
  for (const c of (data ?? []) as CohortRow[]) {
    const startMonth = c.start_month ?? c.start_date ?? null;
    map.set(c.id, {
      key: c.id,
      id: c.id,
      name: c.name,
      region: c.region ?? null,
      start: startMonth ? `${c.start_part ? c.start_part + " " : ""}${prettyMonthYear(startMonth.slice(0, 7))}` : null,
      audience: c.audience ?? c.region ?? null,
      cohortNo: c.cohort_no ?? null,
    });
  }
  return map;
});

/** A class's cohorts: by id when resolved, else parsed from the text. */
export function cohortRefs(r: ScoredRating, names?: Map<string, CohortRef>): CohortRef[] {
  const ids = r.cohort_ids?.length ? r.cohort_ids : r.cohort_id ? [r.cohort_id] : [];
  if (ids.length) {
    return ids.map(
      (id) => names?.get(id) ?? { key: id, id, name: `Cohort ${id.slice(0, 6)}`, region: null, start: null, audience: null, cohortNo: null },
    );
  }
  return parseCohortText(r.cohort_text);
}

/** Read a cohort id from the URL: a uuid or `key:<slug>`. */
export function parseCohortId(id: string): string {
  try {
    return decodeURIComponent(id);
  } catch {
    return id;
  }
}

export type CohortWeek = {
  week: number;
  live: number | null;
  review: number | null;
  score: number | null;
  reach: number | null;
  n: number;
  topics: string[];
  instructors: string[];
  rows: ScoredRating[];
};

export type CohortAgg = ScoreSummary & {
  ref: CohortRef;
  rows: ScoredRating[];
  firstDate: string;
  lastDate: string;
  /** The cohort's current week (1-based) counted from its first rated class. */
  weekNow: number;
  weeks: CohortWeek[];
};

export const COHORT_WEEKS = 14;

export function cohortWeekOf(r: ScoredRating, firstDate: string): number {
  if (r.week_no != null && r.week_no > 0) return r.week_no;
  return Math.floor(daysBetween(firstDate, r.class_date) / 7) + 1;
}

export function cohortJourney(rows: ScoredRating[], firstDate: string, maxWeeks = COHORT_WEEKS): CohortWeek[] {
  const byW = new Map<number, ScoredRating[]>();
  let top = 0;
  for (const r of rows) {
    const w = cohortWeekOf(r, firstDate);
    top = Math.max(top, w);
    byW.set(w, [...(byW.get(w) ?? []), r]);
  }
  const weeks: CohortWeek[] = [];
  for (let w = 1; w <= Math.max(maxWeeks, Math.min(top, 26)); w++) {
    const list = byW.get(w) ?? [];
    weeks.push({
      week: w,
      live: avgScore(list.filter(isLive)),
      review: avgScore(list.filter(isReview)),
      score: avgScore(list),
      reach: mean(list.map((r) => r.participation_pct).filter((v): v is number => v != null)),
      n: list.length,
      topics: [...new Set(list.map((r) => r.topic.trim()).filter((t) => t && !GENERIC.has(t.toLowerCase())))],
      instructors: [...new Set(list.map(instructorName))],
      rows: list,
    });
  }
  return weeks;
}

export function byCohort(rows: ScoredRating[], names?: Map<string, CohortRef>, asOf = today()): CohortAgg[] {
  const map = new Map<string, { ref: CohortRef; rows: ScoredRating[] }>();
  for (const r of rows) {
    for (const ref of cohortRefs(r, names)) {
      if (!map.has(ref.key)) map.set(ref.key, { ref, rows: [] });
      map.get(ref.key)!.rows.push(r);
    }
  }
  return [...map.values()].map((c) => {
    const dates = c.rows.map((r) => r.class_date).sort();
    const firstDate = dates[0];
    const lastDate = dates[dates.length - 1];
    return {
      ref: c.ref,
      rows: c.rows,
      firstDate,
      lastDate,
      weekNow: Math.min(99, Math.floor(daysBetween(firstDate, asOf) / 7) + 1),
      weeks: cohortJourney(c.rows, firstDate),
      ...scoreSummary(c.rows),
    };
  });
}

/** Median score per week across a set of cohorts (the grey reference line). */
export function medianJourney(cohorts: CohortAgg[], weeks = COHORT_WEEKS): (number | null)[] {
  return Array.from({ length: weeks }, (_, i) => median(cohorts.map((c) => c.weeks[i]?.score).filter((v): v is number => v != null)));
}

/** First rated class per cohort key — the anchor cohort weeks count from. */
export function cohortFirstDates(rows: ScoredRating[], names?: Map<string, CohortRef>): Map<string, string> {
  const map = new Map<string, string>();
  for (const r of rows) {
    for (const ref of cohortRefs(r, names)) {
      const cur = map.get(ref.key);
      if (!cur || r.class_date < cur) map.set(ref.key, r.class_date);
    }
  }
  return map;
}

// ── topics / modules ──────────────────────────────────────────────────────────
const GENERIC = new Set(["", "live class", "test review session", "test review", "workshop", "session", "live", "review"]);
export const hasRealTopic = (r: ScoredRating) => !GENERIC.has(r.topic.trim().toLowerCase());
export const topicKey = (r: ScoredRating) => r.topic_id ?? `name:${r.topic.trim()}`;

export function parseTopicId(id: string): { topicId: string | null; name: string | null } {
  let v = id;
  try {
    v = decodeURIComponent(id);
  } catch {
    /* already decoded */
  }
  if (v.startsWith("name:")) return { topicId: null, name: v.slice(5).trim() };
  return { topicId: v, name: null };
}

export function rowsForTopic(rows: ScoredRating[], id: { topicId: string | null; name: string | null }) {
  if (id.topicId) return rows.filter((r) => r.topic_id === id.topicId);
  const name = (id.name ?? "").toLowerCase();
  return rows.filter((r) => r.topic.trim().toLowerCase() === name);
}

export type TopicAgg = ScoreSummary & {
  key: string;
  id: string | null;
  name: string;
  rows: ScoredRating[];
  instructors: InstructorAgg[];
  /** "content" = low across ≥ 2 instructors · "delivery" = low for exactly one of several. */
  tag: "content" | "delivery" | null;
  bestSme: InstructorAgg | null;
  worstSme: InstructorAgg | null;
  /** Median cohort week the module is taught in (curriculum position); null when unknown. */
  order: number | null;
};

const LOW = DEFAULT_CONFIG.bands.good; // below Good = a class that needed a look

export function byTopic(rows: ScoredRating[], firstDates?: Map<string, string>): TopicAgg[] {
  const map = new Map<string, ScoredRating[]>();
  for (const r of rows.filter(hasRealTopic)) {
    const k = topicKey(r);
    map.set(k, [...(map.get(k) ?? []), r]);
  }
  return [...map.entries()].map(([key, list]) => {
    const instructors = byInstructor(list).sort((a, b) => (b.avgScore ?? 0) - (a.avgScore ?? 0));
    const seasoned = instructors.filter((i) => i.n >= 2);
    const low = seasoned.filter((i) => (i.avgScore ?? 100) < LOW);
    const tag = low.length >= 2 ? "content" : low.length === 1 && seasoned.length >= 2 ? "delivery" : null;
    const contenders = instructors.filter((i) => i.n >= 2 && i.avgScore != null);
    const weeks = list
      .map((r) => {
        if (r.week_no != null && r.week_no > 0) return r.week_no;
        const refs = cohortRefs(r);
        const first = refs.length ? firstDates?.get(refs[0].key) : undefined;
        return first ? cohortWeekOf(r, first) : null;
      })
      .filter((v): v is number => v != null);
    return {
      key,
      id: list[0].topic_id,
      name: list[0].topic.trim(),
      rows: list,
      instructors,
      tag,
      bestSme: contenders.length >= 2 ? contenders[0] : null,
      worstSme: contenders.length >= 2 ? contenders[contenders.length - 1] : null,
      order: median(weeks),
      ...scoreSummary(list),
    };
  });
}

/** Curriculum order: by median cohort week, then by first appearance. */
export function inCurriculumOrder(topics: TopicAgg[]): TopicAgg[] {
  const first = (t: TopicAgg) => t.rows.map((r) => r.class_date).sort()[0] ?? "";
  return [...topics].sort((a, b) => (a.order ?? 99) - (b.order ?? 99) || first(a).localeCompare(first(b)));
}

// ── movers ────────────────────────────────────────────────────────────────────
export type Mover = {
  key: string;
  label: string;
  sub?: string;
  href?: string;
  before: number | null;
  after: number | null;
  delta: number;
  nBefore: number;
  nAfter: number;
};

/** Biggest average-score changes between two row sets, for anything with ≥ min classes in both. */
export function movers(
  before: ScoredRating[],
  after: ScoredRating[],
  keyOf: (r: ScoredRating) => string,
  labelOf: (r: ScoredRating) => string,
  min = 3,
  href?: (key: string, sample: ScoredRating) => string | undefined,
): Mover[] {
  const group = (rows: ScoredRating[]) => {
    const m = new Map<string, ScoredRating[]>();
    for (const r of rows) {
      const k = keyOf(r);
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return m;
  };
  const a = group(before);
  const b = group(after);
  const out: Mover[] = [];
  for (const [key, rowsB] of b) {
    const rowsA = a.get(key);
    if (!rowsA || rowsA.length < min || rowsB.length < min) continue;
    const sa = avgScore(rowsA);
    const sb = avgScore(rowsB);
    if (sa == null || sb == null) continue;
    out.push({ key, label: labelOf(rowsB[0]), href: href?.(key, rowsB[0]), before: sa, after: sb, delta: sb - sa, nBefore: rowsA.length, nAfter: rowsB.length });
  }
  return out.sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta));
}

// ── the reason, in a PM's words ───────────────────────────────────────────────
export function classReason(r: ScoredRating): string {
  if (r.band == null) {
    return r.score == null && r.flags.includes("no_rating") ? "No rating recorded yet." : `Only ${r.num_ratings ?? 0} rated it — too few voices for a band yet.`;
  }
  const bits: string[] = [];
  const low = r.rating < 4.55;
  const under = r.approval_pct != null && r.approval_pct < 80;
  const rated = r.rating.toFixed(2);
  if (low && under) bits.push(`Rated ${rated} and only ${Math.round(r.approval_pct!)}% would have the instructor back`);
  else if (low) bits.push(r.approval_pct != null ? `Rated ${rated}, though ${Math.round(r.approval_pct)}% would have the instructor back` : `Rated ${rated} with no approval answer recorded`);
  else if (under) bits.push(`Rated ${rated} but only ${Math.round(r.approval_pct!)}% would have the instructor back`);
  else bits.push(r.approval_pct != null ? `Rated ${rated} and ${Math.round(r.approval_pct)}% would have the instructor back` : `Rated ${rated} with no approval answer recorded`);
  if (r.num_ratings != null && r.num_ratings < 10) bits.push(`${r.num_ratings} rated it`);
  if (r.participation_pct != null && r.participation_pct < 40) bits.push(`${Math.round(r.participation_pct)}% of the room`);
  const a = effectiveAction(r);
  const tail = a === "video" ? "video" : a === "transcript" ? "transcript" : a === "watch" ? "watch" : "no analysis";
  return `${bits.join(" · ")} → ${tail}${r.provisional ? " (provisional)" : ""}.`;
}

// ── the feedback loop (classes → analyses → feedback) ─────────────────────────
export type LoopClass = {
  id: string;
  topic: string;
  class_date: string;
  created_at: string;
  status: string;
  course_id: string | null;
  instructor_id: string | null;
  instructor_name: string | null;
  analysed_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  cost_usd: number;
};

type LoopRow = {
  id: string;
  topic: string;
  class_date: string;
  created_at: string;
  status: string;
  course_id: string | null;
  instructor_id: string | null;
  instructors: { name?: string } | { name?: string }[] | null;
  analyses: { created_at?: string | null; cost_usd?: number | string | null }[] | null;
  feedback: { approved_at?: string | null; sent_at?: string | null; status?: string | null }[] | null;
};

/** Every analysed class with its loop timestamps (the AI engine's tables). */
export const loadLoop = cache(async (courseId?: string | null): Promise<LoopClass[]> => {
  const supabase = await createClient();
  // Paged, not capped: a `.limit(2000)` used to under-count the funnel silently once the archive
  // passed it. A query error is an error, not an empty loop.
  const PAGE = 1000;
  const rows: LoopRow[] = [];
  for (let page = 0; page < 50; page++) {
    let q = supabase
      .from("classes")
      .select("id, topic, class_date, created_at, status, course_id, instructor_id, instructors(name), analyses(created_at, cost_usd), feedback(approved_at, sent_at, status)")
      .order("class_date", { ascending: false })
      .order("id", { ascending: false })
      .range(page * PAGE, page * PAGE + PAGE - 1);
    if (courseId) q = q.eq("course_id", courseId);
    const { data, error } = await q;
    if (error) throw new Error("Could not load the analysed classes: " + error.message);
    const batch = (data ?? []) as unknown as LoopRow[];
    rows.push(...batch);
    if (batch.length < PAGE) break;
  }
  return rows.map((c) => {
    const inst = Array.isArray(c.instructors) ? c.instructors[0] : c.instructors;
    const analyses = [...(c.analyses ?? [])].sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
    const fb = [...(c.feedback ?? [])].sort((a, b) => (a.approved_at ?? "").localeCompare(b.approved_at ?? ""));
    const last = fb[fb.length - 1];
    return {
      id: c.id,
      topic: c.topic,
      class_date: c.class_date,
      created_at: c.created_at,
      status: c.status,
      course_id: c.course_id,
      instructor_id: c.instructor_id,
      instructor_name: inst?.name ?? null,
      analysed_at: analyses[0]?.created_at ?? null,
      approved_at: last?.approved_at ?? null,
      sent_at: last?.status === "sent" ? (last.sent_at ?? null) : null,
      cost_usd: analyses.reduce((a, x) => a + Number(x.cost_usd ?? 0), 0),
    };
  });
});

export type Funnel = {
  flagged: number;
  confirmed: number;
  analysed: number;
  approved: number;
  sent: number;
  /** Median days between steps (null when no pair exists). */
  daysToAnalysis: number | null;
  daysToApproval: number | null;
  daysToSend: number | null;
  cost: number;
};

/** flagged → confirmed → analysed → approved → sent, with the median days per step. */
export function loopFunnel(rows: ScoredRating[], loop: LoopClass[]): Funnel {
  const byClass = new Map(loop.map((c) => [c.id, c]));
  const flaggedRows = rows.filter((r) => {
    const a = effectiveAction(r);
    return a === "video" || a === "transcript" || r.escalated;
  });
  let confirmed = 0;
  let analysed = 0;
  let approved = 0;
  let sent = 0;
  let cost = 0;
  const dA: number[] = [];
  const dP: number[] = [];
  const dS: number[] = [];
  const dayDiff = (a: string | null, b: string | null) => (a && b ? (+new Date(b) - +new Date(a)) / 86400000 : null);
  for (const r of flaggedRows) {
    if (r.review_status === "confirmed" || r.review_status === "analysis_started" || r.class_id) confirmed += 1;
    const c = r.class_id ? byClass.get(r.class_id) : undefined;
    if (!c) continue;
    if (c.analysed_at) {
      analysed += 1;
      cost += c.cost_usd;
      const d = dayDiff(r.synced_at, c.analysed_at);
      if (d != null && d >= 0) dA.push(d);
    }
    if (c.approved_at) {
      approved += 1;
      const d = dayDiff(c.analysed_at, c.approved_at);
      if (d != null && d >= 0) dP.push(d);
    }
    if (c.sent_at) {
      sent += 1;
      const d = dayDiff(c.approved_at, c.sent_at);
      if (d != null && d >= 0) dS.push(d);
    }
  }
  return { flagged: flaggedRows.length, confirmed, analysed, approved, sent, daysToAnalysis: median(dA), daysToApproval: median(dP), daysToSend: median(dS), cost };
}

/** Outcome per class-rating id: was it analysed, approved, sent? */
export function outcomesFor(rows: ScoredRating[], loop: LoopClass[]) {
  const byClass = new Map(loop.map((c) => [c.id, c]));
  const out = new Map<string, { analysed: boolean; approved: boolean; sent: boolean; classId: string | null }>();
  for (const r of rows) {
    const c = r.class_id ? byClass.get(r.class_id) : undefined;
    out.set(r.id, { analysed: !!c?.analysed_at, approved: !!c?.approved_at, sent: !!c?.sent_at, classId: r.class_id });
  }
  return out;
}

// ── identity, housekeeping (tables that may not exist yet — all tolerant) ─────
export const loadAliases = cache(async (instructorId: string | null): Promise<string[]> => {
  if (!instructorId) return [];
  const supabase = await createClient();
  const { data, error } = await supabase.from("instructor_aliases").select("alias").eq("instructor_id", instructorId);
  if (error) return [];
  return [...new Set((data ?? []).map((a) => String((a as { alias?: string }).alias ?? "")).filter(Boolean))];
});

export const loadInstructorNames = cache(async (): Promise<Map<string, string>> => {
  const supabase = await createClient();
  const { data } = await supabase.from("instructors").select("id, name");
  return new Map(((data ?? []) as { id: string; name: string }[]).map((i) => [i.id, i.name]));
});

export const loadPendingSuggestions = cache(async (): Promise<number | null> => {
  const supabase = await createClient();
  const { count, error } = await supabase.from("instructor_match_suggestions").select("*", { count: "exact", head: true }).eq("status", "pending");
  if (error) return null;
  return count ?? 0;
});

export type SyncInfo = { finishedAt: string | null; status: string | null; unmapped: string[] };

export const loadSync = cache(async (): Promise<SyncInfo> => {
  const supabase = await createClient();
  const { data } = await supabase
    .from("sync_runs")
    .select("status, unmapped_labels, started_at, finished_at")
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return {
    finishedAt: (data?.finished_at as string | null) ?? (data?.started_at as string | null) ?? null,
    status: (data?.status as string | null) ?? null,
    unmapped: ((data?.unmapped_labels as string[] | null) ?? []).filter(Boolean),
  };
});

/** "12 min ago" / "3h ago" / "2d ago" from an ISO timestamp. */
export function ago(ts: string | null, now = Date.now()): string | null {
  if (!ts) return null;
  const m = Math.max(0, Math.round((now - +new Date(ts)) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

// ── the AI-feedback history for one instructor ────────────────────────────────
export type FeedbackEvent = { classId: string; date: string; topic: string; sentAt: string; approvedAt: string | null };

/** Classes of this instructor whose AI feedback was SENT (feedback.sent_at), by class date. */
export function feedbackEventsFor(loop: LoopClass[], id: { instructorId: string | null; name: string | null }, aliases: string[] = []): FeedbackEvent[] {
  const names = new Set([id.name, ...aliases].filter((s): s is string => !!s).map((s) => s.toLowerCase()));
  return loop
    .filter((c) => c.sent_at && (id.instructorId ? c.instructor_id === id.instructorId : !!c.instructor_name && names.has(c.instructor_name.toLowerCase())))
    .map((c) => ({ classId: c.id, date: c.class_date, topic: c.topic, sentAt: c.sent_at!, approvedAt: c.approved_at }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** Average of the k classes before vs after a date (the loop's before → after). */
export function beforeAfter(rows: ScoredRating[], date: string, k = 3) {
  const sorted = [...rows].sort((a, b) => a.class_date.localeCompare(b.class_date));
  const before = sorted.filter((r) => r.class_date <= date).slice(-k);
  const after = sorted.filter((r) => r.class_date > date).slice(0, k);
  return { before: avgScore(before), after: avgScore(after), nBefore: before.length, nAfter: after.length };
}

// ── reports ───────────────────────────────────────────────────────────────────
export type ReportPeriod = "week" | "month" | "custom";

export { reportPeriod, type ReportWindow } from "@/lib/report-period";

// ── the curriculum map (pure core in ./curriculum.ts) ─────────────────────────
export {
  ALL_TRACKS,
  LIFT,
  RATING_LINE,
  attendanceJourney,
  fmtSigned,
  initialsOf,
  instructorModuleFit,
  kindMix,
  moduleFixers,
  ratingBand,
  ratioBand,
  reachBand,
  shortCohortName,
  shortModuleName,
  trackLabel,
  trackOf,
  verdictOf,
  type CurriculumCell,
  type CurriculumCohort,
  type CurriculumLinks,
  type CurriculumMap,
  type CurriculumModule,
  type FixerRow,
  type Insight,
  type InsightKind,
  type Journey,
  type JourneyAxis,
  type ModuleFit,
  type TrackOption,
  type Verdict,
} from "@/lib/curriculum";

/** Cohorts with at least one class inside [from, to] — the scope decides WHICH cohorts a map
 *  shows; the map itself is built from a wider window so a cohort's earlier modules are there. */
export function activeCohortKeys(rows: ScoredRating[], from: string, to: string, names?: Map<string, CohortRef>): Set<string> {
  const keys = new Set<string>();
  for (const r of rows) {
    if (r.class_date < from || r.class_date > to) continue;
    for (const ref of cohortRefs(r, names)) keys.add(ref.key);
  }
  return keys;
}

/** How far back the map's rows reach: a year before the period's end, or the period's own
 *  start when it is older than that. */
export function mapWindowStart(from: string, to: string): string {
  const back = addDays(to, -365);
  return from < back ? from : back;
}

/** Every cohort of the course against every module, in curriculum order, with the sentences
 *  a PM reads first. `rowsAll` should be the wide window (`mapWindowStart`); `cohortKeys`
 *  (usually `activeCohortKeys` of the scope) picks the cohorts, `track` the audience. */
export function curriculumMap(rowsAll: ScoredRating[], cohortNames?: Map<string, CohortRef>, opts: Omit<CurriculumOptions, "refsOf"> = {}): CurriculumMap {
  return buildCurriculumMap(rowsAll, { refsOf: (r) => cohortRefs(r, cohortNames), ...opts });
}
