import "server-only";
import { cache } from "react";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser, type SessionUser } from "@/lib/session";
import {
  TEAM_SLUG,
  TEAM_WORKSPACE,
  WS_COOKIE,
  courseColor,
  courseInitials,
  hrefIn,
  workspaceFor,
  type CourseSummary,
  type MemberRole,
  type Workspace,
} from "@/lib/workspace-shared";

export { hrefIn, TEAM_SLUG, WS_COOKIE, TEAM_WORKSPACE } from "@/lib/workspace-shared";
export type { CourseSummary, MemberRole, Workspace } from "@/lib/workspace-shared";
export { WorkspaceProvider } from "@/lib/workspace-context";

type Raw = Record<string, unknown>;

/** Every course with colour, initials, cohort count, handler and the user's membership — loaded
 *  ONCE per request (React cache) and shared by the shell, the layouts and the pages. Tables that
 *  are still being created (`course_members`, `courses.color`) simply contribute nothing. */
export const listCourses = cache(async function listCourses(): Promise<CourseSummary[]> {
  const supabase = await createClient();
  const user = await getCurrentUser();
  const [coursesRes, cohortsRes, membersRes, handlersRes] = await Promise.all([
    supabase.from("courses").select("*").order("name"),
    supabase.from("cohorts").select("course_id"),
    user ? supabase.from("course_members").select("*") : Promise.resolve({ data: null, error: null }),
    supabase.from("course_handlers").select("course_id, handler_email"),
  ]);
  const cohortCount = new Map<string, number>();
  for (const c of (cohortsRes.data ?? []) as Array<{ course_id: string }>) {
    cohortCount.set(c.course_id, (cohortCount.get(c.course_id) ?? 0) + 1);
  }
  const members = (membersRes.error ? [] : (membersRes.data ?? [])) as Raw[];
  const mine = new Map<string, MemberRole>();
  const handler = new Map<string, string>();
  for (const m of members) {
    const courseId = String(m.course_id ?? "");
    if (!courseId) continue;
    const isMe = user && (m.user_id === user.id || (m.email && String(m.email).toLowerCase() === user.email.toLowerCase()));
    if (isMe) {
      const role = (m.role as MemberRole) ?? "pm";
      const prev = mine.get(courseId);
      const rank: Record<MemberRole, number> = { owner: 0, pm: 1, viewer: 2 };
      if (!prev || rank[role] < rank[prev]) mine.set(courseId, role);
    }
    if (m.is_handler && !m.cohort_id) handler.set(courseId, String(m.display_name || m.email || ""));
  }
  if (!handlersRes.error) {
    for (const h of (handlersRes.data ?? []) as Array<{ course_id: string; handler_email: string }>) {
      if (!handler.has(h.course_id) && h.handler_email) handler.set(h.course_id, h.handler_email);
    }
  }
  return ((coursesRes.data ?? []) as Raw[]).map((c) => {
    const id = String(c.id);
    const name = String(c.name ?? "");
    const slug = String(c.slug ?? id);
    return {
      id,
      slug,
      name,
      color: courseColor(c.color == null ? null : String(c.color), slug),
      initials: courseInitials(c.initials == null ? null : String(c.initials), name),
      mine: mine.has(id),
      role: mine.get(id) ?? null,
      cohorts: cohortCount.get(id) ?? 0,
      handler: handler.get(id) ?? null,
    };
  });
});

/** The workspace for a slug: the course (with the member's role) or the team level for
 *  "team" / null. Unknown slugs 404. */
export const resolveWorkspace = cache(async function resolveWorkspace(slug: string | null | undefined): Promise<Workspace> {
  if (!slug || slug === TEAM_SLUG) return TEAM_WORKSPACE;
  const courses = await listCourses();
  const course = courses.find((c) => c.slug === slug) ?? courses.find((c) => c.id === slug);
  if (!course) notFound();
  return workspaceFor(course);
});

const isUuid = (s: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);

/** Where this person lands: the cookie (`fl_ws`), else `default_course_for(uid)`, else their
 *  first course, else the team level. Always returns a slug that exists. */
export async function getDefaultWorkspace(user: SessionUser): Promise<string> {
  const courses = await listCourses();
  const valid = (v: string | null | undefined): string | null => {
    if (!v) return null;
    if (v === TEAM_SLUG) return TEAM_SLUG;
    const hit = courses.find((c) => c.slug === v) ?? (isUuid(v) ? courses.find((c) => c.id === v) : undefined);
    return hit?.slug ?? null;
  };
  const store = await cookies();
  const fromCookie = valid(store.get(WS_COOKIE)?.value);
  if (fromCookie) return fromCookie;
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("default_course_for", { p_uid: user.id });
    if (!error && data != null) {
      const fromRpc = valid(String(data));
      if (fromRpc) return fromRpc;
    }
  } catch {
    // the RPC arrives with migration 0018 — fall through
  }
  if (user.role === "admin") return TEAM_SLUG;
  return courses.find((c) => c.mine)?.slug ?? courses[0]?.slug ?? TEAM_SLUG;
}

/** The workspace root URL for a slug. */
export const workspaceHome = (slug: string) => hrefIn(slug, "/overview");
