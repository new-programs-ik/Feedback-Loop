"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/session";

/** Merge one instructor into another: reassign every reference, then delete the duplicate. */
export async function mergeInstructors(formData: FormData) {
  const user = await getCurrentUser();
  if (!user || user.role !== "admin") throw new Error("Only admins can merge instructors.");
  const fromId = String(formData.get("from_id") ?? "");
  const toId = String(formData.get("to_id") ?? "");
  if (!fromId || !toId) throw new Error("Pick both instructors.");
  if (fromId === toId) throw new Error("Pick two different instructors.");

  const supabase = await createClient();
  // Reassign every place an instructor can be referenced.
  await supabase.from("classes").update({ instructor_id: toId }).eq("instructor_id", fromId);
  await supabase.from("cohort_classes").update({ instructor_id: toId }).eq("instructor_id", fromId);
  await supabase.from("cohort_classes").update({ review_instructor_id: toId }).eq("review_instructor_id", fromId);
  await supabase.from("cohort_classes").update({ coaching_instructor_id: toId }).eq("coaching_instructor_id", fromId);
  await supabase.from("class_catalog").update({ instructor_id: toId }).eq("instructor_id", fromId);

  const del = await supabase.from("instructors").delete().eq("id", fromId);
  if (del.error) throw new Error("Could not merge: " + del.error.message);

  revalidatePath("/instructors");
  redirect("/instructors?merged=1");
}
