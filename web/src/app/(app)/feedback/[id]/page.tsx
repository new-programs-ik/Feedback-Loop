import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft } from "lucide-react";
import { ReviewActions } from "./review-actions";
import { DeleteButton } from "../delete-button";

function sevVariant(s?: string): "destructive" | "warning" | "secondary" {
  return s === "major" ? "destructive" : s === "moderate" ? "warning" : "secondary";
}

type Evidence = { timestamp?: string; quote?: string };
type Flag = { flag?: string; severity?: string; confidence?: string; evidence?: Evidence[] };
type Result = {
  overall?: string;
  flags?: Flag[];
  feedback?: string;
  reclass?: { recommended?: string; reason?: string; deciding_flags?: string[] };
};

export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requireUser();
  const supabase = await createClient();

  const { data: klass } = await supabase
    .from("classes")
    .select("*, courses(name), instructors(name), cohorts(name), analyses(*), feedback(*)")
    .eq("id", id)
    .single();
  if (!klass) notFound();

  const analyses = (klass.analyses ?? []) as Array<Record<string, unknown>>;
  const analysis = analyses[analyses.length - 1];
  const feedbacks = (klass.feedback ?? []) as Array<Record<string, unknown>>;
  const feedback = feedbacks[feedbacks.length - 1];
  const result = (analysis?.result ?? {}) as Result;
  const draft = String(feedback?.edited_text ?? feedback?.draft_text ?? "");
  const fbStatus = String(feedback?.status ?? "draft");
  const done = fbStatus === "approved" || fbStatus === "sent";
  const course = (klass.courses as { name?: string } | null)?.name ?? "—";
  const instructor = (klass.instructors as { name?: string } | null)?.name ?? "—";
  const cohort = (klass.cohorts as { name?: string } | null)?.name ?? "—";
  const rating = klass.rating as number | null;
  const reclass = result.reclass;

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="icon">
          <Link href="/feedback" aria-label="Back to queue">
            <ArrowLeft className="size-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{String(klass.topic)}</h1>
            <Badge variant="outline">{klass.session_type === "ars" ? "ARS" : "Live"}</Badge>
          </div>
          <p className="text-muted-foreground text-sm">
            {course} · {instructor} · {cohort} · {String(klass.class_date)}
            {rating != null && <> · rating <strong>{Number(rating).toFixed(2)}</strong></>}
          </p>
        </div>
        <DeleteButton classId={String(klass.id)} />
      </div>

      {!analysis ? (
        <Card>
          <CardContent className="text-muted-foreground py-10 text-center text-sm">
            No analysis yet for this class (status: {String(klass.status)}).
          </CardContent>
        </Card>
      ) : (
        <>
          {result.overall && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Overall</CardTitle>
              </CardHeader>
              <CardContent className="text-sm leading-relaxed">{result.overall}</CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Flags ({result.flags?.length ?? 0})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(result.flags ?? []).map((f, i) => (
                <div key={i} className="rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{f.flag}</span>
                    <Badge variant={sevVariant(f.severity)}>{f.severity}</Badge>
                    <span className="text-muted-foreground text-xs">{f.confidence} confidence</span>
                  </div>
                  {(f.evidence ?? []).map((e, j) => (
                    <p key={j} className="text-muted-foreground mt-1.5 text-sm">
                      <span className="font-mono text-xs">[{e.timestamp}]</span> “{e.quote}”
                    </p>
                  ))}
                </div>
              ))}
              {(result.flags ?? []).length === 0 && (
                <p className="text-muted-foreground text-sm">No flags raised.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between pb-2">
              <CardTitle className="text-base">Instructor feedback</CardTitle>
              {done && <Badge variant="success">Approved</Badge>}
            </CardHeader>
            <CardContent>
              <ReviewActions classId={String(klass.id)} initialText={draft} done={done} />
            </CardContent>
          </Card>

          {reclass?.recommended && (
            <Card className="border-amber-300/60">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  Re-class recommendation
                  <Badge variant="outline">PM only — not shown to the instructor</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={reclass.recommended === "yes" ? "destructive" : reclass.recommended === "maybe" ? "warning" : "secondary"}
                    className="uppercase"
                  >
                    {reclass.recommended}
                  </Badge>
                  {reclass.deciding_flags && reclass.deciding_flags.length > 0 && (
                    <span className="text-muted-foreground text-xs">
                      deciding: {reclass.deciding_flags.join(", ")}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground">{reclass.reason}</p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
