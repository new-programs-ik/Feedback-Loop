"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/session";

export type AnalyzeState = { error?: string };

function safeDetail(s: string): string {
  try {
    const j = JSON.parse(s);
    return typeof j.detail === "string" ? j.detail : s.slice(0, 200);
  } catch {
    return s.slice(0, 200);
  }
}

/** Create a class, run the analysis worker, and store the analysis + draft. */
export async function createAnalysis(_prev: AnalyzeState, formData: FormData): Promise<AnalyzeState> {
  const user = await getCurrentUser();
  if (!user) return { error: "Please sign in again." };
  if (user.role !== "admin" && user.role !== "pm") {
    return { error: "Only PMs and admins can create analyses." };
  }

  const supabase = await createClient();

  let course_id = String(formData.get("course_id") ?? "");
  const newCourse = String(formData.get("new_course") ?? "").trim();
  const cohortIdRaw = String(formData.get("cohort_id") ?? "").trim();
  const cohortName = String(formData.get("cohort") ?? "").trim();
  const instructorName = String(formData.get("instructor") ?? "").trim();
  const topic = String(formData.get("topic") ?? "").trim();
  const class_date = String(formData.get("class_date") ?? "");
  const ratingRaw = String(formData.get("rating") ?? "").trim();
  const numRaw = String(formData.get("num_ratings") ?? "").trim();
  const agenda = String(formData.get("agenda") ?? "").trim();
  const vimeo_url = String(formData.get("vimeo_url") ?? "").trim();
  const file = formData.get("file") as File | null;
  const transcript = file && file.size ? await file.text() : "";
  const materials_text = String(formData.get("materials_text") ?? "").trim();
  const materials_url = String(formData.get("materials_url") ?? "").trim();
  const materials_files: { filename: string; b64: string }[] = [];
  let materialsTotal = 0;
  for (const f of formData.getAll("materials") as File[]) {
    if (!f || !f.size) continue;
    materialsTotal += f.size;
    if (materialsTotal > 4 * 1024 * 1024) {
      return {
        error: "Materials are too large (keep the total under ~4 MB). Compress the deck (or export as PDF), or paste the key content in the text box instead.",
      };
    }
    materials_files.push({ filename: f.name, b64: Buffer.from(await f.arrayBuffer()).toString("base64") });
  }

  // "Other" course → find-or-create it from the typed name.
  if (course_id === "__other__") {
    if (!newCourse) return { error: "Type the new course name." };
    const found = await supabase.from("courses").select("id").eq("name", newCourse).maybeSingle();
    if (found.data) {
      course_id = found.data.id;
    } else {
      const slug = newCourse.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || newCourse.slice(0, 40);
      const ins = await supabase.from("courses").insert({ name: newCourse, slug }).select("id").single();
      if (ins.error || !ins.data) return { error: "Could not create the course: " + (ins.error?.message ?? "") };
      course_id = ins.data.id;
    }
  }

  if (!course_id) return { error: "Pick a course." };
  if (!topic) return { error: "Enter the class topic." };
  if (!class_date) return { error: "Pick the class date." };
  if (!vimeo_url && !transcript) {
    return { error: "Add a Vimeo link or upload a transcript file (.vtt/.srt)." };
  }

  const rating = ratingRaw ? Number(ratingRaw) : null;
  const num_ratings = numRaw ? Number(numRaw) : null;
  const classTypeRaw = String(formData.get("class_type") ?? "live_class");
  const class_type = classTypeRaw === "ars" ? "ars" : "live_class";

  const { data: course } = await supabase.from("courses").select("name").eq("id", course_id).maybeSingle();
  if (!course) return { error: "That course was not found." };

  // Resolve instructor + cohort (create if new).
  let instructor_id: string | null = null;
  if (instructorName) {
    const found = await supabase.from("instructors").select("id").eq("name", instructorName).maybeSingle();
    instructor_id =
      found.data?.id ??
      (await supabase.from("instructors").insert({ name: instructorName }).select("id").single()).data?.id ??
      null;
  }
  let cohort_id: string | null = cohortIdRaw || null;
  if (!cohort_id && cohortName) {
    const found = await supabase
      .from("cohorts").select("id").eq("course_id", course_id).eq("name", cohortName).maybeSingle();
    cohort_id =
      found.data?.id ??
      (await supabase.from("cohorts").insert({ course_id, name: cohortName }).select("id").single()).data?.id ??
      null;
  }

  // Create the class row (status: analyzing).
  const ins = await supabase
    .from("classes")
    .insert({
      course_id, cohort_id, instructor_id, topic, class_date, session_type: class_type,
      rating, num_ratings, vimeo_link: vimeo_url || null, agenda: agenda || null,
      status: "analyzing", created_by: user.id,
    })
    .select("id")
    .single();
  if (ins.error || !ins.data) {
    return { error: "Could not create the class: " + (ins.error?.message ?? "unknown error") };
  }
  const classId = ins.data.id as string;
  await supabase.from("audit_log").insert({
    class_id: classId, actor_id: user.id, action: "created", detail: { source: vimeo_url ? "vimeo" : "upload" },
  });

  // Start the analysis in the BACKGROUND — the worker fetches the transcript, digests the
  // materials, runs the engine, and writes the result to the DB itself when done. We return
  // immediately so the web request never times out (even for a 4-hour class).
  const workerUrl = process.env.ANALYSIS_WORKER_URL || "http://localhost:8000";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.WORKER_API_KEY) headers.Authorization = `Bearer ${process.env.WORKER_API_KEY}`;
  const payload: Record<string, unknown> = {
    class_id: classId,
    course: course.name, topic,
    instructor: instructorName || "(unspecified)",
    rating: rating != null ? String(rating) : "(unspecified)",
    agenda: agenda || "(not provided)",
    class_type,
    ...(materials_files.length || materials_text || materials_url
      ? { materials_files, materials_text, materials_url }
      : {}),
    ...(transcript ? { transcript } : { vimeo_url }),
  };

  async function failStart(where: string, detail: Record<string, unknown>, msg: string): Promise<AnalyzeState> {
    await supabase.from("classes").update({ status: "needs_transcript" }).eq("id", classId);
    await supabase.from("audit_log").insert({ class_id: classId, actor_id: user!.id, action: "error", detail: { where, ...detail } });
    return { error: msg };
  }

  let res: Response;
  try {
    res = await fetch(`${workerUrl}/analyze-async`, { method: "POST", headers, body: JSON.stringify(payload) });
  } catch {
    return failStart("worker-start", { message: "unreachable" },
      "Could not reach the analysis service — try again in a moment (it may be waking up).");
  }
  if (!res.ok) {
    const detail = await res.text();
    return failStart("worker-start", { status: res.status, detail: detail.slice(0, 300) },
      `Could not start the analysis (${res.status}). Please try again.`);
  }

  revalidatePath("/feedback");
  redirect(`/feedback/${classId}`); // review page shows "Analyzing…" and auto-updates when done
}

async function latestFeedbackId(supabase: Awaited<ReturnType<typeof createClient>>, classId: string) {
  const { data } = await supabase
    .from("feedback")
    .select("id, draft_text, edited_text, summary_draft_text, summary_edited_text")
    .eq("class_id", classId)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return data;
}

/** PM edits (optional) + approves. Stores the edit in edited_text; the draft is never overwritten. */
export async function approveFeedback(formData: FormData) {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) throw new Error("Not authorized.");
  const classId = String(formData.get("class_id") ?? "");
  const edited = String(formData.get("edited_text") ?? "").trim();
  const summaryEdited = String(formData.get("summary_edited") ?? "").trim();
  if (!classId) throw new Error("Missing class.");

  const supabase = await createClient();
  const fb = await latestFeedbackId(supabase, classId);
  if (!fb) throw new Error("No feedback to approve.");

  const changed = edited.length > 0 && edited !== fb.draft_text;
  const summaryChanged = summaryEdited.length > 0 && summaryEdited !== fb.summary_draft_text;
  const upd = await supabase
    .from("feedback")
    .update({
      edited_text: changed ? edited : fb.edited_text,
      summary_edited_text: summaryChanged ? summaryEdited : fb.summary_edited_text,
      status: "approved",
      approved_by: user.id,
      approved_at: new Date().toISOString(),
    })
    .eq("id", fb.id);
  if (upd.error) throw new Error("Could not approve: " + upd.error.message);

  await supabase.from("classes").update({ status: "approved" }).eq("id", classId);
  if (changed || summaryChanged) {
    await supabase.from("audit_log").insert({
      class_id: classId, actor_id: user.id, action: "edited",
      detail: { feedback_chars: edited.length, summary_chars: summaryEdited.length },
    });
  }
  await supabase.from("audit_log").insert({
    class_id: classId, actor_id: user.id, action: "approved", detail: { edited: changed },
  });

  revalidatePath("/feedback");
  revalidatePath(`/feedback/${classId}`);
  redirect("/feedback");
}

/** PM discards the draft — the class is marked no-action; nothing is sent. */
export async function discardFeedback(formData: FormData) {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) throw new Error("Not authorized.");
  const classId = String(formData.get("class_id") ?? "");
  if (!classId) throw new Error("Missing class.");

  const supabase = await createClient();
  const fb = await latestFeedbackId(supabase, classId);
  if (fb) await supabase.from("feedback").update({ status: "discarded" }).eq("id", fb.id);
  await supabase.from("classes").update({ status: "discarded" }).eq("id", classId);
  await supabase.from("audit_log").insert({ class_id: classId, actor_id: user.id, action: "discarded" });

  revalidatePath("/feedback");
  redirect("/feedback");
}

export type ReviseResult = { text?: string; error?: string };

/** Review-page agent: rewrite the current draft per the PM's plain-English instruction. */
export async function reviseDraft(
  classId: string,
  instruction: string,
  currentText: string,
  kind: "feedback" | "summary" = "feedback",
): Promise<ReviseResult> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) return { error: "Not authorized." };
  if (!instruction.trim()) return { error: "Tell the AI what you'd like changed." };
  if (!currentText.trim()) return { error: "There's no feedback text to revise." };

  const supabase = await createClient();
  const { data: klass } = await supabase
    .from("classes")
    .select("topic, class_date, session_type, courses(name), instructors(name), analyses(result)")
    .eq("id", classId)
    .single();

  let contextStr = "";
  let flagsJson = "";
  if (klass) {
    const course = (klass.courses as { name?: string } | null)?.name ?? "";
    const instructor = (klass.instructors as { name?: string } | null)?.name ?? "";
    contextStr = `Course: ${course}\nTopic: ${klass.topic}\nInstructor: ${instructor}\n` +
      `Session type: ${klass.session_type === "ars" ? "Assignment Review Session" : "Live class"}`;
    const analyses = (klass.analyses ?? []) as Array<{ result?: { flags?: unknown[] } }>;
    const flags = analyses[analyses.length - 1]?.result?.flags;
    if (flags) flagsJson = JSON.stringify(flags);
  }

  const workerUrl = process.env.ANALYSIS_WORKER_URL || "http://localhost:8000";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.WORKER_API_KEY) headers.Authorization = `Bearer ${process.env.WORKER_API_KEY}`;

  let res: Response;
  try {
    res = await fetch(`${workerUrl}/revise`, {
      method: "POST",
      headers,
      body: JSON.stringify({ feedback: currentText, instruction, context: contextStr, flags_json: flagsJson, kind }),
    });
  } catch {
    return { error: "Could not reach the AI service — try again in a moment (it may be waking up)." };
  }
  if (!res.ok) {
    const detail = await res.text();
    return { error: res.status === 422 ? safeDetail(detail) : `Revision failed (${res.status}) — try again.` };
  }
  const body = await res.json();
  await supabase.from("audit_log").insert({
    class_id: classId, actor_id: user.id, action: "ai_revised",
    detail: { instruction: instruction.slice(0, 300), cost_usd: body.meta?.cost_usd },
  });
  return { text: String(body.feedback ?? "") };
}

/** Delete an analysis + its class entirely (cascades analyses/feedback/transcripts). */
export async function deleteClass(formData: FormData) {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) throw new Error("Not authorized.");
  const classId = String(formData.get("class_id") ?? "");
  if (!classId) throw new Error("Missing class.");
  const supabase = await createClient();

  const { data: klass } = await supabase.from("classes").select("topic").eq("id", classId).maybeSingle();
  await supabase.from("audit_log").insert({
    actor_id: user.id, action: "deleted",
    detail: { class_id: classId, topic: klass?.topic ?? null },
  });
  const del = await supabase.from("classes").delete().eq("id", classId);
  if (del.error) throw new Error("Could not delete: " + del.error.message);

  revalidatePath("/feedback");
  revalidatePath("/dashboard");
  redirect("/feedback");
}

/** Instructor Assignment tab: save the live instructor for each class in a cohort. */
export async function saveAssignments(formData: FormData) {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) throw new Error("Not authorized.");
  const cohortId = String(formData.get("cohort_id") ?? "");
  const supabase = await createClient();

  const cache = new Map<string, string | null>();
  async function instId(name: string): Promise<string | null> {
    const n = name.trim();
    if (!n) return null;
    if (cache.has(n)) return cache.get(n)!;
    const up = await supabase.from("instructors").upsert({ name: n }, { onConflict: "name" }).select("id").single();
    const id = up.data?.id ?? null;
    cache.set(n, id);
    return id;
  }

  let changed = 0;
  for (const [key, value] of formData.entries()) {
    if (!key.startsWith("inst_")) continue;
    const classId = key.slice(5);
    const id = await instId(String(value));
    const res = await supabase
      .from("cohort_classes")
      .update({ instructor_id: id, updated_at: new Date().toISOString() })
      .eq("id", classId);
    if (!res.error) changed++;
  }

  revalidatePath("/assignments");
  redirect(`/assignments?cohort=${encodeURIComponent(cohortId)}&saved=${changed}`);
}
