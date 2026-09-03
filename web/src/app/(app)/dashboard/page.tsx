import Link from "next/link";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BandDot } from "@/components/ui/table";
import { approvalTone } from "@/components/priority-chip";
import { rangeToDates } from "@/components/filter-bar";
import { fetchRatings, byCourse as ratingsByCourse, summarize } from "@/lib/ratings";
import { APPROVAL_BAR, GOOD } from "@/lib/decision";
import {
  Activity, ArrowRight, BadgeCheck, ChevronRight, CircleDollarSign, Hourglass, MessageSquareText,
  Plus, RefreshCcw,
} from "lucide-react";

export default async function DashboardPage() {
  const user = await requireUser();
  const supabase = await createClient();

  // Ping the AI worker (3s cap). Doubles as a PRE-WARM: visiting the dashboard wakes the free-tier
  // worker, so the first analysis of the day doesn't pay the cold-start wait.
  const workerUrl = process.env.ANALYSIS_WORKER_URL || "http://localhost:8000";
  const healthPromise: Promise<{ ok: boolean; video?: boolean }> = fetch(`${workerUrl}/health`, {
    signal: AbortSignal.timeout(3000),
    cache: "no-store",
  })
    .then(async (r) => (r.ok ? { ok: true, video: Boolean((await r.json()).ffmpeg) } : { ok: false }))
    .catch(() => ({ ok: false }));

  // Ratings pulse window: the last 30 days of the hourly-synced ratings feed.
  const pulseRange = rangeToDates("30d");
  const [{ data: rows }, health, pulseRows] = await Promise.all([
    supabase
      .from("classes")
      .select("id, topic, class_date, created_at, status, session_type, courses(name), instructors(name), analyses(reclass, tokens_in, tokens_out, cost_usd, created_at)")
      .order("created_at", { ascending: false }),
    healthPromise,
    fetchRatings({ from: pulseRange.from, to: pulseRange.to }),
  ]);
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
    const mk = String(src).slice(0, 7);
    if (!mk) continue;
    const cur = spendByMonth.get(mk) ?? { count: 0, cost: 0 };
    cur.count += 1;
    cur.cost += cost;
    spendByMonth.set(mk, cur);
  }
  const nowMonth = new Date().toISOString().slice(0, 7);
  const thisMonth = spendByMonth.get(nowMonth) ?? { count: 0, cost: 0 };
  const avgCost = analyzed.length ? totalCost / analyzed.length : 0;

  // Ratings pulse: which courses are hurting, judged by the team rule (below GOOD = flagged).
  const pulseCourses = ratingsByCourse(pulseRows)
    .sort((a, b) => b.bad - a.bad || b.underBar - a.underBar || (a.avgRating ?? 9) - (b.avgRating ?? 9))
    .slice(0, 5);
  const pulse = summarize(pulseRows);
  const pulseFlagged = pulse.bad;

  const stats = [
    { label: "Classes analyzed", value: analyzed.length, note: "all courses", icon: MessageSquareText, tone: "text-primary" },
    { label: "Awaiting review", value: awaiting, note: "drafts ready", icon: Hourglass, tone: "text-warning" },
    { label: "Approved", value: approved, note: "feedback stored", icon: BadgeCheck, tone: "text-success" },
    { label: "Re-class flagged", value: reclass, note: "PM to decide", icon: RefreshCcw, tone: "text-destructive" },
  ];

  return (
    <div className="animate-in-up space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome back, {user.name.split(" ")[0]}
          </h1>
          <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            Here&apos;s where your class feedback stands today.
            {health.ok ? (
              <span className="inline-flex items-center gap-1.5 text-xs">
                <span className="bg-success inline-block size-2 rounded-full" />
                AI engine online{health.video ? " · video ready" : ""}
              </span>
            ) : (
              <span className="text-muted-foreground/80 inline-flex items-center gap-1.5 text-xs">
                <span className="bg-warning inline-block size-2 rounded-full" />
                AI engine waking up — the first analysis may take an extra minute
              </span>
            )}
          </p>
        </div>
        {user.role !== "learner" && (
          <Button asChild>
            <Link href="/feedback/new"><Plus className="size-4" /> New analysis</Link>
          </Button>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="shadow-soft">
              <CardContent className="flex items-start justify-between pt-6">
                <div>
                  <div className="text-muted-foreground text-[13px] font-medium">{s.label}</div>
                  <div className="mt-1 text-3xl font-semibold tracking-tight" data-numeric>{s.value}</div>
                  <div className="text-muted-foreground/80 mt-1 text-xs">{s.note}</div>
                </div>
                <div className="bg-muted flex size-9 items-center justify-center rounded-lg">
                  <Icon className={`size-4.5 ${s.tone}`} />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Recent analyses */}
        <Card className="shadow-soft lg:col-span-3">
          <CardHeader className="flex-row items-center justify-between pb-2">
            <CardTitle className="text-base">Recent analyses</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link href="/feedback">View all <ArrowRight className="size-4" /></Link>
            </Button>
          </CardHeader>
          <CardContent>
            {analyzed.length === 0 ? (
              <div className="text-muted-foreground flex flex-col items-center gap-3 py-10 text-center text-sm">
                <MessageSquareText className="size-6" />
                No analyses yet.
                {user.role !== "learner" && (
                  <Button asChild size="sm"><Link href="/feedback/new">Run your first analysis</Link></Button>
                )}
              </div>
            ) : (
              <div className="divide-y">
                {analyzed.slice(0, 7).map((c) => {
                  const course = (c.courses as { name?: string } | null)?.name ?? "—";
                  const instructor = (c.instructors as { name?: string } | null)?.name ?? "—";
                  const a = (c.analyses as Array<{ reclass?: string; tokens_in?: number; tokens_out?: number; cost_usd?: number }>)?.[0];
                  const rc = a?.reclass;
                  const cost = Number(a?.cost_usd ?? 0);
                  return (
                    <Link key={String(c.id)} href={`/feedback/${String(c.id)}`}
                          className="hover:bg-accent/40 -mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors">
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{String(c.topic)}</div>
                        <div className="text-muted-foreground truncate text-xs">
                          {course} · {instructor} · {String(c.class_date)} · {c.session_type === "ars" ? "ARS" : "Live"}
                          {cost > 0 && <> · <span className="text-foreground/80 font-medium">{money(cost)}</span></>}
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

        <div className="space-y-6 lg:col-span-2">
        {/* Spending */}
        <Card className="shadow-soft">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <CircleDollarSign className="text-primary size-4" /> AI spending
            </CardTitle>
            <CardDescription>Exact cost, tracked per analysis.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <div className="text-xl font-semibold" data-numeric>{money(thisMonth.cost)}</div>
                <div className="text-muted-foreground text-[11px]">this month</div>
              </div>
              <div>
                <div className="text-xl font-semibold" data-numeric>{money(totalCost)}</div>
                <div className="text-muted-foreground text-[11px]">all time</div>
              </div>
              <div>
                <div className="text-xl font-semibold" data-numeric>{money(avgCost)}</div>
                <div className="text-muted-foreground text-[11px]">avg / class</div>
              </div>
            </div>
            {spendByMonth.size > 0 && (
              <div className="space-y-1.5">
                {[...spendByMonth.entries()].sort((a, b) => b[0].localeCompare(a[0])).slice(0, 6).map(([m, v]) => {
                  const max = Math.max(...[...spendByMonth.values()].map((x) => x.cost), 0.01);
                  return (
                    <div key={m} className="flex items-center gap-2 text-xs">
                      <span className="text-muted-foreground w-16 shrink-0">{prettyMonth(m)}</span>
                      <div className="bg-muted h-2 flex-1 overflow-hidden rounded-full">
                        <div className="bg-primary/70 h-full rounded-full"
                             style={{ width: `${Math.max(4, (v.cost / max) * 100)}%` }} />
                      </div>
                      <span className="w-14 shrink-0 text-right font-medium" data-numeric>{money(v.cost)}</span>
                    </div>
                  );
                })}
              </div>
            )}
            {byCourse.size > 0 && (
              <div className="border-t pt-3">
                <div className="text-muted-foreground mb-2 text-[11px] font-medium uppercase tracking-wide">By course</div>
                <div className="flex flex-wrap gap-1.5">
                  {[...byCourse.entries()].sort((a, b) => b[1] - a[1]).map(([name, n]) => (
                    <Badge key={name} variant="secondary">{name} · {n}</Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Ratings pulse — only when the ratings feed has rows in the window */}
        {pulseRows.length > 0 && (
          <Card className="shadow-soft">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="text-primary size-4" /> Ratings pulse — by course
              </CardTitle>
              <CardDescription>
                Classes rated below {GOOD} in the last 30 days, and the share of each room that would have the instructor back.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="divide-y">
                {pulseCourses.map((c) => (
                  <div key={c.key} className="flex items-center gap-2.5 py-2 first:pt-0 last:pb-0">
                    <div className="min-w-0 flex-1 truncate text-[13px] font-medium">{c.name}</div>
                    {c.bad > 0 ? (
                      <span className="bg-destructive/8 text-destructive inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-semibold" data-numeric>
                        {c.bad} below
                      </span>
                    ) : (
                      <span className="text-muted-foreground shrink-0 text-xs" data-numeric>0 below</span>
                    )}
                    <span className="w-14 shrink-0 text-right text-[13px]" data-numeric>
                      <BandDot tone={c.avgRating != null && c.avgRating < GOOD ? "bad" : c.avgRating != null && c.avgRating < 4.7 ? "warn" : "good"} />
                      {c.avgRating != null ? c.avgRating.toFixed(2) : "—"}
                    </span>
                    <span
                      className={`w-14 shrink-0 text-right text-[13px] ${
                        c.approval != null && c.approval < APPROVAL_BAR ? "text-destructive font-semibold" : "text-muted-foreground"
                      }`}
                      data-numeric
                      title="Share of voters who would have the instructor back"
                    >
                      {c.approval != null ? <><BandDot tone={approvalTone(c.approval)} />{Math.round(c.approval)}%</> : "—"}
                    </span>
                    <Link
                      href={c.courseId ? `/ratings?course=${c.courseId}` : "/ratings"}
                      aria-label={`Ratings for ${c.name}`}
                      className="text-muted-foreground/60 hover:text-foreground shrink-0"
                    >
                      <ChevronRight className="size-4" aria-hidden />
                    </Link>
                  </div>
                ))}
              </div>
              <div className="border-t pt-3">
                <Link
                  href="/ratings"
                  className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                >
                  <span>
                    <span className="text-foreground font-semibold" data-numeric>{pulseFlagged}</span> below {GOOD}
                    {pulse.underBar > 0 && (
                      <>
                        {" "}· <span className="text-foreground font-semibold" data-numeric>{pulse.underBar}</span> under {APPROVAL_BAR}%
                      </>
                    )}{" "}
                    in 30 days — open the queue
                  </span>
                  <ArrowRight className="size-3.5 shrink-0" aria-hidden />
                </Link>
              </div>
            </CardContent>
          </Card>
        )}
        </div>
      </div>
    </div>
  );
}
