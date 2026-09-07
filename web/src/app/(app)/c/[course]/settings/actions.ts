"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser, type SessionUser } from "@/lib/session";
import { auditLog, insertMember, makeHandler, type Db, type MemberRole } from "@/lib/admin";

/** Course-scoped settings. Writing needs membership: an app admin, or an `owner` of this course.
 *  Everything returns a value (never throws) so the toast can show the real reason. */
export type SettingsResult<T = null> = { ok: true; data: T } | { ok: false; error: string };

const fail = (error: string): { ok: false; error: string } => ({ ok: false, error });
const done = <T,>(data: T): { ok: true; data: T } => ({ ok: true, data });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ROLES: MemberRole[] = ["owner", "pm", "viewer"];

async function editor(courseId: string): Promise<{ user: SessionUser; db: Db } | { error: string }> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) return { error: "Please sign in with a staff account." };
  if (!UUID.test(courseId)) return { error: "Missing course." };
  const db = await createClient();
  if (user.role === "admin") return { user, db };
  const { data } = await db
    .from("course_members")
    .select("id")
    .eq("course_id", courseId)
    .eq("role", "owner")
    .or(`user_id.eq.${user.id},email.eq.${user.email.toLowerCase()}`)
    .limit(1);
  if (!data || data.length === 0) return { error: "Only the course owner (or an admin) can change these settings." };
  return { user, db };
}

const refresh = () => {
  revalidatePath("/c/[course]/settings", "page");
  revalidatePath("/admin/people");
};

// ── team ──────────────────────────────────────────────────────────────────────
export async function addTeamMember(input: { courseId: string; email: string; role: MemberRole; cohortId?: string | null }): Promise<SettingsResult<{ id: string }>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  if (!ROLES.includes(input.role)) return fail("Pick a role.");
  const res = await insertMember(ctx.db, { courseId: input.courseId, email: input.email, role: input.role, cohortId: input.cohortId, addedBy: ctx.user.id });
  if (res.id === null) return fail(res.error);
  await auditLog(ctx.db, ctx.user, "course_member_added", { member_id: res.id, course_id: input.courseId, email: input.email.trim().toLowerCase(), role: input.role });
  refresh();
  return done({ id: res.id });
}

export async function updateTeamMember(input: { courseId: string; id: string; role?: MemberRole; cohortId?: string | null }): Promise<SettingsResult<null>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  if (!UUID.test(input.id)) return fail("Missing member.");
  const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (input.role !== undefined) {
    if (!ROLES.includes(input.role)) return fail("Pick a role.");
    patch.role = input.role;
  }
  if (input.cohortId !== undefined) patch.cohort_id = input.cohortId || null;
  const { error } = await ctx.db.from("course_members").update(patch).eq("id", input.id).eq("course_id", input.courseId);
  if (error) return fail(error.message);
  await auditLog(ctx.db, ctx.user, "course_member_updated", { member_id: input.id, course_id: input.courseId, ...patch });
  refresh();
  return done(null);
}

export async function removeTeamMember(input: { courseId: string; id: string }): Promise<SettingsResult<null>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  if (!UUID.test(input.id)) return fail("Missing member.");
  const { data: row } = await ctx.db.from("course_members").select("email, is_handler").eq("id", input.id).maybeSingle();
  const { error } = await ctx.db.from("course_members").delete().eq("id", input.id).eq("course_id", input.courseId);
  if (error) return fail(error.message);
  await auditLog(ctx.db, ctx.user, "course_member_removed", { member_id: input.id, course_id: input.courseId, ...(row as object | null) });
  refresh();
  return done(null);
}

/** Hand the course over: the new handler's row records who it came from and when; the audit row
 *  carries the note. (No Slack DM from here — the worker reads handlers on its next sync.) */
export async function handOverCourse(input: { courseId: string; toMemberId: string; note: string }): Promise<SettingsResult<null>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  if (!UUID.test(input.toMemberId)) return fail("Pick who takes over.");
  const note = input.note.trim().slice(0, 1000);
  if (note.length < 3) return fail("Add a short hand-over note — it goes into the audit trail.");
  const { data: current } = await ctx.db
    .from("course_members")
    .select("id, email, user_id")
    .eq("course_id", input.courseId)
    .eq("is_handler", true)
    .maybeSingle();
  const from = current as { id: string; email: string; user_id: string | null } | null;
  if (from?.id === input.toMemberId) return fail("They already handle this course.");
  const err = await makeHandler(ctx.db, input.courseId, input.toMemberId);
  if (err) return fail(err);
  const stamp = await ctx.db
    .from("course_members")
    .update({ handed_over_from: from?.id ?? null, handed_over_at: new Date().toISOString(), updated_at: new Date().toISOString() })
    .eq("id", input.toMemberId);
  if (stamp.error) return fail(`Handler changed, but the hand-over could not be recorded: ${stamp.error.message}`);
  await auditLog(ctx.db, ctx.user, "course_handed_over", {
    course_id: input.courseId,
    from_member_id: from?.id ?? null,
    from_email: from?.email ?? null,
    to_member_id: input.toMemberId,
    note,
  });
  refresh();
  return done(null);
}

/** Per-member Slack toggle. Editors can flip anyone; a member can always flip their own row. */
export async function setMemberSlack(input: { courseId: string; id: string; notifySlack: boolean }): Promise<SettingsResult<null>> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) return fail("Please sign in with a staff account.");
  if (!UUID.test(input.id) || !UUID.test(input.courseId)) return fail("Missing member.");
  const db = await createClient();
  const ctx = await editor(input.courseId);
  if ("error" in ctx) {
    const { data } = await db.from("course_members").select("id").eq("id", input.id).or(`user_id.eq.${user.id},email.eq.${user.email.toLowerCase()}`).maybeSingle();
    if (!data) return fail(ctx.error);
  }
  const { error } = await db
    .from("course_members")
    .update({ notify_slack: !!input.notifySlack, updated_at: new Date().toISOString() })
    .eq("id", input.id)
    .eq("course_id", input.courseId);
  if (error) return fail(error.message);
  await auditLog(db, user, "course_member_notify_changed", { member_id: input.id, course_id: input.courseId, notify_slack: !!input.notifySlack });
  refresh();
  return done(null);
}

// ── cohorts ───────────────────────────────────────────────────────────────────
export async function renameCohort(input: { courseId: string; id: string; name: string }): Promise<SettingsResult<null>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  if (!UUID.test(input.id)) return fail("Missing cohort.");
  const name = input.name.trim().slice(0, 120);
  if (!name) return fail("Give the cohort a name.");
  const { error } = await ctx.db.from("cohorts").update({ name }).eq("id", input.id).eq("course_id", input.courseId);
  if (error) return fail(error.code === "23505" ? "Another cohort on this course already has that name." : error.message);
  await auditLog(ctx.db, ctx.user, "cohort_renamed", { cohort_id: input.id, course_id: input.courseId, name });
  refresh();
  return done(null);
}

// ── modules (topic aliases) ───────────────────────────────────────────────────
/** Map a raw class name to a module: an existing topic, or a new one created on the spot. */
export async function mapTopicAlias(input: {
  courseId: string;
  alias: string;
  topicId?: string | null;
  newTopicName?: string | null;
}): Promise<SettingsResult<{ topicId: string }>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  const alias = input.alias.trim();
  if (!alias) return fail("Missing class name.");
  let topicId = input.topicId && UUID.test(input.topicId) ? input.topicId : null;
  if (!topicId) {
    const name = (input.newTopicName ?? "").trim().slice(0, 160);
    if (!name) return fail("Pick a module, or type a name to create one.");
    const { data, error } = await ctx.db.from("topics").insert({ name, course_id: input.courseId }).select("id").single();
    if (error) return fail(error.message);
    topicId = (data as { id: string }).id;
  }
  const ins = await ctx.db.from("topic_aliases").insert({ alias, topic_id: topicId });
  if (ins.error && ins.error.code !== "23505" && !ins.error.message.includes("duplicate")) return fail(ins.error.message);
  // Best effort: point existing rated classes at the module (no-op if the column is not there yet).
  await ctx.db.from("class_ratings").update({ topic_id: topicId, updated_at: new Date().toISOString() }).eq("course_id", input.courseId).eq("topic", alias);
  await auditLog(ctx.db, ctx.user, "topic_alias_added", { course_id: input.courseId, alias, topic_id: topicId, created: !input.topicId });
  refresh();
  return done({ topicId });
}

export async function removeTopicAlias(input: { courseId: string; id: string }): Promise<SettingsResult<null>> {
  const ctx = await editor(input.courseId);
  if ("error" in ctx) return fail(ctx.error);
  if (!UUID.test(input.id)) return fail("Missing alias.");
  const { error } = await ctx.db.from("topic_aliases").delete().eq("id", input.id);
  if (error) return fail(error.message);
  await auditLog(ctx.db, ctx.user, "topic_alias_removed", { course_id: input.courseId, alias_id: input.id });
  refresh();
  return done(null);
}
