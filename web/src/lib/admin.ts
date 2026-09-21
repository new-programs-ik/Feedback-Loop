import "server-only";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import {
  normalizeConfig,
  type ActionKind,
  type Band,
  type ScoringConfig,
} from "@/components/admin/scoring-config";

/** Data helpers for the admin and settings surfaces. Every reader here is TOLERANT of the
 *  additive migrations (0015 → 0021) not being applied yet: a missing table or column comes back
 *  as `{ rows: [], error }` — the page shows an honest empty state instead of a crash. Selects
 *  that need new columns try the full column list first and fall back to the columns that have
 *  existed since 0012/0014. */

export type Db = Awaited<ReturnType<typeof createClient>>;
type PgError = { message: string; code?: string; details?: string | null } | null;

/** Missing table / column / function, in any of the ways PostgREST reports it. */
export function isMissingSchema(error: PgError): boolean {
  if (!error) return false;
  const code = error.code ?? "";
  if (["42P01", "42703", "PGRST202", "PGRST204", "PGRST205"].includes(code)) return true;
  const m = error.message.toLowerCase();
  return m.includes("does not exist") || m.includes("could not find") || m.includes("schema cache");
}

/** Try each column list in turn until one the database accepts. */
async function selectWithFallback<T>(
  attempts: string[],
  run: (cols: string) => PromiseLike<{ data: unknown; error: PgError }>,
): Promise<{ rows: T[]; cols: string; error: string | null }> {
  let last: string | null = null;
  for (const cols of attempts) {
    const { data, error } = await run(cols);
    if (!error) return { rows: (data ?? []) as T[], cols, error: null };
    last = error.message;
    if (!isMissingSchema(error)) break;
  }
  return { rows: [], cols: attempts[attempts.length - 1], error: last };
}

const numOrNull = (v: unknown): number | null => (v == null || v === "" ? null : Number.isNaN(Number(v)) ? null : Number(v));

export async function auditLog(db: Db, actor: { id: string; email: string }, action: string, detail: object) {
  await db.from("audit_log").insert({ actor_id: actor.id, actor_label: actor.email, action, detail });
}

// ── courses ───────────────────────────────────────────────────────────────────
export type CourseRow = { id: string; slug: string; name: string; color: string | null; initials: string | null };

export async function getCourses(db?: Db): Promise<CourseRow[]> {
  const supabase = db ?? (await createClient());
  const { rows } = await selectWithFallback<Partial<CourseRow> & { id: string; slug: string; name: string }>(
    ["id, slug, name, color, initials", "id, slug, name"],
    (cols) => supabase.from("courses").select(cols).order("name"),
  );
  return rows.map((c) => ({ id: c.id, slug: c.slug, name: c.name, color: c.color ?? null, initials: c.initials ?? null }));
}

export async function getCourseBySlug(slug: string, db?: Db): Promise<CourseRow | null> {
  const courses = await getCourses(db);
  return courses.find((c) => c.slug === slug) ?? null;
}

// ── scoring configs ───────────────────────────────────────────────────────────
export type ScoringConfigRow = {
  id: string;
  version: number;
  key: string | null;
  name: string;
  status: "draft" | "active" | "retired";
  config: ScoringConfig;
  note: string | null;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  activated_at: string | null;
  retired_at: string | null;
  band_mix: Partial<Record<Band | "no_data", number>> | null;
};

async function profileNames(db: Db, ids: (string | null | undefined)[]): Promise<Map<string, string>> {
  const clean = [...new Set(ids.filter((v): v is string => !!v))];
  const map = new Map<string, string>();
  if (clean.length === 0) return map;
  const { data } = await db.from("profiles").select("user_id, full_name, email").in("user_id", clean);
  for (const p of (data ?? []) as { user_id: string; full_name: string | null; email: string | null }[])
    map.set(p.user_id, p.full_name || p.email || p.user_id.slice(0, 8));
  return map;
}

/** Band mix a version produced when it was applied — counted from class_score_history with
 *  five cheap HEAD requests (no aggregate support needed). Null when the history table is
 *  missing or the version never ran. */
async function historyBandMix(db: Db, configId: string): Promise<ScoringConfigRow["band_mix"]> {
  const keys: (Band | "no_data")[] = ["excellent", "good", "average", "bad", "no_data"];
  const results = await Promise.all(
    keys.map((k) => {
      let q = db.from("class_score_history").select("class_rating_id", { count: "exact", head: true }).eq("config_id", configId);
      q = k === "no_data" ? q.is("band", null) : q.eq("band", k);
      return q;
    }),
  );
  if (results.some((r) => r.error)) return null;
  const mix: Partial<Record<Band | "no_data", number>> = {};
  let total = 0;
  keys.forEach((k, i) => {
    mix[k] = results[i].count ?? 0;
    total += results[i].count ?? 0;
  });
  return total > 0 ? mix : null;
}

export async function listScoringConfigs(db?: Db): Promise<{ configs: ScoringConfigRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const { data, error } = await supabase
    .from("scoring_configs")
    .select("id, version, key, name, status, config, note, created_by, created_at, activated_at, retired_at")
    .order("version", { ascending: false });
  if (error) return { configs: [], error: error.message };
  type RawCfg = Omit<ScoringConfigRow, "config" | "created_by_name" | "band_mix"> & { config: unknown };
  const raw = (data ?? []) as RawCfg[];
  const names = await profileNames(supabase, raw.map((r) => r.created_by));
  const mixes = await Promise.all(raw.map((r) => (r.activated_at ? historyBandMix(supabase, r.id) : Promise.resolve(null))));
  const configs: ScoringConfigRow[] = raw.map((r, i) => ({
    ...r,
    config: normalizeConfig(r.config),
    created_by_name: r.created_by ? (names.get(r.created_by) ?? null) : null,
    band_mix: mixes[i],
  }));
  return { configs, error: null };
}

export async function getScoringConfig(id: string, db?: Db): Promise<ScoringConfigRow | null> {
  const { configs } = await listScoringConfigs(db);
  return configs.find((c) => c.id === id) ?? null;
}

// ── preview rows (the live what-if) ───────────────────────────────────────────
export type PreviewRow = {
  id: string;
  topic: string;
  instructor: string;
  course_id: string | null;
  course_name: string;
  class_date: string;
  session_kind: string;
  rating: number;
  num_ratings: number | null;
  attended: number | null;
  yes_votes: number | null;
  no_votes: number | null;
  escalated: boolean;
  track_avg: number | null;
  prior_rating: number | null;
  prior_approval: number | null;
  /** What the queue does with this class TODAY: the stored action when the row is scored, else
   *  the legacy rule's decision. */
  current_action: ActionKind | null;
  current_band: Band | null;
  current_score: number | null;
  review_status: string;
};

export type PreviewPayload = {
  rows: PreviewRow[];
  from: string;
  to: string;
  scored_columns: boolean;
  global_prior: { rating: number | null; approval: number | null };
  error: string | null;
};

const BASE_COLS =
  "id, topic, instructor, course_id, course_label, class_date, session_kind, rating, num_ratings, attended, yes_votes, no_votes, escalated, track_avg, decision, review_status, courses(name)";

/** Every rated class in [from, to] with the inputs the score needs, plus the course's typical
 *  rating / pooled approval over the same window (the guard's prior). Paged past the 1,000-row
 *  PostgREST cap; capped at 6,000 rows (≈ 15 months) to keep the browser preview instant. */
export async function fetchPreviewRows(from: string, to: string, db?: Db): Promise<PreviewPayload> {
  const supabase = db ?? (await createClient());
  type Raw = {
    id: string; topic: string; instructor: string; course_id: string | null; course_label: string; class_date: string;
    session_kind: string; rating: number | string; num_ratings: number | null; attended: number | null;
    yes_votes: number | null; no_votes: number | null; escalated: boolean; track_avg: number | string | null;
    decision: string | null; review_status: string; courses: { name: string } | null;
    score?: number | string | null; band?: string | null; action?: string | null;
  };
  const PAGE = 1000;
  const all: Raw[] = [];
  let scored = false;
  let error: string | null = null;
  let cols: string | null = null;
  for (let page = 0; page < 6; page++) {
    const attempts: string[] = cols ? [cols] : [`${BASE_COLS}, score, band, action`, `${BASE_COLS}, score, band`, BASE_COLS];
    const res: { rows: Raw[]; cols: string; error: string | null } = await selectWithFallback<Raw>(attempts, (c) =>
      supabase
        .from("class_ratings")
        .select(c)
        .gte("class_date", from)
        .lte("class_date", to)
        .order("class_date", { ascending: false })
        .order("id", { ascending: false })
        .range(page * PAGE, page * PAGE + PAGE - 1),
    );
    if (res.error) {
      error = res.error;
      break;
    }
    cols = res.cols;
    scored = res.cols.includes("score");
    all.push(...res.rows);
    if (res.rows.length < PAGE) break;
  }

  // Course priors: mean rating and pooled approval per course over the window.
  const groups = new Map<string, { ratings: number[]; yes: number; votes: number }>();
  const keyOf = (r: Raw) => r.course_id ?? `label:${r.course_label}`;
  const gRatings: number[] = [];
  let gYes = 0, gVotes = 0;
  for (const r of all) {
    const k = keyOf(r);
    const g = groups.get(k) ?? { ratings: [], yes: 0, votes: 0 };
    const rating = Number(r.rating);
    if (Number.isFinite(rating) && rating > 0) {
      g.ratings.push(rating);
      gRatings.push(rating);
    }
    if (r.yes_votes != null && r.no_votes != null && r.yes_votes + r.no_votes > 0) {
      g.yes += r.yes_votes;
      g.votes += r.yes_votes + r.no_votes;
      gYes += r.yes_votes;
      gVotes += r.yes_votes + r.no_votes;
    }
    groups.set(k, g);
  }
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
  const priorOf = (k: string) => {
    const g = groups.get(k);
    if (!g) return { rating: null, approval: null };
    return { rating: mean(g.ratings), approval: g.votes > 0 ? (g.yes / g.votes) * 100 : null };
  };
  const ACTIONS: ActionKind[] = ["video", "transcript", "none", "watch"];
  const BANDS: Band[] = ["excellent", "good", "average", "bad"];
  const rows: PreviewRow[] = all.map((r) => {
    const prior = priorOf(keyOf(r));
    const action = (r.action ?? r.decision) as string | null;
    return {
      id: r.id,
      topic: r.topic,
      instructor: r.instructor,
      course_id: r.course_id,
      course_name: r.courses?.name ?? r.course_label,
      class_date: r.class_date,
      session_kind: r.session_kind,
      rating: Number(r.rating),
      num_ratings: r.num_ratings,
      attended: r.attended,
      yes_votes: r.yes_votes,
      no_votes: r.no_votes,
      escalated: !!r.escalated,
      track_avg: numOrNull(r.track_avg),
      prior_rating: prior.rating,
      prior_approval: prior.approval,
      current_action: action && (ACTIONS as string[]).includes(action) ? (action as ActionKind) : null,
      current_band: r.band && (BANDS as string[]).includes(r.band) ? (r.band as Band) : null,
      current_score: numOrNull(r.score),
      review_status: r.review_status,
    };
  });
  return {
    rows,
    from,
    to,
    scored_columns: scored,
    global_prior: { rating: mean(gRatings), approval: gVotes > 0 ? (gYes / gVotes) * 100 : null },
    error,
  };
}

// ── identity ──────────────────────────────────────────────────────────────────
export type InstructorRow = { id: string; name: string; merged_into: string | null };

export async function listInstructors(db?: Db): Promise<{ rows: InstructorRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const res = await selectWithFallback<Partial<InstructorRow> & { id: string; name: string }>(
    ["id, name, merged_into", "id, name"],
    (cols) => supabase.from("instructors").select(cols).order("name"),
  );
  return {
    rows: res.rows.map((r) => ({ id: r.id, name: r.name, merged_into: r.merged_into ?? null })).filter((r) => !r.merged_into),
    error: res.error,
  };
}

export type SuggestionRow = {
  id: string;
  raw_name: string;
  raw_norm: string | null;
  candidate_instructor_id: string;
  candidate_name: string;
  score: number;
  method: string | null;
  evidence: Record<string, unknown> | null;
  status: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  /** The spelling is an instructor record's own name — accepting merges the two records (undoable). */
  raw_has_record: boolean;
};

export async function listPendingSuggestions(db?: Db): Promise<{ rows: SuggestionRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const { data, error } = await supabase
    .from("instructor_match_suggestions")
    .select("id, raw_name, raw_norm, candidate_instructor_id, score, method, evidence, status, first_seen_at, last_seen_at")
    .eq("status", "pending")
    .order("score", { ascending: false })
    .limit(300);
  if (error) return { rows: [], error: error.message };
  type RawSug = Omit<SuggestionRow, "candidate_name" | "score"> & { score: number | string };
  const raw = (data ?? []) as RawSug[];
  const ids = [...new Set(raw.map((r) => r.candidate_instructor_id))];
  const names = new Map<string, string>();
  if (ids.length) {
    const { data: ins } = await supabase.from("instructors").select("id, name").in("id", ids);
    for (const i of (ins ?? []) as { id: string; name: string }[]) names.set(i.id, i.name);
  }
  const norms = [...new Set(raw.map((r) => r.raw_norm).filter((n): n is string => !!n))];
  const own = new Set<string>();
  if (norms.length) {
    const { data: recs } = await supabase.from("instructors").select("normalized_name").in("normalized_name", norms).is("merged_into", null);
    for (const r of (recs ?? []) as { normalized_name: string }[]) own.add(r.normalized_name);
  }
  return {
    rows: raw.map((r) => ({
      ...r,
      score: Number(r.score),
      candidate_name: names.get(r.candidate_instructor_id) ?? "(unknown)",
      raw_has_record: !!r.raw_norm && own.has(r.raw_norm) && !(names.get(r.candidate_instructor_id) && normalizeLike(names.get(r.candidate_instructor_id)!) === r.raw_norm),
    })),
    error: null,
  };
}

const normalizeLike = (s: string) =>
  s
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

export type NameStats = {
  classes: number;
  first: string | null;
  last: string | null;
  avg_score: number | null;
  avg_rating: number | null;
  top_modules: { topic: string; n: number }[];
};

const emptyStats = (): NameStats => ({ classes: 0, first: null, last: null, avg_score: null, avg_rating: null, top_modules: [] });

function foldStats(rows: { class_date: string; rating: number | string; score?: number | string | null; topic: string }[]): NameStats {
  if (rows.length === 0) return emptyStats();
  const dates = rows.map((r) => r.class_date).sort();
  const ratings = rows.map((r) => Number(r.rating)).filter((v) => Number.isFinite(v));
  const scores = rows.map((r) => numOrNull(r.score ?? null)).filter((v): v is number => v != null);
  const topics = new Map<string, number>();
  for (const r of rows) {
    const t = r.topic.trim();
    if (!t || ["live class", "test review session"].includes(t.toLowerCase())) continue;
    topics.set(t, (topics.get(t) ?? 0) + 1);
  }
  return {
    classes: rows.length,
    first: dates[0],
    last: dates[dates.length - 1],
    avg_rating: ratings.length ? ratings.reduce((a, b) => a + b, 0) / ratings.length : null,
    avg_score: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    top_modules: [...topics.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([topic, n]) => ({ topic, n })),
  };
}

/** Class history behind a set of raw names (matched on the recorded spelling) and a set of
 *  resolved instructor ids — what the side-by-side duplicate cards show. */
export async function instructorHistory(
  rawNames: string[],
  instructorIds: string[],
  db?: Db,
): Promise<{ byName: Map<string, NameStats>; byId: Map<string, NameStats> }> {
  const supabase = db ?? (await createClient());
  type R = { instructor: string; instructor_id: string | null; class_date: string; rating: number | string; score?: number | string | null; topic: string };
  const attempts = ["instructor, instructor_id, class_date, rating, score, topic", "instructor, instructor_id, class_date, rating, topic"];
  const byName = new Map<string, NameStats>();
  const byId = new Map<string, NameStats>();
  const names = [...new Set(rawNames.filter(Boolean))];
  const ids = [...new Set(instructorIds.filter(Boolean))];
  const chunk = <T,>(xs: T[], n: number) => Array.from({ length: Math.ceil(xs.length / n) }, (_, i) => xs.slice(i * n, i * n + n));
  const nameRows: R[] = [];
  for (const part of chunk(names, 100)) {
    const res = await selectWithFallback<R>(attempts, (cols) => supabase.from("class_ratings").select(cols).in("instructor", part).limit(5000));
    nameRows.push(...res.rows);
  }
  const idRows: R[] = [];
  for (const part of chunk(ids, 100)) {
    const res = await selectWithFallback<R>(attempts, (cols) => supabase.from("class_ratings").select(cols).in("instructor_id", part).limit(5000));
    idRows.push(...res.rows);
  }
  for (const n of names) byName.set(n, foldStats(nameRows.filter((r) => r.instructor === n)));
  for (const id of ids) byId.set(id, foldStats(idRows.filter((r) => r.instructor_id === id)));
  return { byName, byId };
}

export type UnresolvedName = { name: string; classes: number; last: string | null };

/** Raw instructor spellings on rated classes that no instructor row claims yet. */
export async function listUnresolvedNames(db?: Db, sinceDays = 400): Promise<{ rows: UnresolvedName[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const since = new Date(Date.now() - sinceDays * 86400000).toISOString().slice(0, 10);
  const PAGE = 1000;
  const counts = new Map<string, { n: number; last: string }>();
  for (let page = 0; page < 8; page++) {
    const { data, error } = await supabase
      .from("class_ratings")
      .select("instructor, class_date")
      .is("instructor_id", null)
      .gte("class_date", since)
      .neq("instructor", "")
      .order("class_date", { ascending: false })
      .range(page * PAGE, page * PAGE + PAGE - 1);
    if (error) return { rows: [], error: error.message };
    const batch = (data ?? []) as { instructor: string; class_date: string }[];
    for (const r of batch) {
      const cur = counts.get(r.instructor) ?? { n: 0, last: r.class_date };
      cur.n += 1;
      if (r.class_date > cur.last) cur.last = r.class_date;
      counts.set(r.instructor, cur);
    }
    if (batch.length < PAGE) break;
  }
  return {
    rows: [...counts.entries()].map(([name, c]) => ({ name, classes: c.n, last: c.last })).sort((a, b) => b.classes - a.classes),
    error: null,
  };
}

export type MergeRow = {
  id: string;
  from_instructor_id: string;
  into_instructor_id: string;
  from_name: string;
  into_name: string;
  moved: Record<string, unknown> | null;
  performed_by: string | null;
  performed_by_name: string | null;
  performed_at: string;
  undone_at: string | null;
  undoable: boolean;
};

export async function listRecentMerges(db?: Db): Promise<{ rows: MergeRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const { data, error } = await supabase
    .from("instructor_merges")
    .select("id, from_instructor_id, into_instructor_id, moved, performed_by, performed_at, undone_by, undone_at")
    .order("performed_at", { ascending: false })
    .limit(30);
  if (error) return { rows: [], error: error.message };
  const raw = (data ?? []) as Omit<MergeRow, "from_name" | "into_name" | "performed_by_name" | "undoable">[];
  const ids = [...new Set(raw.flatMap((r) => [r.from_instructor_id, r.into_instructor_id]))];
  const names = new Map<string, string>();
  if (ids.length) {
    const { data: ins } = await supabase.from("instructors").select("id, name").in("id", ids);
    for (const i of (ins ?? []) as { id: string; name: string }[]) names.set(i.id, i.name);
  }
  const people = await profileNames(supabase, raw.map((r) => r.performed_by));
  const cutoff = Date.now() - 30 * 86400000;
  return {
    rows: raw.map((r) => ({
      ...r,
      from_name: names.get(r.from_instructor_id) ?? "(removed)",
      into_name: names.get(r.into_instructor_id) ?? "(removed)",
      performed_by_name: r.performed_by ? (people.get(r.performed_by) ?? null) : null,
      undoable: !r.undone_at && +new Date(r.performed_at) > cutoff,
    })),
    error: null,
  };
}

/** What a merge would move: rated classes, analysed classes, aliases on the duplicate. */
export async function mergePreview(fromId: string, db?: Db) {
  const supabase = db ?? (await createClient());
  const [ratings, classes, aliases] = await Promise.all([
    supabase.from("class_ratings").select("id", { count: "exact", head: true }).eq("instructor_id", fromId),
    supabase.from("classes").select("id", { count: "exact", head: true }).eq("instructor_id", fromId),
    supabase.from("instructor_aliases").select("id", { count: "exact", head: true }).eq("instructor_id", fromId),
  ]);
  return {
    ratings: ratings.count ?? 0,
    classes: classes.count ?? 0,
    aliases: aliases.error ? null : (aliases.count ?? 0),
  };
}

// ── people ────────────────────────────────────────────────────────────────────
export type MemberRole = "owner" | "pm" | "viewer";
export type MemberRow = {
  id: string;
  course_id: string;
  cohort_id: string | null;
  user_id: string | null;
  email: string;
  display_name: string | null;
  role: MemberRole;
  is_handler: boolean;
  notify_slack: boolean;
  slack_user_id: string | null;
  added_by: string | null;
  created_at: string;
  updated_at: string | null;
  handed_over_from: string | null;
  handed_over_at: string | null;
};

export async function listMembers(courseId?: string, db?: Db): Promise<{ rows: MemberRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  let q = supabase.from("course_members").select("*").order("created_at");
  if (courseId) q = q.eq("course_id", courseId);
  const { data, error } = await q;
  if (error) return { rows: [], error: error.message };
  return { rows: (data ?? []) as MemberRow[], error: null };
}

export type CohortRow = {
  id: string;
  course_id: string;
  name: string;
  region: string | null;
  start_month: string | null;
  cohort_key: string | null;
};

export async function listCohorts(courseId?: string, db?: Db): Promise<{ rows: CohortRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const res = await selectWithFallback<Partial<CohortRow> & { id: string; course_id: string; name: string }>(
    ["id, course_id, name, region, start_month, cohort_key", "id, course_id, name"],
    (cols) => {
      let q = supabase.from("cohorts").select(cols).order("name");
      if (courseId) q = q.eq("course_id", courseId);
      return q;
    },
  );
  return {
    rows: res.rows.map((c) => ({
      id: c.id,
      course_id: c.course_id,
      name: c.name,
      region: c.region ?? null,
      start_month: c.start_month ?? null,
      cohort_key: c.cohort_key ?? null,
    })),
    error: res.error,
  };
}

export const IK_EMAIL = /^[a-z0-9._%+-]+@interviewkickstart\.com$/i;

/** Insert a member row (shared by the admin People page and each course's Team tab). Links the
 *  login when the person has already signed in; otherwise the row waits on `email` alone. */
export async function insertMember(
  db: Db,
  input: { courseId: string; email: string; role: MemberRole; cohortId?: string | null; addedBy: string },
): Promise<{ id: string; error: null } | { id: null; error: string }> {
  const email = input.email.trim().toLowerCase();
  if (!IK_EMAIL.test(email)) return { id: null, error: "Only @interviewkickstart.com addresses can be added." };
  const { data: profile } = await db.from("profiles").select("user_id, full_name").ilike("email", email).maybeSingle();
  const p = profile as { user_id: string; full_name: string | null } | null;
  const display = p?.full_name || email.split("@")[0].split(".").map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(" ");
  const { data, error } = await db
    .from("course_members")
    .insert({
      course_id: input.courseId,
      cohort_id: input.cohortId || null,
      user_id: p?.user_id ?? null,
      email,
      display_name: display,
      role: input.role,
      is_handler: false,
      notify_slack: true,
      added_by: input.addedBy,
    })
    .select("id")
    .single();
  if (error) {
    const dup = error.code === "23505" || error.message.toLowerCase().includes("duplicate");
    return { id: null, error: dup ? `${email} is already on this course.` : error.message };
  }
  return { id: (data as { id: string }).id, error: null };
}

/** Exactly one handler per course: clear the others, then set this one. Returns an error string
 *  or null. */
export async function makeHandler(db: Db, courseId: string, memberId: string): Promise<string | null> {
  const clear = await db
    .from("course_members")
    .update({ is_handler: false, updated_at: new Date().toISOString() })
    .eq("course_id", courseId)
    .neq("id", memberId);
  if (clear.error) return clear.error.message;
  const set = await db
    .from("course_members")
    .update({ is_handler: true, updated_at: new Date().toISOString() })
    .eq("id", memberId)
    .eq("course_id", courseId);
  return set.error ? set.error.message : null;
}

/** Staff who have signed in at least once (profiles are IK-only). Feeds the add-member typeahead. */
export async function listStaffProfiles(db?: Db): Promise<{ user_id: string; full_name: string | null; email: string | null }[]> {
  const supabase = db ?? (await createClient());
  const { data } = await supabase.from("profiles").select("user_id, full_name, email").order("full_name");
  return ((data ?? []) as { user_id: string; full_name: string | null; email: string | null }[]).filter((p) =>
    (p.email ?? "").toLowerCase().endsWith("@interviewkickstart.com"),
  );
}

// ── modules (topics) ──────────────────────────────────────────────────────────
export type TopicRow = { id: string; name: string; course_id: string | null };
export type TopicAliasRow = { id: string; alias: string; topic_id: string; topic_name: string | null };

export async function listTopics(courseId: string, db?: Db): Promise<{ rows: TopicRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const res = await selectWithFallback<Partial<TopicRow> & { id: string; name: string }>(
    ["id, name, course_id", "id, name"],
    (cols) => supabase.from("topics").select(cols).order("name").limit(1000),
  );
  return {
    rows: res.rows
      .map((t) => ({ id: t.id, name: t.name, course_id: t.course_id ?? null }))
      .filter((t) => t.course_id == null || t.course_id === courseId),
    error: res.error,
  };
}

export async function listTopicAliases(topicIds: string[], db?: Db): Promise<{ rows: TopicAliasRow[]; error: string | null }> {
  if (topicIds.length === 0) return { rows: [], error: null };
  const supabase = db ?? (await createClient());
  const { data, error } = await supabase.from("topic_aliases").select("id, alias, topic_id").in("topic_id", topicIds).limit(2000);
  if (error) return { rows: [], error: error.message };
  return { rows: ((data ?? []) as Omit<TopicAliasRow, "topic_name">[]).map((a) => ({ ...a, topic_name: null })), error: null };
}

export type RawTopic = { topic: string; classes: number; last: string | null };

/** Distinct class names recorded on this course's rated classes (last 12 months). */
export async function listRawTopics(courseId: string, db?: Db): Promise<RawTopic[]> {
  const supabase = db ?? (await createClient());
  const since = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
  const PAGE = 1000;
  const counts = new Map<string, { n: number; last: string }>();
  for (let page = 0; page < 6; page++) {
    const { data, error } = await supabase
      .from("class_ratings")
      .select("topic, class_date")
      .eq("course_id", courseId)
      .gte("class_date", since)
      .order("class_date", { ascending: false })
      .range(page * PAGE, page * PAGE + PAGE - 1);
    if (error) break;
    const batch = (data ?? []) as { topic: string; class_date: string }[];
    for (const r of batch) {
      const t = r.topic.trim();
      if (!t || ["live class", "test review session"].includes(t.toLowerCase())) continue;
      const cur = counts.get(t) ?? { n: 0, last: r.class_date };
      cur.n += 1;
      if (r.class_date > cur.last) cur.last = r.class_date;
      counts.set(t, cur);
    }
    if (batch.length < PAGE) break;
  }
  return [...counts.entries()].map(([topic, c]) => ({ topic, classes: c.n, last: c.last })).sort((a, b) => b.classes - a.classes);
}

// ── sync ──────────────────────────────────────────────────────────────────────
export type SyncRunRow = {
  id: string;
  source: string;
  trigger: string;
  status: string;
  rows_fetched: number | null;
  rows_upserted: number | null;
  rows_unchanged?: number | null;
  rows_flagged: number | null;
  rows_scored?: number | null;
  scoring_config_version?: number | null;
  band_counts?: Record<string, number> | null;
  cohorts_created?: number | null;
  cohorts_unparsed?: number | null;
  instructors_unresolved?: number | null;
  suggestions_created?: number | null;
  topics_unmapped?: number | null;
  duration_ms?: number | null;
  notifications_sent: number | null;
  unmapped_labels: string[] | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
};

export async function listSyncRuns(limit = 25, db?: Db): Promise<{ rows: SyncRunRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  const { data, error } = await supabase.from("sync_runs").select("*").order("started_at", { ascending: false }).limit(limit);
  if (error) return { rows: [], error: error.message };
  return { rows: (data ?? []) as SyncRunRow[], error: null };
}

/** Scheduled runs the worker never took: a token was minted for them but never spent. Read
 *  with the service role (the table has no policies on purpose). */
export async function listUnspentTriggers(hours = 48): Promise<{ trigger: string; created_at: string }[]> {
  try {
    const admin = createAdminClient();
    const since = new Date(Date.now() - hours * 3_600_000).toISOString();
    const { data, error } = await admin
      .from("sync_triggers")
      .select("trigger, created_at")
      .is("used_at", null)
      .gte("created_at", since)
      .lt("created_at", new Date(Date.now() - 2 * 60_000).toISOString())   // give a fresh one two minutes
      .order("created_at", { ascending: false })
      .limit(20);
    if (error) return [];
    return (data ?? []) as { trigger: string; created_at: string }[];
  } catch {
    return [];
  }
}

export async function listUnmappedLabels(db?: Db): Promise<{ label: string; classes: number }[]> {
  const supabase = db ?? (await createClient());
  const { data } = await supabase.from("class_ratings").select("course_label").is("course_id", null).limit(5000);
  const counts = new Map<string, number>();
  for (const r of (data ?? []) as { course_label: string }[]) counts.set(r.course_label, (counts.get(r.course_label) ?? 0) + 1);
  return [...counts.entries()].map(([label, classes]) => ({ label, classes })).sort((a, b) => b.classes - a.classes);
}

const SYNC_ASLEEP = "Could not reach the sync service — it may be waking up; try again in a minute.";

/** POST /sync-ratings on the worker. Null on success, else the friendly reason. (Copied from the
 *  queue's actions so the admin surfaces do not depend on where C1 moves that file.) */
export async function askWorkerToSync(): Promise<string | null> {
  const workerUrl = process.env.ANALYSIS_WORKER_URL || "http://localhost:8000";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.WORKER_API_KEY) headers.Authorization = `Bearer ${process.env.WORKER_API_KEY}`;
  try {
    const res = await fetch(`${workerUrl}/sync-ratings`, {
      method: "POST",
      headers,
      body: JSON.stringify({ trigger: "manual" }),
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) throw new Error(`worker said ${res.status}`);
    return null;
  } catch {
    return SYNC_ASLEEP;
  }
}

// ── audit ─────────────────────────────────────────────────────────────────────
export type AuditRow = {
  id: string;
  class_id: string | null;
  actor_id: string | null;
  actor_label: string | null;
  actor_name: string | null;
  action: string;
  detail: Record<string, unknown> | null;
  created_at: string;
};

export async function listAudit(opts: { page: number; pageSize: number; action?: string; db?: Db }) {
  const supabase = opts.db ?? (await createClient());
  const from = opts.page * opts.pageSize;
  let q = supabase
    .from("audit_log")
    .select("id, class_id, actor_id, actor_label, action, detail, created_at", { count: "exact" })
    .order("created_at", { ascending: false })
    .range(from, from + opts.pageSize - 1);
  if (opts.action) q = q.eq("action", opts.action);
  const { data, error, count } = await q;
  if (error) return { rows: [] as AuditRow[], total: 0, error: error.message };
  const raw = (data ?? []) as Omit<AuditRow, "actor_name">[];
  const names = await profileNames(supabase, raw.map((r) => r.actor_id));
  return {
    rows: raw.map((r) => ({ ...r, actor_name: r.actor_id ? (names.get(r.actor_id) ?? null) : null })),
    total: count ?? 0,
    error: null,
  };
}

// ── shares ────────────────────────────────────────────────────────────────────
export type SharePeriod = { kind: "weekly" | "monthly" | "custom"; from: string; to: string; label?: string; require_login?: boolean };
export type ShareRow = {
  id: string;
  token: string;
  course_id: string | null;
  period: SharePeriod;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
};

export async function listShares(courseId: string | null | undefined, db?: Db): Promise<{ rows: ShareRow[]; error: string | null }> {
  const supabase = db ?? (await createClient());
  let q = supabase
    .from("report_shares")
    .select("id, token, course_id, period, created_by, created_at, expires_at, revoked_at")
    .order("created_at", { ascending: false })
    .limit(100);
  if (courseId) q = q.eq("course_id", courseId);
  const { data, error } = await q;
  if (error) return { rows: [], error: error.message };
  const raw = (data ?? []) as Omit<ShareRow, "created_by_name">[];
  const names = await profileNames(supabase, raw.map((r) => r.created_by));
  return { rows: raw.map((r) => ({ ...r, created_by_name: r.created_by ? (names.get(r.created_by) ?? null) : null })), error: null };
}

/** live / expired / revoked for a share row (time-dependent, so it lives here, not in render). */
export function shareState(share: Pick<ShareRow, "expires_at" | "revoked_at">): "live" | "expired" | "revoked" {
  if (share.revoked_at) return "revoked";
  if (share.expires_at && +new Date(share.expires_at) < Date.now()) return "expired";
  return "live";
}

/** Token lookup for the read-only report. Uses the service role: the token IS the secret and the
 *  page already requires an IK sign-in, so the row must be found whatever RLS says about the
 *  reader. */
export async function getShareByToken(token: string): Promise<ShareRow | null> {
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(token)) return null;
  const admin = createAdminClient();
  const { data } = await admin
    .from("report_shares")
    .select("id, token, course_id, period, created_by, created_at, expires_at, revoked_at")
    .eq("token", token)
    .maybeSingle();
  if (!data) return null;
  const row = data as Omit<ShareRow, "created_by_name">;
  let created_by_name: string | null = null;
  if (row.created_by) {
    const { data: p } = await admin.from("profiles").select("full_name, email").eq("user_id", row.created_by).maybeSingle();
    created_by_name = (p as { full_name: string | null; email: string | null } | null)?.full_name ?? (p as { email: string | null } | null)?.email ?? null;
  }
  return { ...row, created_by_name };
}

export type ShareClassRow = {
  id: string;
  topic: string;
  instructor: string;
  course_name: string;
  class_date: string;
  session_kind: string;
  rating: number;
  num_ratings: number | null;
  attended: number | null;
  yes_votes: number | null;
  no_votes: number | null;
  score: number | null;
  band: Band | null;
  action: ActionKind | null;
  review_status: string;
};

/** The rows a shared report renders — read with the signed-in reader's own client (staff can read
 *  every course) and tolerant of the scoring columns not existing yet. */
export async function fetchShareRows(from: string, to: string, courseId: string | null, db?: Db): Promise<ShareClassRow[]> {
  const supabase = db ?? (await createClient());
  type Raw = {
    id: string; topic: string; instructor: string; course_label: string; class_date: string; session_kind: string;
    rating: number | string; num_ratings: number | null; attended: number | null; yes_votes: number | null; no_votes: number | null;
    decision: string | null; review_status: string; courses: { name: string } | null; score?: number | string | null; band?: string | null; action?: string | null;
  };
  const base = "id, topic, instructor, course_label, class_date, session_kind, rating, num_ratings, attended, yes_votes, no_votes, decision, review_status, courses(name)";
  const PAGE = 1000;
  const out: ShareClassRow[] = [];
  let cols: string | null = null;
  for (let page = 0; page < 4; page++) {
    const attempts: string[] = cols ? [cols] : [`${base}, score, band, action`, `${base}, score, band`, base];
    const res: { rows: Raw[]; cols: string; error: string | null } = await selectWithFallback<Raw>(attempts, (c) => {
      let q = supabase
        .from("class_ratings")
        .select(c)
        .gte("class_date", from)
        .lte("class_date", to)
        .order("class_date", { ascending: false })
        .order("id", { ascending: false })
        .range(page * PAGE, page * PAGE + PAGE - 1);
      if (courseId) q = q.eq("course_id", courseId);
      return q;
    });
    if (res.error) break;
    cols = res.cols;
    for (const r of res.rows) {
      const band = r.band ?? null;
      const action = (r.action ?? r.decision) ?? null;
      out.push({
        id: r.id,
        topic: r.topic,
        instructor: r.instructor,
        course_name: r.courses?.name ?? r.course_label,
        class_date: r.class_date,
        session_kind: r.session_kind,
        rating: Number(r.rating),
        num_ratings: r.num_ratings,
        attended: r.attended,
        yes_votes: r.yes_votes,
        no_votes: r.no_votes,
        score: numOrNull(r.score ?? null),
        band: band && ["excellent", "good", "average", "bad"].includes(band) ? (band as Band) : null,
        action: action && ["video", "transcript", "none", "watch"].includes(action) ? (action as ActionKind) : null,
        review_status: r.review_status,
      });
    }
    if (res.rows.length < PAGE) break;
  }
  return out;
}
