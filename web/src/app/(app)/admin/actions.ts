"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getCurrentUser, type SessionUser } from "@/lib/session";
import {
  askWorkerToSync,
  auditLog,
  fetchPreviewRows,
  insertMember,
  makeHandler,
  mergePreview,
  type MemberRole,
  type PreviewPayload,
  type SharePeriod,
} from "@/lib/admin";
import {
  MANAGER_ORIGINAL,
  TWO_LINES_GRADED,
  normalizeConfig,
  validateConfig,
  type ScoringConfig,
} from "@/components/admin/scoring-config";

/** Every action returns a VALUE, never throws: production strips the message off an error thrown
 *  from a Server Action, and a PM needs to read the real reason in the toast. */
export type ActionResult<T = null> = { ok: true; data: T } | { ok: false; error: string };

const fail = (error: string): { ok: false; error: string } => ({ ok: false, error });
const done = <T,>(data: T): { ok: true; data: T } => ({ ok: true, data });
const NOT_ADMIN = "Only admins can do that.";
const NOT_STAFF = "Please sign in with a staff account.";

async function requireAdmin(): Promise<SessionUser | null> {
  const user = await getCurrentUser();
  return user && user.role === "admin" ? user : null;
}
async function requireStaff(): Promise<SessionUser | null> {
  const user = await getCurrentUser();
  return user && (user.role === "admin" || user.role === "pm") ? user : null;
}
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// ═══════════════════════════════════════════════════════════════════ scoring
/** The rows the client-side preview scores. Staff only; at most ~15 months. */
export async function getPreviewRows(from: string, to: string): Promise<PreviewPayload> {
  const user = await requireStaff();
  if (!user) return { rows: [], from, to, scored_columns: false, global_prior: { rating: null, approval: null }, error: NOT_STAFF };
  if (!ISO_DATE.test(from) || !ISO_DATE.test(to) || from > to) {
    return { rows: [], from, to, scored_columns: false, global_prior: { rating: null, approval: null }, error: "Pick a valid date range." };
  }
  const span = (+new Date(to) - +new Date(from)) / 86400000;
  if (span > 460) return { rows: [], from, to, scored_columns: false, global_prior: { rating: null, approval: null }, error: "Keep the range under 15 months." };
  return fetchPreviewRows(from, to);
}

export type WhatIfSummary = {
  band_counts: Record<string, number>;
  action_counts: Record<string, number>;
  analyses_per_week: number;
  videos_per_week: number;
  transcripts_per_week: number;
  changed: { id: string; from_band: string | null; to_band: string | null; from_action: string | null; to_action: string | null }[];
  changed_count: number;
  dropped_count: number;
  flip_share: number;
};

/** The database's own answer for a draft over a range (scoring_whatif_summary). */
export async function whatIfSummary(config: ScoringConfig, from: string, to: string): Promise<ActionResult<WhatIfSummary>> {
  const user = await requireStaff();
  if (!user) return fail(NOT_STAFF);
  if (!ISO_DATE.test(from) || !ISO_DATE.test(to)) return fail("Pick a valid date range.");
  const cfg = normalizeConfig(config);
  const errs = validateConfig(cfg);
  if (errs.length) return fail(errs[0]);
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("scoring_whatif_summary", { p_config: cfg, p_from: from, p_to: to });
  if (error) return fail(error.message);
  return done(data as WhatIfSummary);
}

async function nextVersion(supabase: Awaited<ReturnType<typeof createClient>>): Promise<number> {
  const { data } = await supabase.from("scoring_configs").select("version").order("version", { ascending: false }).limit(1).maybeSingle();
  return ((data as { version: number } | null)?.version ?? 0) + 1;
}

/** Insert a scoring row with the next free version. Two admins creating a draft in the same
 *  minute used to collide on the unique version and see a raw "23505"; now the loser simply
 *  takes the next number. */
async function insertWithFreshVersion(
  supabase: Awaited<ReturnType<typeof createClient>>,
  insert: (version: number) => PromiseLike<{ data: unknown; error: { code?: string; message: string } | null }>,
): Promise<{ data: { id: string; version: number } | null; error: string | null }> {
  for (let attempt = 0; attempt < 3; attempt++) {
    const version = await nextVersion(supabase);
    const { data, error } = await insert(version);
    if (!error) return { data: data as { id: string; version: number }, error: null };
    if (error.code !== "23505") return { data: null, error: error.message };
  }
  return { data: null, error: "Someone else created a version at the same moment — try again." };
}

const slug = (s: string) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "").slice(0, 40);

/** New draft from the active version, any stored version, or one of the two presets. */
export async function createScoringDraft(input: {
  fromConfigId?: string | null;
  preset?: "C0" | "C5" | null;
  name?: string;
}): Promise<ActionResult<{ id: string; version: number }>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  const supabase = await createClient();
  let config: ScoringConfig;
  let baseName: string;
  let baseKey: string | null = null;
  if (input.preset === "C0") {
    config = MANAGER_ORIGINAL;
    baseName = MANAGER_ORIGINAL.name!;
  } else if (input.preset === "C5") {
    config = TWO_LINES_GRADED;
    baseName = TWO_LINES_GRADED.name!;
  } else {
    let q = supabase.from("scoring_configs").select("id, key, name, config").limit(1);
    q = input.fromConfigId && UUID.test(input.fromConfigId) ? q.eq("id", input.fromConfigId) : q.eq("status", "active");
    const { data, error } = await q.maybeSingle();
    if (error) return fail(error.message);
    if (!data) return fail("No version to start from — pick a preset.");
    const row = data as { id: string; key: string | null; name: string; config: unknown };
    config = normalizeConfig(row.config);
    baseName = row.name;
    baseKey = row.key;
  }
  const name = (input.name?.trim() || `${baseName} (draft)`).slice(0, 120);
  const { data: row, error } = await insertWithFreshVersion(supabase, (version) =>
    supabase
      .from("scoring_configs")
      .insert({
        version,
        key: baseKey ? `${baseKey}-v${version}` : slug(name) || `v${version}`,
        name,
        status: "draft",
        config: { ...config, name },
        note: null,
        created_by: user.id,
      })
      .select("id, version")
      .single(),
  );
  if (error || !row) return fail(error ?? "Could not create the draft.");
  await auditLog(supabase, user, "scoring_draft_created", { config_id: row.id, version: row.version, from: input.fromConfigId ?? input.preset ?? "active" });
  revalidatePath("/admin/scoring");
  return done(row);
}

export async function saveScoringDraft(input: {
  id: string;
  name: string;
  key: string;
  note: string;
  config: ScoringConfig;
}): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.id)) return fail("Missing draft.");
  const name = input.name.trim().slice(0, 120);
  if (!name) return fail("Give the draft a name.");
  const cfg = normalizeConfig(input.config);
  const errs = validateConfig(cfg);
  if (errs.length) return fail(errs[0]);
  const supabase = await createClient();
  const { error, count } = await supabase
    .from("scoring_configs")
    .update({ name, key: slug(input.key) || null, note: input.note.trim().slice(0, 2000) || null, config: { ...cfg, name } }, { count: "exact" })
    .eq("id", input.id)
    .eq("status", "draft");
  if (error) return fail(error.message);
  if (!count) return fail("Only drafts can be edited — start a new draft from this version instead.");
  await auditLog(supabase, user, "scoring_draft_saved", { config_id: input.id, name });
  revalidatePath("/admin/scoring");
  return done(null);
}

export type ApplySummary = { version: number; scored: number; band_counts: Record<string, number>; action_counts: Record<string, number> };

/** Publish a draft (or re-activate a retired version = rollback). The RPC re-scores every class,
 *  writes the history rows and its own audit row; we add the note the admin typed. */
export async function publishScoringConfig(input: { id: string; name?: string; note: string }): Promise<ActionResult<ApplySummary>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.id)) return fail("Missing version.");
  const note = input.note.trim();
  if (note.length < 3) return fail("Write a short note saying why — it goes into the audit trail.");
  const supabase = await createClient();
  const { data: row, error: readErr } = await supabase.from("scoring_configs").select("id, name, status, config").eq("id", input.id).maybeSingle();
  if (readErr) return fail(readErr.message);
  if (!row) return fail("That version no longer exists.");
  const r = row as { id: string; name: string; status: string; config: unknown };
  if (r.status === "active") return fail("That version is already active.");
  const cfg = normalizeConfig(r.config);
  const errs = validateConfig(cfg);
  if (errs.length) return fail(`This version cannot be applied: ${errs[0]}`);
  if (r.status === "draft") {
    const name = (input.name ?? r.name).trim().slice(0, 120);
    if (!name) return fail("Give the version a name before publishing.");
    const upd = await supabase.from("scoring_configs").update({ name, note, config: { ...cfg, name } }).eq("id", input.id);
    if (upd.error) return fail(upd.error.message);
  }
  const { data, error } = await supabase.rpc("apply_scoring_config", { p_config_id: input.id });
  if (error) return fail(error.message);
  const summary = data as ApplySummary;
  await auditLog(supabase, user, r.status === "draft" ? "scoring_published" : "scoring_rolled_back", {
    config_id: input.id,
    version: summary?.version ?? null,
    scored: summary?.scored ?? null,
    band_counts: summary?.band_counts ?? null,
    note,
  });
  revalidatePath("/", "layout");
  return done(summary);
}

export async function deleteScoringDraft(input: { id: string }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.id)) return fail("Missing draft.");
  const supabase = await createClient();
  const { error, count } = await supabase.from("scoring_configs").delete({ count: "exact" }).eq("id", input.id).eq("status", "draft");
  if (error) return fail(error.message);
  if (!count) return fail("Only drafts can be deleted.");
  await auditLog(supabase, user, "scoring_draft_deleted", { config_id: input.id });
  revalidatePath("/admin/scoring");
  return done(null);
}

/** A PM's what-if, saved as a draft for an admin to review. Written with the service role AFTER
 *  the staff check, because scoring_configs is admin-writable under RLS. */
export async function proposeScoringDraft(input: { name: string; note: string; config: ScoringConfig }): Promise<ActionResult<{ id: string; version: number }>> {
  // Drafts are admin-only in the database; this used to write with the service role for any
  // staff member, letting a PM insert unlimited config rows.
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  const name = input.name.trim().slice(0, 120);
  if (!name) return fail("Give your proposal a name.");
  const note = input.note.trim().slice(0, 2000);
  if (note.length < 3) return fail("Add a note for the admin — what you changed and why.");
  const cfg = normalizeConfig(input.config);
  const errs = validateConfig(cfg);
  if (errs.length) return fail(errs[0]);
  const supabase = await createClient();
  const { data: row, error } = await insertWithFreshVersion(supabase, (version) =>
    supabase
      .from("scoring_configs")
      .insert({
        version,
        key: `proposal-${slug(name) || version}`,
        name,
        status: "draft",
        config: { ...cfg, name },
        note: `Proposed by ${user.name} (${user.email}): ${note}`,
        created_by: user.id,
      })
      .select("id, version")
      .single(),
  );
  if (error || !row) return fail(error ?? "Could not save the proposal.");
  await auditLog(supabase, user, "scoring_proposed", { config_id: row.id, version: row.version, name, note });
  revalidatePath("/admin/scoring");
  return done(row);
}

// ══════════════════════════════════════════════════════════════════ identity
export async function decideSuggestion(input: { id: string; accept: boolean }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.id)) return fail("Missing suggestion.");
  const supabase = await createClient();
  const { error } = await supabase.rpc(input.accept ? "accept_instructor_suggestion" : "reject_instructor_suggestion", { p_id: input.id });
  if (error) return fail(error.message);
  await auditLog(supabase, user, input.accept ? "instructor_suggestion_accepted" : "instructor_suggestion_rejected", { suggestion_id: input.id });
  revalidatePath("/", "layout");
  return done(null);
}

/** Bulk accept: every pending suggestion at or above the threshold, one RPC each (the RPC is the
 *  only thing that knows how to move the rows). Reports how many went through. */
export async function acceptSuggestionsAbove(threshold: number): Promise<ActionResult<{ accepted: number; failed: number }>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  const t = Number(threshold);
  if (!(t >= 0.5 && t <= 1)) return fail("Threshold must be between 0.5 and 1.");
  const supabase = await createClient();
  const { data, error } = await supabase.from("instructor_match_suggestions").select("id").eq("status", "pending").gte("score", t).limit(500);
  if (error) return fail(error.message);
  let accepted = 0, failed = 0;
  for (const row of (data ?? []) as { id: string }[]) {
    const { error: e } = await supabase.rpc("accept_instructor_suggestion", { p_id: row.id });
    if (e) failed += 1;
    else accepted += 1;
  }
  await auditLog(supabase, user, "instructor_suggestions_bulk_accepted", { threshold: t, accepted, failed });
  revalidatePath("/", "layout");
  return done({ accepted, failed });
}

async function backfillAlias(supabase: Awaited<ReturnType<typeof createClient>>, alias: string, instructorId: string) {
  // Harmless if the RPC already moved the rows; catches the case where it only wrote the alias.
  await supabase.from("class_ratings").update({ instructor_id: instructorId, updated_at: new Date().toISOString() }).eq("instructor", alias).is("instructor_id", null);
}

export async function addAliasToInstructor(input: { alias: string; instructorId: string }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  const alias = input.alias.trim();
  if (!alias) return fail("Missing name.");
  if (!UUID.test(input.instructorId)) return fail("Pick an instructor.");
  const supabase = await createClient();
  const { error } = await supabase.rpc("add_instructor_alias", { p_alias: alias, p_instructor_id: input.instructorId });
  if (error) return fail(error.message);
  await backfillAlias(supabase, alias, input.instructorId);
  await auditLog(supabase, user, "instructor_alias_added", { alias, instructor_id: input.instructorId });
  revalidatePath("/", "layout");
  return done(null);
}

/** Create the instructor from an unresolved spelling and link that spelling to it. */
export async function createInstructorForName(input: { name: string; displayName?: string }): Promise<ActionResult<{ id: string }>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  const raw = input.name.trim();
  const display = (input.displayName ?? raw).trim();
  if (!raw || !display) return fail("Missing name.");
  const supabase = await createClient();
  const { data, error } = await supabase.from("instructors").insert({ name: display }).select("id").single();
  if (error) return fail(error.message);
  const id = (data as { id: string }).id;
  const rpc = await supabase.rpc("add_instructor_alias", { p_alias: raw, p_instructor_id: id });
  if (rpc.error) return fail(`Instructor created, but the alias failed: ${rpc.error.message}`);
  await backfillAlias(supabase, raw, id);
  await auditLog(supabase, user, "instructor_created_from_name", { instructor_id: id, alias: raw, name: display });
  revalidatePath("/", "layout");
  return done({ id });
}

export async function getMergePreview(fromId: string): Promise<ActionResult<{ ratings: number; classes: number; aliases: number | null }>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(fromId)) return fail("Pick an instructor.");
  return done(await mergePreview(fromId));
}

export async function mergeInstructorIdentities(input: { fromId: string; intoId: string }): Promise<ActionResult<{ mergeId: string | null }>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.fromId) || !UUID.test(input.intoId)) return fail("Pick both instructors.");
  if (input.fromId === input.intoId) return fail("Pick two different instructors.");
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("merge_instructors", { p_from: input.fromId, p_into: input.intoId });
  if (error) return fail(error.message);
  const mergeId = typeof data === "string" ? data : null;
  await auditLog(supabase, user, "instructor_merged", { from: input.fromId, into: input.intoId, merge_id: mergeId });
  revalidatePath("/", "layout");
  return done({ mergeId });
}

export async function undoInstructorMerge(input: { mergeId: string }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.mergeId)) return fail("Missing merge.");
  const supabase = await createClient();
  const { error } = await supabase.rpc("undo_instructor_merge", { p_merge_id: input.mergeId });
  if (error) return fail(error.message);
  await auditLog(supabase, user, "instructor_merge_undone", { merge_id: input.mergeId });
  revalidatePath("/", "layout");
  return done(null);
}

// ════════════════════════════════════════════════════════════════════ people
const ROLES: MemberRole[] = ["owner", "pm", "viewer"];

export async function addCourseMember(input: {
  courseId: string;
  email: string;
  role: MemberRole;
  cohortId?: string | null;
  isHandler?: boolean;
}): Promise<ActionResult<{ id: string }>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.courseId)) return fail("Pick a course.");
  if (!ROLES.includes(input.role)) return fail("Pick a role.");
  const supabase = await createClient();
  const res = await insertMember(supabase, { courseId: input.courseId, email: input.email, role: input.role, cohortId: input.cohortId, addedBy: user.id });
  if (res.id === null) return fail(res.error);
  if (input.isHandler) {
    const err = await makeHandler(supabase, input.courseId, res.id);
    if (err) return fail(`Added, but could not make them the handler: ${err}`);
  }
  await auditLog(supabase, user, "course_member_added", { member_id: res.id, course_id: input.courseId, email: input.email.trim().toLowerCase(), role: input.role, handler: !!input.isHandler });
  revalidatePath("/", "layout");
  return done({ id: res.id });
}

export async function updateCourseMember(input: {
  id: string;
  role?: MemberRole;
  notifySlack?: boolean;
  cohortId?: string | null;
}): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.id)) return fail("Missing member.");
  const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (input.role !== undefined) {
    if (!ROLES.includes(input.role)) return fail("Pick a role.");
    patch.role = input.role;
  }
  if (input.notifySlack !== undefined) patch.notify_slack = !!input.notifySlack;
  if (input.cohortId !== undefined) patch.cohort_id = input.cohortId || null;
  const supabase = await createClient();
  const { error } = await supabase.from("course_members").update(patch).eq("id", input.id);
  if (error) return fail(error.message);
  await auditLog(supabase, user, "course_member_updated", { member_id: input.id, ...patch });
  revalidatePath("/", "layout");
  return done(null);
}

export async function setCourseHandler(input: { courseId: string; memberId: string }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.courseId) || !UUID.test(input.memberId)) return fail("Missing member.");
  const supabase = await createClient();
  const err = await makeHandler(supabase, input.courseId, input.memberId);
  if (err) return fail(err);
  await auditLog(supabase, user, "course_handler_set", { course_id: input.courseId, member_id: input.memberId });
  revalidatePath("/", "layout");
  return done(null);
}

export async function removeCourseMember(input: { id: string }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.id)) return fail("Missing member.");
  const supabase = await createClient();
  const { data: row } = await supabase.from("course_members").select("course_id, email, is_handler").eq("id", input.id).maybeSingle();
  const { error } = await supabase.from("course_members").delete().eq("id", input.id);
  if (error) return fail(error.message);
  await auditLog(supabase, user, "course_member_removed", { member_id: input.id, ...(row as object | null) });
  revalidatePath("/", "layout");
  return done(null);
}

/** The eight course colours, stored as the 1–8 index the shell's `--course-N` tokens use. */
export async function updateCourseIdentity(input: { courseId: string; color: string; initials: string }): Promise<ActionResult<null>> {
  const user = await requireAdmin();
  if (!user) return fail(NOT_ADMIN);
  if (!UUID.test(input.courseId)) return fail("Pick a course.");
  const color = input.color.trim();
  if (!/^[1-8]$/.test(color)) return fail("Pick one of the eight colours.");
  const initials = input.initials.trim().toUpperCase().slice(0, 3);
  if (!/^[A-Z0-9]{1,3}$/.test(initials)) return fail("Initials: one to three letters or digits.");
  const supabase = await createClient();
  const { error } = await supabase.from("courses").update({ color, initials }).eq("id", input.courseId);
  if (error) return fail(error.message);
  await auditLog(supabase, user, "course_identity_updated", { course_id: input.courseId, color, initials });
  revalidatePath("/", "layout");
  return done(null);
}

// ══════════════════════════════════════════════════════════════════════ sync
export async function requestSyncNow(): Promise<ActionResult<null>> {
  const user = await requireStaff();
  if (!user) return fail(NOT_STAFF);
  const err = await askWorkerToSync();
  if (err) return fail(err);
  const supabase = await createClient();
  await auditLog(supabase, user, "sync_requested", { trigger: "manual" });
  revalidatePath("/admin/sync");
  return done(null);
}

/** Map an unmapped sheet label to a course: alias row + backfill of existing rows. */
export async function mapLabelToCourse(input: { alias: string; courseId: string }): Promise<ActionResult<{ updated: number }>> {
  const user = await requireStaff();
  if (!user) return fail(NOT_STAFF);
  const alias = input.alias.trim();
  if (!alias || !UUID.test(input.courseId)) return fail("Pick a course for the label.");
  const supabase = await createClient();
  const ins = await supabase.from("course_aliases").insert({ alias, course_id: input.courseId });
  if (ins.error && ins.error.code !== "23505" && !ins.error.message.includes("duplicate")) return fail(ins.error.message);
  const upd = await supabase
    .from("class_ratings")
    .update({ course_id: input.courseId, updated_at: new Date().toISOString() }, { count: "exact" })
    .eq("course_label", alias)
    .is("course_id", null);
  if (upd.error) return fail(upd.error.message);
  await auditLog(supabase, user, "course_alias_added", { alias, course_id: input.courseId, rows: upd.count ?? 0 });
  revalidatePath("/", "layout");
  return done({ updated: upd.count ?? 0 });
}

// ═════════════════════════════════════════════════════════════════════ shares
/** A read-only report link: an unguessable token, an expiry, revocable. Any staff member can
 *  share; the page behind it still needs an IK sign-in. */
export async function createShareLink(input: {
  courseId: string | null;
  period: SharePeriod;
  expiresInDays?: number;
}): Promise<ActionResult<{ id: string; token: string; path: string; expires_at: string }>> {
  const user = await requireStaff();
  if (!user) return fail(NOT_STAFF);
  if (input.courseId && !UUID.test(input.courseId)) return fail("Pick a course.");
  if (!input.courseId && user.role !== "admin") return fail("Only an admin can share a report across all courses.");
  const p = input.period;
  if (!p || !ISO_DATE.test(p.from) || !ISO_DATE.test(p.to) || p.from > p.to) return fail("Pick a valid period.");
  const days = Math.min(365, Math.max(1, Math.round(Number(input.expiresInDays ?? 30)) || 30));
  const token = randomBytes(24).toString("base64url");
  const expires_at = new Date(Date.now() + days * 86400000).toISOString();
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("report_shares")
    .insert({
      token,
      course_id: input.courseId,
      period: { kind: p.kind, from: p.from, to: p.to, label: p.label ?? null, require_login: p.require_login ?? true },
      created_by: user.id,
      expires_at,
    })
    .select("id")
    .single();
  if (error) return fail(error.message);
  const id = (data as { id: string }).id;
  await auditLog(supabase, user, "share_link_created", { share_id: id, course_id: input.courseId, period: p, expires_at });
  revalidatePath("/admin/people");
  revalidatePath("/c/[course]/settings", "page");
  return done({ id, token, path: `/share/${token}`, expires_at });
}

export async function revokeShareLink(input: { id: string }): Promise<ActionResult<null>> {
  const user = await requireStaff();
  if (!user) return fail(NOT_STAFF);
  if (!UUID.test(input.id)) return fail("Missing link.");
  const supabase = await createClient();
  const { data: row } = await supabase.from("report_shares").select("created_by, revoked_at").eq("id", input.id).maybeSingle();
  const r = row as { created_by: string | null; revoked_at: string | null } | null;
  if (!r) return fail("That link no longer exists.");
  if (r.revoked_at) return done(null);
  if (user.role !== "admin" && r.created_by !== user.id) return fail("Only the person who created the link (or an admin) can revoke it.");
  const { error } = await supabase.from("report_shares").update({ revoked_at: new Date().toISOString() }).eq("id", input.id);
  if (error) return fail(error.message);
  await auditLog(supabase, user, "share_link_revoked", { share_id: input.id });
  revalidatePath("/admin/people");
  revalidatePath("/c/[course]/settings", "page");
  return done(null);
}
