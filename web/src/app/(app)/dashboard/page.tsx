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
    .select("id, topic, class_date, created_at, status, session_type, courses(name), instructors(name), analyses(reclass, tokens_in, tokens_out, cost_usd, created_at), feedback(status)")
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

  // Spending: the exact $ cost is stored per analysis. Group it by the month it was run.
  const money = (n: number) => `$${n.toFixed(2)}`;
  const prettyMonth = (m: string) => {
    const [y, mo] = m.split("-").map(Number);
    return new Date(y, mo - 1, 1).toLocaleString("en-US", { month: "short", year: "numeric" });
  };
  const spendByMonth = new Map<string, { count: number; cost: number }>();
  let totalCost = 0;
  for (const c of analyzed) {
    const a = (c.analyses as Array<{ cost_usd?: number; created_at?: string }>)?.[0];
    const cost = Number(a?.cost_usd ?? 0);
    totalCost += cost;
    const src = a?.created_at || (c.created_at as string) || (c.class_date as string) || "";
    const mk = String(src).slice(0, 7); // YYYY-MM
    if (!mk) continue;
    const cur = spendByMonth.get(mk) ?? { count: 0, cost: 0 };
    cur.count += 1;
    cur.cost += cost;
    spendByMonth.set(mk, cur);
  }
  const nowMonth = new Date().toISOString().slice(0, 7);
  const thisMonth = spendByMonth.get(nowMonth) ?? { count: 0, cost: 0 };
  const avgCost = analyzed.length ? totalCost / analyzed.length : 0;

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

      {analyzed.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Spending on AI analysis</CardTitle>
            <CardDescription>What the AI analysis has cost — this month, in total, and month by month.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-8">
              <div>
                <div className="text-2xl font-semibold">{money(thisMonth.cost)}</div>
                <div className="text-muted-foreground text-xs">this month · {thisMonth.count} analyses</div>
              </div>
              <div>
                <div className="text-2xl font-semibold">{money(totalCost)}</div>
                <div className="text-muted-foreground text-xs">all time · {analyzed.length} analyses</div>
              </div>
              <div>
                <div className="text-2xl font-semibold">{money(avgCost)}</div>
                <div className="text-muted-foreground text-xs">avg per analysis</div>
              </div>
            </div>
            {spendByMonth.size > 0 && (
              <div className="overflow-hidden rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-muted-foreground text-left">
                    <tr>
                      <th className="px-4 py-2 font-medium">Month</th>
                      <th className="px-4 py-2 font-medium">Analyses</th>
                      <th className="px-4 py-2 font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...spendByMonth.entries()].sort((a, b) => b[0].localeCompare(a[0])).slice(0, 6).map(([m, v]) => (
                      <tr key={m} className="border-t">
                        <td className="px-4 py-2">{prettyMonth(m)}</td>
                        <td className="text-muted-foreground px-4 py-2">{v.count}</td>
                        <td className="px-4 py-2 font-medium">{money(v.cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="text-muted-foreground text-xs">
              Reading the transcript costs $3 per million tokens; writing the feedback costs $15 per million —
              usually about $1 per class. Exact costs are tracked per analysis.
            </p>
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
                const a = (c.analyses as Array<{ reclass?: string; tokens_in?: number; tokens_out?: number; cost_usd?: number }>)?.[0];
                const rc = a?.reclass;
                const tokens = (a?.tokens_in ?? 0) + (a?.tokens_out ?? 0);
                const cost = Number(a?.cost_usd ?? 0);
                return (
                  <Link key={String(c.id)} href={`/feedback/${String(c.id)}`}
                        className="hover:bg-muted/40 -mx-2 flex items-center gap-3 rounded px-2 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{String(c.topic)}</div>
                      <div className="text-muted-foreground truncate text-xs">
                        {course} · {instructor} · {String(c.class_date)} · {c.session_type === "ars" ? "ARS" : "Live"}
                        {tokens > 0 && <> · {(tokens / 1000).toFixed(1)}k tokens</>}
                        {cost > 0 && <> · <span className="font-medium">{money(cost)}</span></>}
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
