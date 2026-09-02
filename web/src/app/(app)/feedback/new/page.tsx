import { redirect } from "next/navigation";
import Link from "next/link";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { NewAnalysisForm } from "./new-analysis-form";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

// Give the analysis kick-off (Vimeo fetch + handing the job to the worker) the platform max.
export const maxDuration = 60;

export default async function NewAnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{ prefill?: string }>;
}) {
  const user = await requireUser();
  if (user.role === "learner") redirect("/dashboard");

  const supabase = await createClient();
  const { prefill: prefillId } = await searchParams;
  const [{ data: courses }, { data: instructors }, prefillRes] = await Promise.all([
    supabase.from("courses").select("id, name").order("name"),
    supabase.from("instructors").select("name").order("name"),
    prefillId
      ? supabase
          .from("class_ratings")
          .select("id, course_id, topic, instructor, class_date, session_kind, rating, num_ratings, attended, escalated, decision")
          .eq("id", prefillId)
          .maybeSingle()
      : Promise.resolve({ data: null }),
  ]);
  const instructorNames = ((instructors ?? []) as Array<{ name: string }>).map((i) => i.name);
  const p = prefillRes.data as {
    id: string; course_id: string | null; topic: string; instructor: string; class_date: string;
    session_kind: string; rating: number; num_ratings: number | null; attended: number | null;
    escalated: boolean; decision: string;
  } | null;
  // One click from the Needs-analysis queue lands here with everything filled in.
  const prefill = p
    ? {
        classRatingId: p.id,
        courseId: p.course_id ?? "",
        topic: p.topic,
        instructor: p.instructor,
        classDate: p.class_date,
        classType: (p.session_kind === "Test Review" ? "ars" : "live_class") as "ars" | "live_class",
        rating: String(p.rating),
        numRatings: p.num_ratings != null ? String(p.num_ratings) : "",
        attended: p.attended != null ? String(p.attended) : "",
        escalated: p.escalated,
        video: p.decision === "video",
      }
    : undefined;

  return (
    <div className="animate-in-up space-y-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="icon">
          <Link href="/feedback" aria-label="Back to queue">
            <ArrowLeft className="size-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">New analysis</h1>
          <p className="text-muted-foreground text-sm">
            Point the AI at a class recording — it drafts the feedback, you approve it.
          </p>
        </div>
      </div>
      <NewAnalysisForm courses={courses ?? []} instructorNames={instructorNames} prefill={prefill} />
    </div>
  );
}
