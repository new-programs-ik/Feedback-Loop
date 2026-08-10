import { redirect } from "next/navigation";
import Link from "next/link";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { NewAnalysisForm } from "./new-analysis-form";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

// Give the analysis kick-off (Vimeo fetch + handing the job to the worker) the platform max.
export const maxDuration = 60;

export default async function NewAnalysisPage() {
  const user = await requireUser();
  if (user.role === "learner") redirect("/dashboard");

  const supabase = await createClient();
  const [{ data: courses }, { data: instructors }] = await Promise.all([
    supabase.from("courses").select("id, name").order("name"),
    supabase.from("instructors").select("name").order("name"),
  ]);
  const instructorNames = ((instructors ?? []) as Array<{ name: string }>).map((i) => i.name);

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
      <NewAnalysisForm courses={courses ?? []} instructorNames={instructorNames} />
    </div>
  );
}
