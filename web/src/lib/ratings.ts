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
  let q = supabase
    .from("class_ratings")
    .select(
      "id, course_label, course_id, topic, instructor, class_date, session_kind, rating, num_ratings, attended, participation_pct, escalated, decision, decision_override, review_status, class_id, synced_at, courses(name)",
    )
    .gte("class_date", opts.from)
    .lte("class_date", opts.to)
    .order("class_date", { ascending: false });
  if (opts.courseId) q = q.eq("course_id", opts.courseId);
  const { data } = await q;
  return ((data ?? []) as unknown as Row[]).map((r) => ({
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
