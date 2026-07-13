import Link from "next/link";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MessageSquareText, ArrowRight } from "lucide-react";

export default async function DashboardPage() {
  const user = await requireUser();
  const supabase = await createClient();

  const { data: rows } = await supabase
    .from("classes")
    .select("id, topic, class_date, status, session_type, courses(name), instructors(name), analyses(reclass, tokens_in, tokens_out), feedback(status)")
    .order("created_at", { ascending: false });
  const classes = (rows ?? []) as Array<Record<string, unknown>>;

  const analyzed = classes.filter((c) => (c.analyses as unknown[] | null)?.length);
  const awaiting = classes.filter((c) => c.status === "draft_ready").length;
  const approved = classes.filter((c) => c.status === "approved" || c.status === "sent").length;
  const reclass = analyzed.filter((c) => (c.analyses as Array<{ reclass?: string }>)?.[0]?.reclass === "yes").length;

  const byCourse = new Map<string, number>();
  for (const c of analyzed) {
    const name = (c.courses as { name?: string } | null)?.name ?? "—";
    byCourse.set(name, (byCourse.get(name) ?? 0) + 1);
  }

  const stats = [
    { label: "Classes analyzed", value: analyzed.length, note: "all courses" },
    { label: "Awaiting review", value: awaiting, note: "drafts ready" },
    { label: "Approved", value: approved, note: "feedback stored" },
    { label: "Re-class flagged", value: reclass, note: "PM to decide" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {user.name.split(" ").slice(-1)[0]}</h1>
        <p className="text-muted-foreground mt-1">Interview Kickstart · Feedback & Analytics.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="pb-2">
              <CardDescription>{s.label}</CardDescription>
              <CardTitle className="text-3xl">{s.value}</CardTitle>
            </CardHeader>
            <CardContent><span className="text-muted-foreground text-xs">{s.note}</span></CardContent>
          </Card>
        ))}
      </div>

      {byCourse.size > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Analyses by course</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {[...byCourse.entries()].sort((a, b) => b[1] - a[1]).map(([name, n]) => (
              <Badge key={name} variant="secondary">{name}: {n}</Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Recent analyses</CardTitle>
          <Button asChild variant="ghost" size="sm">
            <Link href="/feedback">View all <ArrowRight className="size-4" /></Link>
          </Button>
        </CardHeader>
        <CardContent>
          {analyzed.length === 0 ? (
            <div className="text-muted-foreground flex flex-col items-center gap-3 py-8 text-center text-sm">
              <MessageSquareText className="size-6" />
              No analyses yet.
              {user.role !== "learner" && (
                <Button asChild size="sm"><Link href="/feedback/new">New analysis</Link></Button>
              )}
            </div>
          ) : (
            <div className="divide-y">
              {analyzed.slice(0, 6).map((c) => {
                const course = (c.courses as { name?: string } | null)?.name ?? "—";
                const instructor = (c.instructors as { name?: string } | null)?.name ?? "—";
                const a = (c.analyses as Array<{ reclass?: string; tokens_in?: number; tokens_out?: number }>)?.[0];
                const rc = a?.reclass;
                const tokens = (a?.tokens_in ?? 0) + (a?.tokens_out ?? 0);
                return (
                  <Link key={String(c.id)} href={`/feedback/${String(c.id)}`}
                        className="hover:bg-muted/40 -mx-2 flex items-center gap-3 rounded px-2 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{String(c.topic)}</div>
                      <div className="text-muted-foreground truncate text-xs">
                        {course} · {instructor} · {String(c.class_date)} · {c.session_type === "ars" ? "ARS" : "Live"}
                        {tokens > 0 && <> · {(tokens / 1000).toFixed(1)}k tokens</>}
                      </div>
                    </div>
                    {rc && <Badge variant={rc === "yes" ? "destructive" : rc === "maybe" ? "warning" : "secondary"} className="uppercase">{rc}</Badge>}
                    <Badge variant={c.status === "approved" || c.status === "sent" ? "success" : c.status === "draft_ready" ? "warning" : "outline"}>
                      {String(c.status).replace("_", " ")}
                    </Badge>
                  </Link>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
