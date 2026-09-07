import { bandOf, type Band } from "./sentiment.ts";

/** The curriculum map — every cohort of a course against every module, in curriculum order —
 *  and the plain sentences it produces ("attendance falls most at…", "the rating dips most at…",
 *  "X teaches Y above its average"). This module is PURE: no Next, no React, no database, so it
 *  runs in the browser (the map's tint helpers), on the server (`analytics.ts` re-exports it and
 *  hands it the real cohort resolver) and under `node --test` (curriculum.test.ts) alike.
 *
 *  Rules of the map:
 *  - a module is a real topic with at least `minClasses` classes across the rows given;
 *  - a cohort's cell on a module merges every session it had on it (live + review → one cell:
 *    rating = mean, attended = the fuller room, the live class opens first);
 *  - modules sit in the median cohort week they are taught (week_no, else counted from the
 *    cohort's first class), ties by first appearance — the same order `byTopic` uses;
 *  - a drop is measured per cohort against THAT cohort's previous module, so tracks that take
 *    different modules, modules taught out of order and cohorts still running all read right;
 *  - a rating of 0 is "not rated", never a zero. */

// ── input shape (a ScoredRating satisfies it; the tests build it directly) ────
export type CurriculumRow = {
  id: string;
  topic: string;
  topic_id: string | null;
  class_date: string;
  session_kind: string;
  rating: number;
  num_ratings: number | null;
  attended: number | null;
  participation_pct: number | null;
  week_no: number | null;
  instructor: string;
  instructor_id: string | null;
  instructor_canonical: string | null;
  score: number | null;
  band: Band | null;
};

export type CohortRefLike = {
  key: string;
  name: string;
  start: string | null;
  region: string | null;
  audience: string | null;
  cohortNo?: number | null;
};

export type BandCounts = { excellent: number; good: number; average: number; bad: number };

// ── constants ─────────────────────────────────────────────────────────────────
/** The rating line the team agreed: under it a class "needed a look". */
export const RATING_LINE = 4.55;
/** How far above (or under) a module's average an instructor must sit to "lift" (or "struggle"). */
export const LIFT = 0.15;
/** Weeks a cohort journey is drawn over, and the most it can stretch to. */
export const JOURNEY_WEEKS = 14;
export const MAX_WEEKS = 26;
/** A cohort with a class in the last three weeks is still running. */
export const ACTIVE_DAYS = 21;
export const ALL_TRACKS = "all";

// ── small pure helpers ────────────────────────────────────────────────────────
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
const nums = <T>(xs: T[], f: (x: T) => number | null | undefined) => xs.map(f).filter((v): v is number => v != null && Number.isFinite(v));
const ratingsOf = (rows: CurriculumRow[]) => nums(rows, (r) => (r.rating > 0 ? r.rating : null));
const iso = (d: Date) => d.toISOString().slice(0, 10);
const today = () => iso(new Date());
export const daysBetween = (a: string, b: string) => Math.round((+new Date(b + "T00:00:00Z") - +new Date(a + "T00:00:00Z")) / 86400000);
function push<K, V>(m: Map<K, V[]>, k: K, v: V) {
  const list = m.get(k);
  if (list) list.push(v);
  else m.set(k, [v]);
}
const uniq = <T>(xs: T[]) => [...new Set(xs)];

/** One key per real person: the resolved id when the sync has one, else the recorded name. */
export const instructorKeyOf = (r: Pick<CurriculumRow, "instructor_id" | "instructor" | "instructor_canonical">) =>
  r.instructor_id ?? `name:${r.instructor_canonical || r.instructor || "(unknown)"}`;
export const instructorNameOf = (r: Pick<CurriculumRow, "instructor" | "instructor_canonical">) => r.instructor_canonical || r.instructor || "(unknown)";

const GENERIC = new Set(["", "live class", "test review session", "test review", "workshop", "session", "live", "review"]);
/** A row that names a module (not the sheet's generic "Live Class" / "Test Review" labels). */
export const isModuleRow = (r: Pick<CurriculumRow, "topic">) => !GENERIC.has(r.topic.trim().toLowerCase());
export const moduleKeyOf = (r: Pick<CurriculumRow, "topic" | "topic_id">) => r.topic_id ?? `name:${r.topic.trim()}`;

const kindRank = (r: Pick<CurriculumRow, "session_kind">) => (r.session_kind === "Live Class" ? 0 : r.session_kind === "Test Review" ? 1 : 2);
export const kindShort = (kind: string) => (kind === "Live Class" ? "Live" : kind === "Test Review" ? "Review" : kind || "—");
/** "Live + review" / "Live" / "Review" — the kind mix of a cell. */
export const kindMix = (kinds: string[]) => kinds.map(kindShort).join(" + ");

function bandCounts(rows: { band: Band | null }[]): BandCounts {
  const c: BandCounts = { excellent: 0, good: 0, average: 0, bad: 0 };
  for (const r of rows) if (r.band) c[r.band] += 1;
  return c;
}

// ── the bands a raw number would earn (the map's tints) ───────────────────────
/** The band a rating alone would earn on the knee the team agreed (3.55 floor · 4.55 line = 75
 *  points · 5.00 = 100): Excellent from 4.82, Good from 4.55, Average from 4.35, Bad under it. */
export function ratingBand(rating: number | null | undefined): Band | null {
  if (rating == null || !Number.isFinite(rating) || rating <= 0) return null;
  return rating >= 4.82 ? "excellent" : rating >= RATING_LINE ? "good" : rating >= 4.35 ? "average" : "bad";
}
/** Share of the room that rated: 60%+ · 40%+ (the bar) · 25%+ · under. */
export function reachBand(pct: number | null | undefined): Band | null {
  if (pct == null || !Number.isFinite(pct)) return null;
  return pct >= 60 ? "excellent" : pct >= 40 ? "good" : pct >= 25 ? "average" : "bad";
}
/** Attendance against a reference room (the cohort's first class, the course's typical room):
 *  90%+ · 75%+ · 60%+ · under. */
export function ratioBand(ratio: number | null | undefined): Band | null {
  if (ratio == null || !Number.isFinite(ratio)) return null;
  return ratio >= 0.9 ? "excellent" : ratio >= 0.75 ? "good" : ratio >= 0.6 ? "average" : "bad";
}
export function scoreBand(score: number | null | undefined): Band | null {
  return score == null || !Number.isFinite(score) ? null : bandOf(Math.round(score));
}

// ── tracks (a course runs parallel tracks by audience: swe / em / pm / tech …) ─
export function trackOf(ref: { audience: string | null }): string {
  const a = (ref.audience ?? "").trim().toLowerCase();
  return a || "other";
}
const TRACK_LABELS: Record<string, string> = { swe: "SWE", em: "EM", pm: "PM", tech: "Tech", ind: "India", us: "US", other: "No track" };
export function trackLabel(track: string): string {
  if (track === ALL_TRACKS) return "All tracks";
  return TRACK_LABELS[track] ?? (track.length <= 4 ? track.toUpperCase() : track[0].toUpperCase() + track.slice(1));
}

// ── names ─────────────────────────────────────────────────────────────────────
/** "SWE : Retrieval-Augmented Generation" → "Retrieval-Augme…" — a column header, an x label. */
export function shortModuleName(name: string, max = 16): string {
  const s = name.replace(/^\s*[A-Za-z]{1,5}\s*[:：]\s*/, "").trim() || name.trim();
  return s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s;
}
/** "C2 · Mid Mar 2026 · IND" when the cohort has a number, else the name cut to size. */
export function shortCohortName(ref: CohortRefLike, max = 26): string {
  const no = ref.cohortNo ?? (/cohort\s*#?\s*(\d+)/i.exec(ref.name)?.[1] != null ? Number(/cohort\s*#?\s*(\d+)/i.exec(ref.name)![1]) : null);
  if (no != null) return [`C${no}`, ref.start, ref.region].filter(Boolean).join(" · ");
  return ref.name.length > max ? ref.name.slice(0, max - 1).trimEnd() + "…" : ref.name;
}
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
/** "+0.30" / "−0.30" / "0.00" — the typographic minus, like the Delta pill. */
export function fmtSigned(v: number, decimals = 2, unit = ""): string {
  const r = Number(v.toFixed(decimals));
  if (r === 0) return `${(0).toFixed(decimals)}${unit}`;
  return `${r > 0 ? "+" : "−"}${Math.abs(r).toFixed(decimals)}${unit}`;
}
export const plural = (n: number, one: string, many = one + "s") => (n === 1 ? one : many);

// ── the map ───────────────────────────────────────────────────────────────────
export type CurriculumCell = {
  /** Every session on this module, the live class first — the first id is what a click opens. */
  classIds: string[];
  rating: number | null;
  rated: number | null;
  attended: number | null;
  reach: number | null;
  score: number | null;
  band: Band | null;
  kinds: string[];
  instructors: string[];
  dates: string[];
  weeks: number[];
};

export type CohortWeekPoint = { week: number; attended: number | null; rating: number | null; rated: number | null; score: number | null; n: number };

export type CurriculumCohort = {
  key: string;
  name: string;
  short: string;
  href?: string;
  track: string;
  trackLabel: string;
  start: string | null;
  region: string | null;
  firstDate: string;
  lastDate: string;
  weekNow: number;
  /** A class in the last three weeks — the cohort is still running. */
  active: boolean;
  /** The fullest room the cohort ever had. */
  size: number | null;
  firstAttended: number | null;
  lastAttended: number | null;
  /** Last module's room over the first module's room (needs two modules with attendance). */
  retention: number | null;
  n: number;
  avgRating: number | null;
  avgAttended: number | null;
  avgReach: number | null;
  avgScore: number | null;
  counts: BandCounts;
  cells: Record<string, CurriculumCell>;
  /** The curriculum position (module order) of the cohort's last module — where it has got to. */
  lastOrder: number | null;
  weeks: CohortWeekPoint[];
};

export type ModuleInstructor = { key: string; name: string; href?: string; rating: number | null; attended: number | null; n: number };

export type CurriculumModule = {
  key: string;
  id: string | null;
  name: string;
  short: string;
  href?: string;
  order: number | null;
  n: number;
  cohorts: number;
  avgRating: number | null;
  avgAttended: number | null;
  avgReach: number | null;
  avgScore: number | null;
  /** Mean % change in attended against the cohort's previous module, over cohorts that have both. */
  dropAttended: number | null;
  /** Mean rating change against the cohort's previous module. */
  dropRating: number | null;
  dropPairs: number;
  dropFell: number;
  /** The module most cohorts took just before this one. */
  prevKey: string | null;
  prevName: string | null;
  /** Cohorts whose cell is under the 4.55 line. */
  underLine: number;
  bestInstructor: ModuleInstructor | null;
  instructors: ModuleInstructor[];
};

export type InsightKind = "attendance_drop" | "rating_dip" | "fixer" | "consistent_low";
export type Insight = {
  kind: InsightKind;
  /** Plain sentence; `**…**` marks the name to set in bold. */
  title: string;
  detail: string;
  href?: string;
  moduleKey?: string;
  instructorKey?: string;
};

export type TrackOption = { track: string; label: string; cohorts: number };

export type CurriculumMap = {
  modules: CurriculumModule[];
  /** Most recent first. */
  cohorts: CurriculumCohort[];
  insights: Insight[];
  /** Every track among the cohorts in the window (before the track filter), biggest first. */
  tracks: TrackOption[];
  /** The track applied ("all" = every cohort). */
  track: string;
  courseAvgRating: number | null;
  courseAvgAttended: number | null;
};

export type CurriculumLinks = {
  module?: (key: string) => string;
  instructor?: (key: string) => string;
  cohort?: (key: string) => string;
  /** Where "attendance falls…" should point when a page has a map elsewhere (the overview). */
  map?: string;
};

export type CurriculumOptions<R extends CurriculumRow = CurriculumRow> = {
  /** A row's cohorts (ids resolved through the cohorts table, else the sheet's text). */
  refsOf: (r: R) => CohortRefLike[];
  /** Cohorts to include — those with a class in the period; null = every cohort in the rows. */
  cohortKeys?: ReadonlySet<string> | null;
  /** "swe" / "pm" / … / "all"; undefined = the track with the most cohorts (all when there is one). */
  track?: string | null;
  asOf?: string;
  /** Classes a topic needs (across every row given) to count as a module. */
  minClasses?: number;
  links?: CurriculumLinks;
};

function buildCell(list: CurriculumRow[], weekOf: (r: CurriculumRow) => number): CurriculumCell {
  const sorted = [...list].sort((a, b) => kindRank(a) - kindRank(b) || a.class_date.localeCompare(b.class_date));
  const withRoom = sorted.filter((r) => r.attended != null);
  const fullest = withRoom.length ? withRoom.reduce((m, r) => (r.attended! > m.attended! ? r : m)) : null;
  const maxRated = nums(sorted, (r) => r.num_ratings);
  const score = mean(nums(sorted, (r) => r.score));
  const kinds = uniq(sorted.map((r) => r.session_kind)).sort((a, b) => kindRank({ session_kind: a }) - kindRank({ session_kind: b }));
  return {
    classIds: sorted.map((r) => r.id),
    rating: mean(ratingsOf(sorted)),
    rated: fullest?.num_ratings ?? (maxRated.length ? Math.max(...maxRated) : null),
    attended: fullest?.attended ?? null,
    reach: mean(nums(sorted, (r) => r.participation_pct)),
    score,
    band: scoreBand(score),
    kinds,
    instructors: uniq(sorted.map(instructorNameOf)),
    dates: uniq(sorted.map((r) => r.class_date)).sort(),
    weeks: uniq(sorted.map(weekOf)).sort((a, b) => a - b),
  };
}

export function buildCurriculumMap<R extends CurriculumRow>(rows: R[], opts: CurriculumOptions<R>): CurriculumMap {
  const asOf = opts.asOf ?? today();
  const minClasses = opts.minClasses ?? 2;
  const links = opts.links ?? {};
  const rowById = new Map<string, R>(rows.map((r) => [r.id, r]));

  // ── modules: real topics with enough classes across everything we were given ──
  const moduleRowsAll = new Map<string, R[]>();
  for (const r of rows) if (isModuleRow(r)) push(moduleRowsAll, moduleKeyOf(r), r);
  const moduleKeys = new Set([...moduleRowsAll].filter(([, list]) => list.length >= minClasses).map(([k]) => k));

  // ── cohorts: group, then keep the ones the page asked for ──
  const groups = new Map<string, { ref: CohortRefLike; rows: R[] }>();
  for (const r of rows) {
    for (const ref of opts.refsOf(r)) {
      const g = groups.get(ref.key);
      if (g) g.rows.push(r);
      else groups.set(ref.key, { ref, rows: [r] });
    }
  }
  const firstDateOf = new Map<string, string>();
  for (const [key, g] of groups) firstDateOf.set(key, g.rows.map((r) => r.class_date).sort()[0]);
  let included = [...groups.values()].filter((g) => !opts.cohortKeys || opts.cohortKeys.has(g.ref.key));

  const trackCounts = new Map<string, number>();
  for (const g of included) trackCounts.set(trackOf(g.ref), (trackCounts.get(trackOf(g.ref)) ?? 0) + 1);
  const tracks: TrackOption[] = [...trackCounts]
    .map(([track, n]) => ({ track, label: trackLabel(track), cohorts: n }))
    .sort((a, b) => b.cohorts - a.cohorts || a.label.localeCompare(b.label));
  let track = opts.track == null || opts.track === "" ? null : opts.track.toLowerCase();
  if (track == null) track = tracks.length >= 2 ? tracks[0].track : ALL_TRACKS;
  if (track !== ALL_TRACKS && !trackCounts.has(track)) track = ALL_TRACKS;
  if (track !== ALL_TRACKS) included = included.filter((g) => trackOf(g.ref) === track);

  // ── one cohort at a time ──
  const cohorts: CurriculumCohort[] = included.map((g) => {
    const list = [...g.rows].sort((a, b) => a.class_date.localeCompare(b.class_date) || a.id.localeCompare(b.id));
    const firstDate = list[0].class_date;
    const lastDate = list[list.length - 1].class_date;
    const weekOf = (r: CurriculumRow) => (r.week_no != null && r.week_no > 0 ? r.week_no : Math.floor(daysBetween(firstDate, r.class_date) / 7) + 1);
    const byModule = new Map<string, R[]>();
    for (const r of list) if (isModuleRow(r) && moduleKeys.has(moduleKeyOf(r))) push(byModule, moduleKeyOf(r), r);
    const cells: Record<string, CurriculumCell> = {};
    for (const [k, l] of byModule) cells[k] = buildCell(l, weekOf);
    const chrono = [...byModule.entries()]
      .map(([k, l]) => ({ k, date: l[0].class_date, cell: cells[k] }))
      .sort((a, b) => a.date.localeCompare(b.date));
    const withRoom = chrono.filter((x) => x.cell.attended != null);
    const firstAttended = withRoom[0]?.cell.attended ?? null;
    const lastAttended = withRoom.length >= 2 ? withRoom[withRoom.length - 1].cell.attended : null;
    const rooms = nums(list, (r) => r.attended);
    const top = Math.max(0, ...list.map(weekOf));
    const nWeeks = Math.max(JOURNEY_WEEKS, Math.min(top, MAX_WEEKS));
    const weekRows = new Map<number, R[]>();
    for (const r of list) push(weekRows, weekOf(r), r);
    const weeks: CohortWeekPoint[] = Array.from({ length: nWeeks }, (_, i) => {
      const w = i + 1;
      const l = weekRows.get(w) ?? [];
      return { week: w, attended: mean(nums(l, (r) => r.attended)), rating: mean(ratingsOf(l)), rated: mean(nums(l, (r) => r.num_ratings)), score: mean(nums(l, (r) => r.score)), n: l.length };
    });
    const t = trackOf(g.ref);
    return {
      key: g.ref.key,
      name: g.ref.name,
      short: shortCohortName(g.ref),
      href: links.cohort?.(g.ref.key),
      track: t,
      trackLabel: trackLabel(t),
      start: g.ref.start,
      region: g.ref.region,
      firstDate,
      lastDate,
      weekNow: Math.min(99, Math.floor(daysBetween(firstDate, asOf) / 7) + 1),
      active: daysBetween(lastDate, asOf) <= ACTIVE_DAYS,
      size: rooms.length ? Math.max(...rooms) : null,
      firstAttended,
      lastAttended,
      retention: firstAttended && lastAttended != null ? lastAttended / firstAttended : null,
      n: list.length,
      avgRating: mean(ratingsOf(list)),
      avgAttended: mean(rooms),
      avgReach: mean(nums(list, (r) => r.participation_pct)),
      avgScore: mean(nums(list, (r) => r.score)),
      counts: bandCounts(list),
      cells,
      lastOrder: null,
      weeks,
    };
  });
  cohorts.sort((a, b) => b.firstDate.localeCompare(a.firstDate) || a.name.localeCompare(b.name));
  // Short names must be unique — charts key their legends on them.
  const seen = new Map<string, number>();
  for (const c of cohorts) {
    const k = seen.get(c.short) ?? 0;
    seen.set(c.short, k + 1);
    if (k > 0) c.short = `${c.short} (${k + 1})`;
  }

  // ── modules the included cohorts took, in curriculum order ──
  const taken = new Set(cohorts.flatMap((c) => Object.keys(c.cells)));
  const orderOf = (key: string): number | null => {
    const weeks = cohorts.flatMap((c) => c.cells[key]?.weeks ?? []);
    if (weeks.length) return median(weeks);
    // Not taken by the cohorts shown: fall back to every row of the module.
    const all = (moduleRowsAll.get(key) ?? []).map((r) => {
      if (r.week_no != null && r.week_no > 0) return r.week_no;
      const ref = opts.refsOf(r)[0];
      const first = ref ? firstDateOf.get(ref.key) : undefined;
      return first ? Math.floor(daysBetween(first, r.class_date) / 7) + 1 : null;
    });
    return median(all.filter((v): v is number => v != null));
  };
  const firstSeen = (key: string) => (moduleRowsAll.get(key) ?? []).map((r) => r.class_date).sort()[0] ?? "";
  const moduleOrder = [...taken]
    .map((key) => ({ key, order: orderOf(key), first: firstSeen(key) }))
    .sort((a, b) => (a.order ?? 99) - (b.order ?? 99) || a.first.localeCompare(b.first) || a.key.localeCompare(b.key));
  const orderIndex = new Map(moduleOrder.map((m, i) => [m.key, i]));

  // ── drops: per cohort, against the cohort's own previous module ──
  const attDrops = new Map<string, number[]>();
  const ratDrops = new Map<string, number[]>();
  const prevCounts = new Map<string, Map<string, number>>();
  for (const c of cohorts) {
    const seq = Object.keys(c.cells).sort((a, b) => (orderIndex.get(a) ?? 0) - (orderIndex.get(b) ?? 0));
    c.lastOrder = seq.length ? (orderIndex.get(seq[seq.length - 1]) ?? null) : null;
    for (let i = 1; i < seq.length; i++) {
      const prev = c.cells[seq[i - 1]];
      const cur = c.cells[seq[i]];
      const pc = prevCounts.get(seq[i]) ?? new Map<string, number>();
      pc.set(seq[i - 1], (pc.get(seq[i - 1]) ?? 0) + 1);
      prevCounts.set(seq[i], pc);
      if (prev.attended && cur.attended != null) push(attDrops, seq[i], ((cur.attended - prev.attended) / prev.attended) * 100);
      if (prev.rating != null && cur.rating != null) push(ratDrops, seq[i], cur.rating - prev.rating);
    }
  }

  const nameOf = (key: string) => (moduleRowsAll.get(key)?.[0]?.topic.trim() ?? key.replace(/^name:/, ""));
  const modules: CurriculumModule[] = moduleOrder.map(({ key, order }) => {
    const ids = uniq(cohorts.flatMap((c) => c.cells[key]?.classIds ?? []));
    const list = ids.map((id) => rowById.get(id)).filter((r): r is R => !!r);
    const byInstructor = new Map<string, R[]>();
    for (const r of list) push(byInstructor, instructorKeyOf(r), r);
    const instructors: ModuleInstructor[] = [...byInstructor.entries()]
      .map(([k, l]) => ({ key: k, name: instructorNameOf(l[0]), href: links.instructor?.(k), rating: mean(ratingsOf(l)), attended: mean(nums(l, (r) => r.attended)), n: l.length }))
      .sort((a, b) => (b.rating ?? -1) - (a.rating ?? -1) || b.n - a.n);
    const seasoned = instructors.filter((i) => i.n >= 2 && i.rating != null);
    const pc = prevCounts.get(key);
    const prevKey = pc ? [...pc.entries()].sort((a, b) => b[1] - a[1])[0][0] : null;
    const drops = attDrops.get(key) ?? [];
    const name = nameOf(key);
    return {
      key,
      id: list[0]?.topic_id ?? moduleRowsAll.get(key)?.[0]?.topic_id ?? null,
      name,
      short: shortModuleName(name),
      href: links.module?.(key),
      order,
      n: list.length,
      cohorts: cohorts.filter((c) => c.cells[key]).length,
      avgRating: mean(ratingsOf(list)),
      avgAttended: mean(nums(list, (r) => r.attended)),
      avgReach: mean(nums(list, (r) => r.participation_pct)),
      avgScore: mean(nums(list, (r) => r.score)),
      dropAttended: mean(drops),
      dropRating: mean(ratDrops.get(key) ?? []),
      dropPairs: drops.length,
      dropFell: drops.filter((d) => d < 0).length,
      prevKey,
      prevName: prevKey ? nameOf(prevKey) : null,
      underLine: cohorts.filter((c) => c.cells[key]?.rating != null && c.cells[key].rating! < RATING_LINE).length,
      bestInstructor: instructors.length >= 2 && seasoned.length ? seasoned[0] : null,
      instructors,
    };
  });

  const includedRows = uniq(cohorts.flatMap((c) => Object.values(c.cells).flatMap((cell) => cell.classIds)))
    .map((id) => rowById.get(id))
    .filter((r): r is R => !!r);
  const courseAvgRating = mean(ratingsOf(includedRows));
  const courseAvgAttended = mean(nums(includedRows, (r) => r.attended));

  return {
    modules,
    cohorts,
    insights: buildInsights(modules, cohorts.length, courseAvgRating, links),
    tracks,
    track,
    courseAvgRating,
    courseAvgAttended,
  };
}

// ── the sentences ─────────────────────────────────────────────────────────────
const bold = (s: string) => `**${s}**`;
const f2 = (v: number) => v.toFixed(2);

export function buildInsights(modules: CurriculumModule[], cohortCount: number, courseAvgRating: number | null, links: CurriculumLinks = {}): Insight[] {
  const out: Insight[] = [];
  if (!modules.length || cohortCount === 0) return out;
  const byKey = new Map(modules.map((m) => [m.key, m]));
  const weak: CurriculumModule[] = [];

  // Where the room shrinks most, against the module just before it.
  const dropCandidates = modules.filter((m) => m.dropAttended != null && m.dropPairs >= 2);
  const biggestDrop = dropCandidates.sort((a, b) => a.dropAttended! - b.dropAttended!)[0];
  if (biggestDrop && biggestDrop.dropAttended! <= -5) {
    const prev = biggestDrop.prevKey ? byKey.get(biggestDrop.prevKey) : undefined;
    const rooms = prev?.avgAttended != null && biggestDrop.avgAttended != null ? ` — the room goes from ${Math.round(prev.avgAttended)} to ${Math.round(biggestDrop.avgAttended)} on average` : "";
    out.push({
      kind: "attendance_drop",
      title: `Attendance falls most at ${bold(biggestDrop.name)}: ${fmtSigned(biggestDrop.dropAttended!, 0, "%")} against the module before it, in ${biggestDrop.dropFell} of ${biggestDrop.dropPairs} cohorts`,
      detail: `${prev ? `After ${prev.name}` : "After the previous module"}${rooms}.`,
      href: links.map ?? biggestDrop.href,
      moduleKey: biggestDrop.key,
    });
  }

  // The lowest-rated module against the course.
  const rated = modules.filter((m) => m.avgRating != null);
  const lowest = [...rated].sort((a, b) => a.avgRating! - b.avgRating!)[0];
  if (lowest && courseAvgRating != null && lowest.avgRating! <= courseAvgRating - 0.1) {
    const step = lowest.dropRating != null && lowest.dropRating <= -0.1 && lowest.prevName ? ` · ${fmtSigned(lowest.dropRating)} from ${lowest.prevName} just before it` : "";
    const who = lowest.instructors.length >= 2 ? `${lowest.instructors.length} instructors have taught it` : `always taught by ${lowest.instructors[0]?.name ?? "one instructor"}`;
    out.push({
      kind: "rating_dip",
      title: `The rating dips most at ${bold(lowest.name)}: ${f2(lowest.avgRating!)} against the course's ${f2(courseAvgRating)}`,
      detail: `${lowest.n} ${plural(lowest.n, "class", "classes")} across ${lowest.cohorts} ${plural(lowest.cohorts, "cohort")} · ${who}${step}.`,
      href: lowest.href,
      moduleKey: lowest.key,
    });
    weak.push(lowest);
  }

  // The biggest step down between two modules, when it is somewhere else.
  const stepDown = modules.filter((m) => m.dropRating != null && m.dropPairs >= 2 && m.key !== lowest?.key).sort((a, b) => a.dropRating! - b.dropRating!)[0];
  if (stepDown && stepDown.dropRating! <= -0.15 && stepDown.prevName) {
    out.push({
      kind: "rating_dip",
      title: `The biggest step down is at ${bold(stepDown.name)}: ${fmtSigned(stepDown.dropRating!)} from ${stepDown.prevName} just before it`,
      detail: `${f2(stepDown.avgRating ?? 0)} on average after ${f2(byKey.get(stepDown.prevKey!)?.avgRating ?? 0)} · over ${stepDown.dropPairs} ${plural(stepDown.dropPairs, "cohort")}.`,
      href: stepDown.href,
      moduleKey: stepDown.key,
    });
    weak.push(stepDown);
  }

  // Under the line for most cohorts — the material, not one person.
  const consistent = modules
    .filter((m) => m.cohorts >= 3 && m.underLine / m.cohorts >= 0.6)
    .sort((a, b) => b.underLine / b.cohorts - a.underLine / a.cohorts || (a.avgRating ?? 5) - (b.avgRating ?? 5))
    .slice(0, 2);
  for (const m of consistent) {
    const k = m.instructors.length;
    out.push({
      kind: "consistent_low",
      title: `${bold(m.name)} is under the ${RATING_LINE} line in ${m.underLine} of ${m.cohorts} cohorts`,
      detail: k >= 2 ? `${k} different instructors taught it — that points at the material, not one person.` : `Always taught by ${m.instructors[0]?.name ?? "one instructor"} — the material and the delivery are hard to tell apart here.`,
      href: m.href,
      moduleKey: m.key,
    });
    if (!weak.some((w) => w.key === m.key)) weak.push(m);
  }

  // Who lifts the weak modules — and where nobody does yet.
  let fixers = 0;
  for (const m of weak) {
    if (fixers >= 2 || m.avgRating == null || m.instructors.length < 2) continue;
    const best = m.bestInstructor;
    if (best && best.rating != null && best.rating >= m.avgRating + LIFT) {
      const others = m.instructors.filter((i) => i.key !== best.key && i.rating != null);
      const othersAvg = mean(others.map((i) => i.rating!));
      out.push({
        kind: "fixer",
        title: `${bold(best.name)} teaches ${m.name} above its average: ${f2(best.rating)} across ${best.n} ${plural(best.n, "class", "classes")} (module average ${f2(m.avgRating)})`,
        detail: othersAvg != null ? `The other ${others.length} ${plural(others.length, "instructor")} average ${f2(othersAvg)} on it.` : `No one else has a rating on it yet.`,
        href: best.href ?? m.href,
        moduleKey: m.key,
        instructorKey: best.key,
      });
      fixers += 1;
    } else {
      const top = m.instructors.find((i) => i.rating != null);
      out.push({
        kind: "fixer",
        title: `Nobody lifts ${bold(m.name)} yet — all ${m.instructors.length} instructors who taught it sit at or near its ${f2(m.avgRating)} average`,
        detail: top ? `Best so far: ${top.name} at ${f2(top.rating!)} across ${top.n} ${plural(top.n, "class", "classes")}.` : "No instructor has a rating on it.",
        href: m.href,
        moduleKey: m.key,
      });
      fixers += 1;
    }
  }
  return out.slice(0, 6);
}

// ── the journeys (attendance and rating along the course) ─────────────────────
export type JourneySeries = { key: string; name: string; attended: (number | null)[]; rating: (number | null)[] };
export type JourneyAxis = {
  labels: string[];
  /** Full names behind the labels (module names; null for weeks). */
  names: (string | null)[];
  /** A second line under each label ("W3"); null for weeks. */
  notes: (string | null)[];
  cohorts: JourneySeries[];
  median: { attended: (number | null)[]; rating: (number | null)[] };
};
export type Journey = { byModule: JourneyAxis; byWeek: JourneyAxis };

/** Per cohort, the room and the rating at each curriculum position and at each cohort week,
 *  plus the median across the cohorts given (the bold line). */
export function attendanceJourney(cohorts: CurriculumCohort[], modules: CurriculumModule[]): Journey {
  const med = (xs: (number | null)[][], i: number) => median(xs.map((s) => s[i]).filter((v): v is number => v != null));
  const byModule: JourneyAxis = {
    labels: modules.map((m) => m.short),
    names: modules.map((m) => m.name),
    notes: modules.map((m) => (m.order != null ? `W${Math.round(m.order)}` : null)),
    cohorts: cohorts.map((c) => ({
      key: c.key,
      name: c.short,
      attended: modules.map((m) => c.cells[m.key]?.attended ?? null),
      rating: modules.map((m) => c.cells[m.key]?.rating ?? null),
    })),
    median: { attended: [], rating: [] },
  };
  byModule.median.attended = modules.map((_, i) => med(byModule.cohorts.map((c) => c.attended), i));
  byModule.median.rating = modules.map((_, i) => med(byModule.cohorts.map((c) => c.rating), i));

  const lastWeek = Math.max(JOURNEY_WEEKS, ...cohorts.map((c) => c.weeks.reduce((top, w) => (w.n > 0 ? w.week : top), 0)));
  const nWeeks = Math.min(lastWeek, MAX_WEEKS);
  const byWeek: JourneyAxis = {
    labels: Array.from({ length: nWeeks }, (_, i) => `W${i + 1}`),
    names: Array.from({ length: nWeeks }, () => null),
    notes: Array.from({ length: nWeeks }, () => null),
    cohorts: cohorts.map((c) => ({
      key: c.key,
      name: c.short,
      attended: Array.from({ length: nWeeks }, (_, i) => c.weeks[i]?.attended ?? null),
      rating: Array.from({ length: nWeeks }, (_, i) => c.weeks[i]?.rating ?? null),
    })),
    median: { attended: [], rating: [] },
  };
  byWeek.median.attended = byWeek.labels.map((_, i) => med(byWeek.cohorts.map((c) => c.attended), i));
  byWeek.median.rating = byWeek.labels.map((_, i) => med(byWeek.cohorts.map((c) => c.rating), i));
  return { byModule, byWeek };
}

// ── who lifts a module, who struggles with it ─────────────────────────────────
export type Verdict = "lifts" | "struggles" | null;
export type FixerRow = {
  key: string;
  name: string;
  href?: string;
  rating: number | null;
  attended: number | null;
  reach: number | null;
  n: number;
  /** Their rating minus the module's average. */
  delta: number | null;
  verdict: Verdict;
};

export function verdictOf(delta: number | null, n: number, minN = 2): Verdict {
  if (delta == null || n < minN) return null;
  return delta >= LIFT ? "lifts" : delta <= -LIFT ? "struggles" : null;
}

/** Instructors on one module ranked by rating, each against the module's average; "lifts" is
 *  ≥ 0.15 above it with two or more classes, "struggles" ≥ 0.15 under. */
export function moduleFixers(topic: { rows: CurriculumRow[] }, links?: { instructor?: (key: string) => string }) {
  const avg = mean(ratingsOf(topic.rows));
  const by = new Map<string, CurriculumRow[]>();
  for (const r of topic.rows) push(by, instructorKeyOf(r), r);
  const instructors: FixerRow[] = [...by.entries()]
    .map(([key, list]) => {
      const rating = mean(ratingsOf(list));
      const delta = rating != null && avg != null ? rating - avg : null;
      return {
        key,
        name: instructorNameOf(list[0]),
        href: links?.instructor?.(key),
        rating,
        attended: mean(nums(list, (r) => r.attended)),
        reach: mean(nums(list, (r) => r.participation_pct)),
        n: list.length,
        delta,
        verdict: verdictOf(delta, list.length),
      };
    })
    .sort((a, b) => (b.rating ?? -1) - (a.rating ?? -1) || b.n - a.n);
  return {
    avgRating: avg,
    instructors,
    lifts: instructors.filter((i) => i.verdict === "lifts"),
    struggles: instructors.filter((i) => i.verdict === "struggles").sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0)),
  };
}

export type ModuleFit = {
  key: string;
  name: string;
  href?: string;
  rating: number;
  moduleRating: number;
  n: number;
  moduleN: number;
  delta: number;
  verdict: Verdict;
};

/** For one instructor: the modules they lift and the ones they struggle with, each with their
 *  rating, the module's average across every instructor, and how many classes each rests on. */
export function instructorModuleFit(own: CurriculumRow[], course: CurriculumRow[], opts: { minN?: number; href?: (key: string) => string } = {}) {
  const minN = opts.minN ?? 2;
  const courseBy = new Map<string, CurriculumRow[]>();
  for (const r of course) if (isModuleRow(r)) push(courseBy, moduleKeyOf(r), r);
  const ownBy = new Map<string, CurriculumRow[]>();
  for (const r of own) if (isModuleRow(r)) push(ownBy, moduleKeyOf(r), r);
  const all: ModuleFit[] = [];
  for (const [key, list] of ownBy) {
    const courseRows = courseBy.get(key);
    if (!courseRows || courseRows.length < 2 || list.length < minN) continue;
    const rating = mean(ratingsOf(list));
    const moduleRating = mean(ratingsOf(courseRows));
    if (rating == null || moduleRating == null) continue;
    const delta = rating - moduleRating;
    all.push({ key, name: list[0].topic.trim(), href: opts.href?.(key), rating, moduleRating, n: list.length, moduleN: courseRows.length, delta, verdict: verdictOf(delta, list.length, minN) });
  }
  all.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  return {
    all,
    lifts: all.filter((m) => m.verdict === "lifts").sort((a, b) => b.delta - a.delta),
    struggles: all.filter((m) => m.verdict === "struggles").sort((a, b) => a.delta - b.delta),
  };
}
