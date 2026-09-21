"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/session";

/** The queue lives at /c/<slug>/queue and /team/queue; the classes table shows the same rows. */
function revalidateQueue() {
  revalidatePath("/c/[course]/queue", "page");
  revalidatePath("/c/[course]/classes", "page");
  revalidatePath("/team/queue");
}

async function requirePm() {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) throw new Error("Not authorized.");
  return user;
}

async function audit(supabase: Awaited<ReturnType<typeof createClient>>, actorId: string, action: string, detail: object) {
  await supabase.from("audit_log").insert({ actor_id: actorId, action, detail });
}

/** Confirm the flag: yes, this class should be analysed (handler's ack from the Slack ping). */
export async function confirmRating(formData: FormData) {
  const user = await requirePm();
  const id = String(formData.get("id") ?? "");
  if (!id) throw new Error("Missing row.");
  const supabase = await createClient();
  const { error } = await supabase
    .from("class_ratings")
    .update({ review_status: "confirmed", updated_at: new Date().toISOString() })
    .eq("id", id)
    .in("review_status", ["new", "notified"]);
  if (error) throw new Error(error.message);
  await audit(supabase, user.id, "rating_confirmed", { class_rating_id: id });
  revalidateQueue();
}

/** Dismiss the flag: no analysis needed. The sync never re-opens a dismissed row. */
export async function dismissRating(formData: FormData) {
  const user = await requirePm();
  const id = String(formData.get("id") ?? "");
  if (!id) throw new Error("Missing row.");
  const supabase = await createClient();
  const { error } = await supabase
    .from("class_ratings")
    .update({ review_status: "dismissed", updated_at: new Date().toISOString() })
    .eq("id", id)
    .in("review_status", ["new", "notified", "confirmed"]);   // not one already being analysed
  if (error) throw new Error(error.message);
  await audit(supabase, user.id, "rating_dismissed", { class_rating_id: id });
  revalidateQueue();
}

/** Escalate: force the video verdict, whatever the numbers say. */
export async function escalateRating(formData: FormData) {
  const user = await requirePm();
  const id = String(formData.get("id") ?? "");
  if (!id) throw new Error("Missing row.");
  const supabase = await createClient();
  const { error } = await supabase
    .from("class_ratings")
    .update({
      escalated: true,
      decision: "video",
      updated_at: new Date().toISOString(),
    })
    .eq("id", id)
    .in("review_status", ["new", "notified", "confirmed"]);   // a dismissed or analysed row is left alone
  if (error) throw new Error(error.message);
  await audit(supabase, user.id, "rating_escalated", { class_rating_id: id });
  revalidateQueue();
}

/** Map an unmapped course label to a course (inserts the alias + backfills existing rows). */
export async function mapCourseLabel(formData: FormData) {
  const user = await requirePm();
  const alias = String(formData.get("alias") ?? "").trim();
  const courseId = String(formData.get("course_id") ?? "");
  if (!alias || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(courseId)) throw new Error("Pick a course for the label.");
  const supabase = await createClient();
  const ins = await supabase.from("course_aliases").insert({ alias, course_id: courseId });
  if (ins.error && ins.error.code !== "23505") throw new Error(ins.error.message);   // 23505 = already mapped, fine
  const upd = await supabase
    .from("class_ratings")
    .update({ course_id: courseId, updated_at: new Date().toISOString() })
    .eq("course_label", alias)
    .is("course_id", null);
  if (upd.error) throw new Error(upd.error.message);
  await audit(supabase, user.id, "course_alias_added", { alias, course_id: courseId });
  revalidateQueue();
}

const SYNC_ASLEEP = "Could not reach the sync service — it may be waking up; try again in a minute.";

/** POST /sync-ratings on the worker. Resolves to null on success, or the friendly reason. */
async function askWorkerToSync(): Promise<string | null> {
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

/** Ask the worker to pull the sheet right now. Throws the friendly reason on failure — the
 *  command palette relies on this shape. */
export async function syncNow() {
  await requirePm();
  const err = await askWorkerToSync();
  if (err) throw new Error(err);
  revalidateQueue();
}

export type SyncResult = { ok: true } | { ok: false; error: string };

/** Same request as syncNow, but the outcome comes back as a VALUE. Production strips the
 *  message off errors thrown from a Server Action, so a client button that wants to show
 *  "it may be waking up" has to receive it as data, not as an exception. */
export async function requestSync(): Promise<SyncResult> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) return { ok: false, error: "Not authorized." };
  const err = await askWorkerToSync();
  if (err) return { ok: false, error: err };
  revalidateQueue();
  return { ok: true };
}
