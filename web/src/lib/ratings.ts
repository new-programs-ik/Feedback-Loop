import "server-only";
import { createClient } from "@/lib/supabase/server";
import { GOOD } from "@/lib/decision";

/** Typed access + pure aggregation over class_ratings (the hourly-synced ratings feed).
 *  ~350 rows/month — in-process aggregation is fine; if volume ever grows, swap the fetchers
 *  for SQL views/rpc here without touching any page. */

export type ClassRating = {
  id: string;
  course_label: string;
  course_id: string | null;
  course_name: string | null;
  topic: string;
  instructor: string;
  class_date: string; // ISO yyyy-mm-dd
  session_kind: "Live Class" | "Test Review" | "Other" | string;
  rating: number;
  num_ratings: number | null;
  attended: number | null;
  participation_pct: number | null;
  escalated: boolean;
  decision: "none" | "watch" | "transcript" | "video";
  decision_override: "none" | "watch" | "transcript" | "video" | null;
  review_status: "new" | "notified" | "confirmed" | "dismissed" | "analysis_started";
  class_id: string | null;
  synced_at: string;
};

type Row = Omit<ClassRating, "course_name" | "rating"> & {
  rating: number | string;
  courses: { name: string } | null;
};

export async function fetchRatings(opts: {
  from: string;
  to: string;
  courseId?: string;
}): Promise<ClassRating[]> {
  const supabase = await createClient();
  // PostgREST caps every response at 1,000 rows — a full-year view is ~4,000+, so page through
  // explicitly or the data silently truncates (bug caught when "since January" showed 1,000).
  const PAGE = 1000;
  const all: Row[] = [];
  for (let page = 0; page < 20; page++) {
    let q = supabase
      .from("class_ratings")
      .select(
        "id, course_label, course_id, topic, instructor, class_date, session_kind, rating, num_ratings, attended, participation_pct, escalated, decision, decision_override, review_status, class_id, synced_at, courses(name)",
      )
      .gte("class_date", opts.from)
      .lte("class_date", opts.to)
      .order("class_date", { ascending: false })
      .order("id", { ascending: false })
      .range(page * PAGE, page * PAGE + PAGE - 1);
    if (opts.courseId) q = q.eq("course_id", opts.courseId);
    const { data } = await q;
    const batch = (data ?? []) as unknown as Row[];
    all.push(...batch);
    if (batch.length < PAGE) break;
  }
  return all.map((r) => ({
    ...r,
    rating: Number(r.rating),
    course_name: r.courses?.name ?? null,
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

// ── aggregation helpers (pure) ────────────────────────────────────────────────
export const isBad = (r: ClassRating) => r.rating < GOOD;
const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

export function summarize(rows: ClassRating[]) {
  const bad = rows.filter(isBad);
  return {
    n: rows.length,
    avgRating: avg(rows.map((r) => r.rating)),
    bad: bad.length,
    badShare: rows.length ? bad.length / rows.length : null,
    avgParticipation: avg(
      rows.map((r) => r.participation_pct).filter((v): v is number => v != null).map(Number),
    ),
  };
}

export function byCourse(rows: ClassRating[]) {
  const map = new Map<string, { key: string; name: string; courseId: string | null; rows: ClassRating[] }>();
  for (const r of rows) {
    const key = r.course_id ?? `label:${r.course_label}`;
    const name = r.course_name ?? r.course_label;
    if (!map.has(key)) map.set(key, { key, name, courseId: r.course_id, rows: [] });
    map.get(key)!.rows.push(r);
  }
  return [...map.values()].map((c) => ({ ...c, ...summarize(c.rows) }));
}

export function byInstructor(rows: ClassRating[]) {
  const map = new Map<string, ClassRating[]>();
  for (const r of rows) {
    const name = r.instructor || "(unknown)";
    map.set(name, [...(map.get(name) ?? []), r]);
  }
  return [...map.entries()].map(([name, list]) => ({ name, ...summarize(list) }));
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
      instructors: new Set(list.map((r) => r.instructor).filter(Boolean)).size,
      ...summarize(list),
    }))
    .filter((t) => t.n >= minClasses);
}

/** One SME's per-topic record — strengths and improvement areas (vision point 1). */
export function smeTopics(rows: ClassRating[], instructor: string, minClasses = 2) {
  const own = withRealTopics(rows).filter((r) => r.instructor === instructor);
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
    if (!r.instructor) continue;
    const t = r.topic.trim();
    if (!byPair.has(t)) byPair.set(t, new Map());
    const inner = byPair.get(t)!;
    inner.set(r.instructor, [...(inner.get(r.instructor) ?? []), r]);
  }
  const out: { topic: string; instructor: string; n: number; avgRating: number; contenders: number }[] = [];
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
      contenders: qualified.length,
    });
  }
  return out.sort((a, b) => b.avgRating - a.avgRating);
}
