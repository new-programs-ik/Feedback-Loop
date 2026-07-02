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
  const { data: courses } = await supabase.from("courses").select("id, name").order("name");

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
      <NewAnalysisForm courses={courses ?? []} />
    </div>
  );
}
