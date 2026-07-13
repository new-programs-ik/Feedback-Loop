"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/session";

export type CourseState = { error?: string; ok?: string };

function slugify(s: string): string {
  return s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

/** Add a new course (any staff member). Shows up immediately in New Analysis. */
export async function createCourse(_prev: CourseState, formData: FormData): Promise<CourseState> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) return { error: "Not authorized." };
  const name = String(formData.get("name") ?? "").trim();
  if (!name) return { error: "Enter a course name." };
  if (name.length > 120) return { error: "That name is too long." };

  const supabase = await createClient();
  const slug = slugify(name) || name.slice(0, 40);
  const ins = await supabase.from("courses").insert({ name, slug }).select("id").single();
  if (ins.error) {
    const dup = ins.error.message.toLowerCase().includes("duplicate") || ins.error.code === "23505";
    return { error: dup ? `"${name}" already exists.` : ins.error.message };
  }
  revalidatePath("/courses");
  revalidatePath("/feedback/new");
  return { ok: `Added "${name}".` };
}

/** Delete a course — admin only, and only when it has no cohorts or analyses. */
export async function deleteCourse(formData: FormData) {
  const user = await getCurrentUser();
  if (!user || user.role !== "admin") throw new Error("Only admins can delete a course.");
  const id = String(formData.get("course_id") ?? "");
  if (!id) throw new Error("Missing course.");

  const supabase = await createClient();
  const [{ count: nClasses }, { count: nCohorts }] = await Promise.all([
    supabase.from("classes").select("id", { count: "exact", head: true }).eq("course_id", id),
    supabase.from("cohorts").select("id", { count: "exact", head: true }).eq("course_id", id),
  ]);
  if ((nClasses ?? 0) > 0 || (nCohorts ?? 0) > 0) {
    throw new Error("This course still has cohorts or analyses — it can only be deleted when empty.");
  }
  const del = await supabase.from("courses").delete().eq("id", id);
  if (del.error) throw new Error("Could not delete: " + del.error.message);

  revalidatePath("/courses");
  redirect("/courses");
}
