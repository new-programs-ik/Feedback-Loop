import "server-only";
import { createClient } from "@/lib/supabase/server";
import { APPROVAL_BAR, GOOD, MIN_VOICES, type FlagReason, type HealthBand } from "@/lib/decision";
import type { Action, Band } from "@/lib/sentiment";

/** Typed access + pure aggregation over class_ratings (the hourly-synced ratings feed).
 *
 *  Every fetch selects `*` and normalises: the v3 columns (sentiment_*, cohort_id, topic_id,
 *  instructor_canonical, week_no …) are added by migrations 0015–0019 which land in parallel with
 *  this code, so a missing column simply reads as null and nothing crashes. */

export type SessionKind = "Live Class" | "Test Review" | "Other" | string;
export type ReviewStatus = "new" | "notified" | "confirmed" | "dismissed" | "analysis_started";
export type Decision = "none" | "watch" | "transcript" | "video";

export type ClassRating = {
  id: string;
  source: string | null;
  course_label: string;
  course_id: string | null;
  course_name: string | null;
  course_slug: string | null;
  cohort_text: string | null;
  topic: string;
  instructor: string;
  instructor_id: string | null;
  /** The resolved (merged) instructor name — falls back to `instructor` until identity lands. */
  instructor_canonical: string | null;
  class_date: string; // ISO yyyy-mm-dd
  session_kind: SessionKind;
  rating: number;
  num_ratings: number | null;
  attended: number | null;
  participation_pct: number | null;
  yes_votes: number | null;
  no_votes: number | null;
  approval_pct: number | null;
  track_avg: number | null;
  health_score: number | null;
  health_band: HealthBand | null;
  flag_reasons: FlagReason[];
  escalated: boolean;
  decision: Decision;
  decision_override: Decision | null;
  review_status: ReviewStatus;
  class_id: string | null;
  synced_at: string;
  updated_at: string | null;
  // ── v3: the Class Sentiment Score (migration 0015) ──
  sentiment_score: number | null;
  sentiment_band: Band | null;
  sentiment_action: Action | null;
  sentiment_provisional: boolean | null;
  sentiment_flags: string[];
  score_config_id: string | null;
  score_components: Record<string, unknown> | null;
  scored_at: string | null;
  // ── v3: cohorts + modules (0017) ──
  cohort_id: string | null;
  cohort_ids: string[];
  topic_id: string | null;
  week_no: number | null;
};

type Raw = Record<string, unknown>;
const numOrNull = (v: unknown): number | null => {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
};
const strOrNull = (v: unknown): string | null => (v == null ? null : String(v));
const arr = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);

/** One normaliser for every source: the table, the `queue_rows` RPC, a joined select. */
export function normalizeRating(r: Raw): ClassRating {
  const course = (r.courses as { name?: string; slug?: string } | null) ?? null;
  return {
    id: String(r.id),
    source: strOrNull(r.source),
    course_label: String(r.course_label ?? ""),
    course_id: strOrNull(r.course_id),
    course_name: strOrNull(r.course_name) ?? course?.name ?? null,
    course_slug: strOrNull(r.course_slug) ?? course?.slug ?? null,
    cohort_text: strOrNull(r.cohort_text),
    topic: String(r.topic ?? ""),
    instructor: String(r.instructor ?? ""),
    instructor_id: strOrNull(r.instructor_id),
    instructor_canonical: strOrNull(r.instructor_canonical),
    class_date: String(r.class_date ?? "").slice(0, 10),
    session_kind: String(r.session_kind ?? "Live Class"),
    rating: Number(r.rating ?? 0),
    num_ratings: numOrNull(r.num_ratings),
    attended: numOrNull(r.attended),
    participation_pct: numOrNull(r.participation_pct),
    yes_votes: numOrNull(r.yes_votes),
    no_votes: numOrNull(r.no_votes),
    approval_pct: numOrNull(r.approval_pct),
    track_avg: numOrNull(r.track_avg),
    health_score: numOrNull(r.health_score),
    health_band: (r.health_band as HealthBand | null) ?? null,
    flag_reasons: arr(r.flag_reasons) as FlagReason[],
    escalated: Boolean(r.escalated),
    decision: ((r.decision as Decision) ?? "none") || "none",
    decision_override: (r.decision_override as Decision | null) ?? null,
    review_status: ((r.review_status as ReviewStatus) ?? "new") || "new",
    class_id: strOrNull(r.class_id),
    synced_at: String(r.synced_at ?? ""),
    updated_at: strOrNull(r.updated_at),
    sentiment_score: numOrNull(r.sentiment_score),
    sentiment_band: (r.sentiment_band as Band | null) ?? null,
    sentiment_action: (r.sentiment_action as Action | null) ?? null,
    sentiment_provisional: r.sentiment_provisional == null ? null : Boolean(r.sentiment_provisional),
    sentiment_flags: arr(r.sentiment_flags),
    score_config_id: strOrNull(r.score_config_id),
    score_components: (r.score_components as Record<string, unknown> | null) ?? null,
    scored_at: strOrNull(r.scored_at),
    cohort_id: strOrNull(r.cohort_id),
    cohort_ids: arr(r.cohort_ids),
    topic_id: strOrNull(r.topic_id),
    week_no: numOrNull(r.week_no),
  };
}

const SELECT = "*, courses(name, slug)";
const PAGE = 1000;

/** The most recent rated class date (one course, or every course) — the report windows end
 *  here when the sheet is behind today, so a report is never empty. */
export async function latestRatedDate(courseId?: string | null): Promise<string | null> {
  const supabase = await createClient();
  let q = supabase.from("class_ratings").select("class_date").order("class_date", { ascending: false }).limit(1);
  if (courseId) q = q.eq("course_id", courseId);
  const { data } = await q;
  const d = (data?.[0] as { class_date?: string } | undefined)?.class_date;
  return d ? String(d).slice(0, 10) : null;
}

export async function fetchRatings(opts: { from: string; to: string; courseId?: string | null }): Promise<ClassRating[]> {
  const supabase = await createClient();
  // PostgREST caps every response at 1,000 rows — a full-year view is ~4,000+, so page through
  // explicitly or the data silently truncates (bug caught when "since January" showed 1,000).
  const all: Raw[] = [];
  for (let page = 0; page < 40; page++) {
    let q = supabase
      .from("class_ratings")
      .select(SELECT)
      .gte("class_date", opts.from)
      .lte("class_date", opts.to)
      .order("class_date", { ascending: false })
      .order("id", { ascending: false })
      .range(page * PAGE, page * PAGE + PAGE - 1);
    if (opts.courseId) q = q.eq("course_id", opts.courseId);
    const { data } = await q;
    const batch = (data ?? []) as unknown as Raw[];
    all.push(...batch);
    if (batch.length < PAGE) break;
  }
  return all.map(normalizeRating);
}

/** The queue's rows: `queue_rows(p_course_id, p_since)` when the RPC exists (migration 0019),
 *  otherwise the plain fetch since the given date. Both come back in the same shape. */
export async function fetchQueue(courseId: string | null, since: string): Promise<{ rows: ClassRating[]; viaRpc: boolean }> {
  const supabase = await createClient();
  const rpc = await supabase.rpc("queue_rows", { p_course_id: courseId, p_since: since });
  if (!rpc.error && Array.isArray(rpc.data)) {
    return { rows: (rpc.data as Raw[]).map(normalizeRating), viaRpc: true };
  }
  const to = new Date().toISOString().slice(0, 10);
  return { rows: await fetchRatings({ from: since, to, courseId }), viaRpc: false };
}

export async function fetchClass(id: string): Promise<ClassRating | null> {
  const supabase = await createClient();
  const { data } = await supabase.from("class_ratings").select(SELECT).eq("id", id).maybeSingle();
  return data ? normalizeRating(data as unknown as Raw) : null;
}

export type ClassSortKey =
  | "score" | "class" | "cohort" | "instructor" | "date" | "kind" | "rating" | "vote" | "reach" | "action";
export const CLASS_SORT_COLUMN: Record<ClassSortKey, string> = {
  score: "sentiment_score",
  class: "topic",
  cohort: "cohort_text",
  instructor: "instructor",
  date: "class_date",
  kind: "session_kind",
  rating: "rating",
  vote: "approval_pct",
  reach: "participation_pct",
  action: "sentiment_action",
};
const V3_COLUMNS = new Set(["sentiment_score", "sentiment_action", "sentiment_band", "instructor_canonical", "cohort_id"]);

export type ClassesPageQuery = {
  courseId: string | null;
  from: string;
  to: string;
  sort?: ClassSortKey;
  dir?: "asc" | "desc";
  page?: number;
  pageSize?: number;
  cohort?: string;
  kind?: string;
  instructor?: string;
  band?: string;
  status?: string;
};

const isUuid = (s: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
const quote = (s: string) => `"${s.replace(/"/g, '\\"')}"`;

/** How many classes fall in each band for this period and these filters, ignoring the band filter
 *  itself - so the chips can say "Bad 12" while Bad is switched off. One narrow column, so this
 *  stays cheap even over a year. */
export async function fetchBandCounts(q: Omit<ClassesPageQuery, "band" | "sort" | "dir" | "page" | "perPage">):
  Promise<Record<string, number>> {
  const supabase = await createClient();
  const out: Record<string, number> = {};
  try {
    let s = supabase.from("class_ratings").select("sentiment_band").gte("class_date", q.from).lte("class_date", q.to);
    if (q.courseId) s = s.eq("course_id", q.courseId);
    if (q.cohort) s = s.eq("cohort_text", q.cohort);
    if (q.kind) s = s.eq("session_kind", q.kind);
    if (q.instructor) {
      if (isUuid(q.instructor)) s = s.eq("instructor_id", q.instructor);
      else s = s.or(`instructor.eq.${quote(q.instructor)},instructor_canonical.eq.${quote(q.instructor)}`);
    }
    const { data, error } = await s.limit(5000);
    if (error) return out;
    for (const r of (data ?? []) as Array<{ sentiment_band: string | null }>) {
      const k = r.sentiment_band ?? "none";
      out[k] = (out[k] ?? 0) + 1;
    }
  } catch {
    return out;                      // the chips simply show no counts
  }
  return out;
}

/** One page of the classes table — filtered, sorted and paged in SQL so it stays fast past a few
 *  thousand rows. Falls back to classic columns (and drops the band filter) while the v3 columns
 *  are still being added; `degraded` says so. */
export async function fetchClassesPage(q: ClassesPageQuery): Promise<{
  rows: ClassRating[];
  total: number;
  page: number;
  pageSize: number;
  degraded: boolean;
}> {
  const supabase = await createClient();
  const pageSize = q.pageSize ?? 50;
  const page = Math.max(1, q.page ?? 1);
  const sort = q.sort ?? "date";
  const dir = q.dir ?? (sort === "date" ? "desc" : "asc");

  const build = (v3: boolean) => {
    let s = supabase
      .from("class_ratings")
      .select(SELECT, { count: "exact" })
      .gte("class_date", q.from)
      .lte("class_date", q.to);
    if (q.courseId) s = s.eq("course_id", q.courseId);
    if (q.kind) s = s.eq("session_kind", q.kind);
    if (q.status) {
      if (q.status === "open") s = s.in("review_status", ["new", "notified", "confirmed"]);
      else s = s.eq("review_status", q.status);
    }
    if (q.cohort) {
      if (v3 && isUuid(q.cohort)) s = s.or(`cohort_id.eq.${q.cohort},cohort_ids.cs.{${q.cohort}}`);
      else s = s.ilike("cohort_text", `%${q.cohort.replace(/[%_]/g, "")}%`);
    }
    if (q.instructor) {
      if (v3 && isUuid(q.instructor)) s = s.eq("instructor_id", q.instructor);
      else if (v3) s = s.or(`instructor.eq.${quote(q.instructor)},instructor_canonical.eq.${quote(q.instructor)}`);
      else s = s.eq("instructor", q.instructor);
    }
    if (q.band && v3) {
      // One band or several, comma separated. It used to accept only one, so "show me the bad ones
      // and the average ones" was not a question the page could be asked.
      const wanted = q.band.split(",").map((b) => b.trim()).filter(Boolean);
      const withNone = wanted.includes("none");
      const named = wanted.filter((b) => b !== "none");
      if (withNone && named.length) s = s.or(`sentiment_band.is.null,sentiment_band.in.(${named.join(",")})`);
      else if (withNone) s = s.is("sentiment_band", null);
      else if (named.length === 1) s = s.eq("sentiment_band", named[0]);
      else if (named.length) s = s.in("sentiment_band", named);
    }
    const col = CLASS_SORT_COLUMN[sort];
    const sortCol = v3 || !V3_COLUMNS.has(col) ? col : "class_date";
    s = s.order(sortCol, { ascending: dir === "asc", nullsFirst: false });
    if (sortCol !== "class_date") s = s.order("class_date", { ascending: false });
    s = s.order("id", { ascending: false });
    return s.range((page - 1) * pageSize, page * pageSize - 1);
  };

  let res = await build(true);
  let degraded = false;
  if (res.error) {
    res = await build(false);
    degraded = true;
  }
  const rows = ((res.data ?? []) as unknown as Raw[]).map(normalizeRating);
  return { rows, total: res.count ?? rows.length, page, pageSize, degraded };
}

/** The instructor's most recent classes before (and including) a date — the drawer's
 *  "last six". Matches by id when the row has one, else by the recorded name. */
export async function fetchInstructorRecent(
  row: Pick<ClassRating, "instructor" | "instructor_id" | "instructor_canonical" | "class_date" | "id">,
  limit = 6,
): Promise<ClassRating[]> {
  const supabase = await createClient();
  const name = row.instructor_canonical || row.instructor;
  if (!name && !row.instructor_id) return [];
  let s = supabase
    .from("class_ratings")
    .select(SELECT)
    .lte("class_date", row.class_date)
    .neq("id", row.id)
    .order("class_date", { ascending: false })
    .limit(limit);
  if (row.instructor_id) s = s.eq("instructor_id", row.instructor_id);
  else s = s.eq("instructor", name);
  const { data, error } = await s;
  if (error && row.instructor_id) {
    // instructor_id may not be populated yet — fall back to the name
    const alt = await supabase
      .from("class_ratings")
      .select(SELECT)
      .lte("class_date", row.class_date)
      .neq("id", row.id)
      .eq("instructor", name)
      .order("class_date", { ascending: false })
      .limit(limit);
    return ((alt.data ?? []) as unknown as Raw[]).map(normalizeRating);
  }
  return ((data ?? []) as unknown as Raw[]).map(normalizeRating);
}

/** Every class of the same module in the same course (last 180 days) — the module average. */
export async function fetchTopicRows(row: Pick<ClassRating, "topic" | "topic_id" | "course_id" | "class_date" | "id">, limit = 200): Promise<ClassRating[]> {
  const supabase = await createClient();
  if (!row.topic && !row.topic_id) return [];
  const since = new Date(new Date(row.class_date + "T00:00:00").getTime() - 180 * 86400000).toISOString().slice(0, 10);
  let s = supabase.from("class_ratings").select(SELECT).gte("class_date", since).neq("id", row.id).limit(limit);
  if (row.course_id) s = s.eq("course_id", row.course_id);
  if (row.topic_id) s = s.eq("topic_id", row.topic_id);
  else s = s.ilike("topic", row.topic.trim());
  const { data, error } = await s;
  if (error && row.topic_id) {
    let alt = supabase.from("class_ratings").select(SELECT).gte("class_date", since).neq("id", row.id).ilike("topic", row.topic.trim()).limit(limit);
    if (row.course_id) alt = alt.eq("course_id", row.course_id);
    return (((await alt).data ?? []) as unknown as Raw[]).map(normalizeRating);
  }
  return ((data ?? []) as unknown as Raw[]).map(normalizeRating);
}

export type ScoreHistoryRow = {
  id: string;
  scored_at: string | null;
  score: number | null;
  band: string | null;
  action: string | null;
  config_id: string | null;
  config_version: number | string | null;
  note: string | null;
};

/** `class_score_history` for one class (migration 0015); empty until the table exists. */
export async function fetchScoreHistory(classRatingId: string): Promise<ScoreHistoryRow[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("class_score_history")
    .select("*")
    .eq("class_rating_id", classRatingId)
    .order("scored_at", { ascending: false })
    .limit(20);
  if (error || !data) return [];
  return (data as Raw[]).map((h) => ({
    id: String(h.id ?? ""),
    scored_at: strOrNull(h.scored_at ?? h.created_at),
    score: numOrNull(h.sentiment_score ?? h.score),
    band: strOrNull(h.sentiment_band ?? h.band),
    action: strOrNull(h.sentiment_action ?? h.action),
    config_id: strOrNull(h.score_config_id ?? h.config_id),
    config_version: (h.config_version as number | string | null) ?? null,
    note: strOrNull(h.note ?? h.reason),
  }));
}

export type PingRow = { id: string; channel: string; recipient: string | null; status: string; sent_at: string; error: string | null };

/** The Slack ping history for one class (rating_notifications). */
export async function fetchPings(classRatingId: string): Promise<PingRow[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("rating_notifications")
    .select("id, channel, recipient, status, sent_at, error")
    .eq("class_rating_id", classRatingId)
    .order("sent_at", { ascending: false })
    .limit(20);
  if (error || !data) return [];
  return (data as Raw[]).map((p) => ({
    id: String(p.id),
    channel: String(p.channel ?? "slack"),
    recipient: strOrNull(p.recipient),
    status: String(p.status ?? "sent"),
    sent_at: String(p.sent_at ?? ""),
    error: strOrNull(p.error),
  }));
}

export async function lastSyncRun() {
  const supabase = await createClient();
  const { data } = await supabase
    .from("sync_runs")
    .select("id, source, trigger, status, rows_fetched, rows_upserted, rows_flagged, notifications_sent, unmapped_labels, error, started_at, finished_at")
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return data;
}

// ── identity helpers ──────────────────────────────────────────────────────────
/** One key per real person: the resolved id when the sync has one, else the recorded name. */
export const instructorKey = (r: Pick<ClassRating, "instructor_id" | "instructor" | "instructor_canonical">) =>
  r.instructor_id ?? `name:${r.instructor_canonical || r.instructor || "(unknown)"}`;
export const instructorName = (r: Pick<ClassRating, "instructor" | "instructor_canonical">) =>
  r.instructor_canonical || r.instructor || "(unknown)";

// ── aggregation helpers (pure) ────────────────────────────────────────────────
export const isBad = (r: ClassRating) => r.rating < GOOD;
/** Under the 80% approval bar with enough voices for the vote to count. */
export const isUnderBar = (r: ClassRating) =>
  r.approval_pct != null && r.approval_pct < APPROVAL_BAR && (r.num_ratings ?? 0) >= MIN_VOICES;
export const underBar = (rows: ClassRating[]) => rows.filter(isUnderBar);
const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

/** Pooled approval — every yes over every vote, not an average of percentages — so a class of
 *  four cannot outweigh a class of forty. Null when nobody in the set voted. */
export function approvalOf(rows: ClassRating[]): number | null {
  let yes = 0;
  let votes = 0;
  for (const r of rows) {
    if (r.yes_votes == null || r.no_votes == null) continue;
    yes += r.yes_votes;
    votes += r.yes_votes + r.no_votes;
  }
  return votes > 0 ? (yes / votes) * 100 : null;
}

export const votesOf = (rows: ClassRating[]) =>
  rows.reduce((a, r) => a + (r.yes_votes ?? 0) + (r.no_votes ?? 0), 0);

/** Average of the stored Class Sentiment Scores (null when none is scored yet). */
export const avgScore = (rows: ClassRating[]) =>
  avg(rows.map((r) => r.sentiment_score).filter((v): v is number => v != null));

export function bandCounts(rows: ClassRating[]): Record<Band, number> {
  const out: Record<Band, number> = { excellent: 0, good: 0, average: 0, bad: 0 };
  for (const r of rows) if (r.sentiment_band) out[r.sentiment_band] += 1;
  return out;
}

export function summarize(rows: ClassRating[]) {
  const bad = rows.filter(isBad);
  return {
    n: rows.length,
    avgRating: avg(rows.map((r) => r.rating)),
    avgScore: avgScore(rows),
    bands: bandCounts(rows),
    bad: bad.length,
    badShare: rows.length ? bad.length / rows.length : null,
    avgParticipation: avg(
      rows.map((r) => r.participation_pct).filter((v): v is number => v != null).map(Number),
    ),
    approval: approvalOf(rows),
    votes: votesOf(rows),
    underBar: underBar(rows).length,
  };
}

export function byCourse(rows: ClassRating[]) {
  const map = new Map<string, { key: string; name: string; courseId: string | null; slug: string | null; rows: ClassRating[] }>();
  for (const r of rows) {
    const key = r.course_id ?? `label:${r.course_label}`;
    const name = r.course_name ?? r.course_label;
    if (!map.has(key)) map.set(key, { key, name, courseId: r.course_id, slug: r.course_slug, rows: [] });
    map.get(key)!.rows.push(r);
  }
  return [...map.values()].map((c) => ({ ...c, ...summarize(c.rows) }));
}

/** Grouped by the resolved identity (`instructor_id`, else the name) so merged spellings unify. */
export function byInstructor(rows: ClassRating[]) {
  const map = new Map<string, { key: string; name: string; instructorId: string | null; aliases: Set<string>; rows: ClassRating[] }>();
  for (const r of rows) {
    const key = instructorKey(r);
    if (!map.has(key)) map.set(key, { key, name: instructorName(r), instructorId: r.instructor_id, aliases: new Set(), rows: [] });
    const g = map.get(key)!;
    g.rows.push(r);
    if (r.instructor && r.instructor !== g.name) g.aliases.add(r.instructor);
  }
  return [...map.values()].map((g) => ({
    key: g.key,
    name: g.name,
    instructorId: g.instructorId,
    aliases: [...g.aliases],
    rows: g.rows,
    ...summarize(g.rows),
  }));
}

/** yyyy-mm keys, ascending. */
export function byMonth(rows: ClassRating[]) {
  const map = new Map<string, ClassRating[]>();
  for (const r of rows) {
    const key = r.class_date.slice(0, 7);
    map.set(key, [...(map.get(key) ?? []), r]);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, list]) => ({ month, ...summarize(list) }));
}

export const BAND_DEFS = [
  { label: "Below 4.0|worst", test: (v: number) => v < 4.0 },
  { label: "4.0–4.24|poor", test: (v: number) => v >= 4.0 && v < 4.25 },
  { label: "4.25–4.54|weak", test: (v: number) => v >= 4.25 && v < GOOD },
  { label: "4.55–4.74|good", test: (v: number) => v >= GOOD && v < 4.75 },
  { label: "4.75+|excellent", test: (v: number) => v >= 4.75 },
];

export function bands(rows: ClassRating[]) {
  return BAND_DEFS.map((b) => ({
    label: b.label,
    count: rows.filter((r) => b.test(r.rating)).length,
  }));
}

export function liveVsReview(rows: ClassRating[]) {
  return (["Live Class", "Test Review"] as const).map((kind) => ({
    kind,
    ...summarize(rows.filter((r) => r.session_kind === kind)),
  }));
}

export function worstClasses(rows: ClassRating[], limit = 10) {
  return [...rows].filter(isBad).sort((a, b) => a.rating - b.rating).slice(0, limit);
}

// ── SME / module intelligence (the vision layer) ──────────────────────────────
/** Rows whose topic is a real module name (some sheet rows only carry the generic session label). */
const GENERIC_TOPICS = new Set(["", "live class", "test review session", "workshop", "session"]);
export function withRealTopics(rows: ClassRating[]) {
  return rows.filter((r) => !GENERIC_TOPICS.has(r.topic.trim().toLowerCase()));
}

/** Module-level view across ALL instructors — the "content issue vs instructor issue" detector:
 *  a module rated low by several different SMEs points at the material, not the person. */
export function byTopic(rows: ClassRating[], minClasses = 3) {
  const map = new Map<string, ClassRating[]>();
  for (const r of withRealTopics(rows)) {
    const key = r.topic.trim();
    map.set(key, [...(map.get(key) ?? []), r]);
  }
  return [...map.entries()]
    .map(([topic, list]) => ({
      topic,
      instructors: new Set(list.map(instructorKey)).size,
      ...summarize(list),
    }))
    .filter((t) => t.n >= minClasses);
}

/** One SME's per-topic record — strengths and improvement areas (vision point 1). */
export function smeTopics(rows: ClassRating[], instructor: string, minClasses = 2) {
  const own = withRealTopics(rows).filter((r) => instructorName(r) === instructor || r.instructor === instructor || instructorKey(r) === instructor);
  const map = new Map<string, ClassRating[]>();
  for (const r of own) map.set(r.topic.trim(), [...(map.get(r.topic.trim()) ?? []), r]);
  return [...map.entries()]
    .map(([topic, list]) => ({ topic, ...summarize(list) }))
    .filter((t) => t.n >= minClasses)
    .sort((a, b) => (b.avgRating ?? 0) - (a.avgRating ?? 0));
}

/** Best-known SME per module (vision point 4): among instructors with >= minClasses on the
 *  topic, the one with the highest average — the seed of the SME-to-module allocation map. */
export function bestSmePerTopic(rows: ClassRating[], minClasses = 3) {
  const byPair = new Map<string, Map<string, ClassRating[]>>();
  for (const r of withRealTopics(rows)) {
    if (!r.instructor && !r.instructor_id) continue;
    const t = r.topic.trim();
    if (!byPair.has(t)) byPair.set(t, new Map());
    const inner = byPair.get(t)!;
    const name = instructorName(r);
    inner.set(name, [...(inner.get(name) ?? []), r]);
  }
  const out: {
    topic: string; instructor: string; n: number; avgRating: number; approval: number | null; contenders: number;
  }[] = [];
  for (const [topic, inner] of byPair) {
    const qualified = [...inner.entries()]
      .map(([instructor, list]) => ({ instructor, ...summarize(list) }))
      .filter((x) => x.n >= minClasses && x.avgRating != null);
    if (qualified.length < 2) continue; // a "best" needs competition to mean anything
    qualified.sort((a, b) => (b.avgRating ?? 0) - (a.avgRating ?? 0));
    out.push({
      topic,
      instructor: qualified[0].instructor,
      n: qualified[0].n,
      avgRating: qualified[0].avgRating!,
      approval: qualified[0].approval,
      contenders: qualified.length,
    });
  }
  return out.sort((a, b) => b.avgRating - a.avgRating);
}
