import { redirect } from "next/navigation";
import Link from "next/link";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { NewAnalysisForm } from "./new-analysis-form";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

export default async function NewAnalysisPage() {
  const user = await requireUser();
  if (user.role === "learner") redirect("/dashboard");

  const supabase = await createClient();
  const [{ data: courses }, { data: cohorts }, { data: classes }, { data: instructors }] = await Promise.all([
    supabase.from("courses").select("id, name").order("name"),
    supabase.from("cohorts").select("id, course_id, name").order("name"),
    supabase.from("cohort_classes")
      .select("id, cohort_id, topic, class_date, instructor:instructor_id(name)")
      .order("class_date"),
    supabase.from("instructors").select("name").order("name"),
  ]);

  const cohortsByCourse: Record<string, { id: string; name: string }[]> = {};
  for (const c of (cohorts ?? []) as Array<Record<string, unknown>>) {
    (cohortsByCourse[String(c.course_id)] ??= []).push({ id: String(c.id), name: String(c.name) });
  }
  const classesByCohort: Record<string, { id: string; topic: string; date: string; instructor: string }[]> = {};
  for (const c of (classes ?? []) as Array<Record<string, unknown>>) {
    (classesByCohort[String(c.cohort_id)] ??= []).push({
      id: String(c.id),
      topic: String(c.topic),
      date: c.class_date ? String(c.class_date) : "",
      instructor: (c.instructor as { name?: string } | null)?.name ?? "",
    });
  }
  const instructorNames = ((instructors ?? []) as Array<{ name: string }>).map((i) => i.name);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="icon">
          <Link href="/feedback" aria-label="Back to queue">
            <ArrowLeft className="size-4" />
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">New analysis</h1>
      </div>
      <NewAnalysisForm
        courses={courses ?? []}
        cohortsByCourse={cohortsByCourse}
        classesByCohort={classesByCohort}
        instructorNames={instructorNames}
      />
    </div>
  );
}
