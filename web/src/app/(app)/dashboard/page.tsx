import Link from "next/link";
import {
  Activity, ArrowRight, BadgeCheck, ChevronRight, CircleAlert, CircleDollarSign, Hourglass, ListChecks,
  Loader2, MessageSquareText, Plus, RefreshCcw, Send, TrendingDown, TriangleAlert, XCircle, type LucideIcon,
} from "lucide-react";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { fetchRatings, byCourse as ratingsByCourse, isBad, lastSyncRun, summarize, type ClassRating } from "@/lib/ratings";
import { APPROVAL_BAR, GOOD, type HealthBand } from "@/lib/decision";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatTile } from "@/components/ui/stat-tile";
import { Sparkline } from "@/components/charts/sparkline";
import { PriorityChip } from "@/components/priority-chip";
import { CountUp } from "@/components/motion/count-up";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { Greeting } from "@/components/dashboard/greeting";
import { PulseBars, type PulseRow } from "@/components/dashboard/pulse-bars";
import { SpendRings, type SpendMonth } from "@/components/dashboard/spend-rings";
import { cn } from "@/lib/utils";

export const metadata = { title: "Dashboard" };

type Analysis = { reclass?: string | null; cost_usd?: number | string | null; created_at?: string | null };
type Feedback = { status?: string | null; approved_at?: string | null; sent_at?: string | null };
type ClassRow = {
  id: string;
  topic: string;
  class_date: string;
  created_at: string;
  updated_at?: string | null;
  status: string;
  session_type: string;
  courses: { name?: string } | null;
  instructors: { name?: string } | null;
  analyses: Analysis[] | null;
  feedback: Feedback[] | null;
};

const day = (ts: string | null | undefined) => (ts ?? "").slice(0, 10);
const prettyMonth = (m: string) => {
  const [y, mo] = m.split("-").map(Number);
  return new Date(y, mo - 1, 1).toLocaleString("en-US", { month: "short" });
};
const prettyDate = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

const BANDS: HealthBand[] = ["urgent", "look", "borderline"];
const bandRank = (r: ClassRating) => (r.health_band ? BANDS.indexOf(r.health_band) : BANDS.length);
/** Same order as the queue: urgent first, then the lowest Health Score, then the lowest rating. */
const byPriority = (a: ClassRating, b: ClassRating) =>
  bandRank(a) - bandRank(b) ||
  (a.health_score ?? Infinity) - (b.health_score ?? Infinity) ||
  a.rating - b.rating;

type EventKind = "analysis" | "approved" | "sent" | "analyzing" | "failed";
const EVENT: Record<EventKind, { label: string; icon: LucideIcon; token: string }> = {
  analysis: { label: "Analysis ready", icon: MessageSquareText, token: "var(--primary)" },
  approved: { label: "Approved", icon: BadgeCheck, token: "var(--success)" },
  sent: { label: "Sent to the instructor", icon: Send, token: "var(--success)" },
  analyzing: { label: "Analyzing now", icon: Loader2, token: "var(--warning)" },
  failed: { label: "Analysis failed", icon: XCircle, token: "var(--destructive)" },
};

type Delta = { text: string; suffix?: string; good?: boolean; direction?: "up" | "down" };
const deltaOf = (d: number, suffix: string, upIsGood: boolean): Delta | undefined =>
  d === 0
    ? undefined
    : { text: `${d > 0 ? "+" : "−"}${Math.abs(d)}`, suffix, good: upIsGood ? d > 0 : d < 0, direction: d > 0 ? "up" : "down" };

/** The overview's card: a quiet title row and the content; height fills the grid cell. */
function Panel({
  title,
  description,
  icon: Icon,
  action,
  className,
  children,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("bg-card shadow-soft flex h-full flex-col rounded-xl border p-5", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[13.5px] font-semibold tracking-[-0.01em]">
            {Icon && <Icon className="text-primary size-4" aria-hidden />}
            {title}
          </h2>
          {description && <p className="text-muted-foreground mt-0.5 text-xs">{description}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <div className="flex-1">{children}</div>
    </section>
  );
}

export default async function DashboardPage() {
  const user = await requireUser();
  const supabase = await createClient();

  // "Now" is read ONCE per request; every window and every relative time keys off it.
  const now = new Date();
  const nowMs = now.getTime();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const daysAgo = (n: number) => new Date(nowMs - n * 86400000);
  const to = iso(now);
  const from30 = iso(daysAgo(30));
  const from45 = iso(daysAgo(45));
  const from60 = iso(daysAgo(60));
  const nowMonth = to.slice(0, 7);

  // Ping the AI worker (3s cap). Doubles as a PRE-WARM: visiting the dashboard wakes the free-tier
  // worker, so the first analysis of the day doesn't pay the cold-start wait.
  const workerUrl = process.env.ANALYSIS_WORKER_URL || "http://localhost:8000";
  const healthPromise: Promise<{ ok: boolean; video?: boolean }> = fetch(`${workerUrl}/health`, {
    signal: AbortSignal.timeout(3000),
    cache: "no-store",
  })
    .then(async (r) => (r.ok ? { ok: true, video: Boolean((await r.json()).ffmpeg) } : { ok: false }))
    .catch(() => ({ ok: false }));

  // One 60-day pull of the hourly-synced ratings feed serves three views: the last 30 days
  // (the pulse), the 30 before that (the delta baseline) and the 45-day queue window.
  const [{ data: rows }, health, ratingRows, run] = await Promise.all([
    supabase
      .from("classes")
      .select(
        "id, topic, class_date, created_at, updated_at, status, session_type, courses(name), instructors(name), analyses(reclass, cost_usd, created_at), feedback(status, approved_at, sent_at)",
      )
      .order("created_at", { ascending: false }),
    healthPromise,
    fetchRatings({ from: from60, to }),
    lastSyncRun(),
  ]);
  const classes = (rows ?? []) as unknown as ClassRow[];
  const analysisOf = (c: ClassRow) => c.analyses?.[0];
  const feedbackOf = (c: ClassRow) => {
    const f = c.feedback ?? [];
    return f[f.length - 1];
  };

  // ── analyses ────────────────────────────────────────────────────────────────
  const analyzed = classes.filter((c) => (c.analyses ?? []).length > 0);
  const awaiting = classes.filter((c) => c.status === "draft_ready");
  const approvedAll = classes.filter((c) => c.status === "approved" || c.status === "sent");
  const reclass = analyzed.filter((c) => analysisOf(c)?.reclass === "yes").length;

  const inCurrent = (d: string) => d >= from30;
  const inPrior = (d: string) => d >= from60 && d < from30;
  const analysisDates = analyzed.map((c) => day(analysisOf(c)?.created_at)).filter(Boolean);
  const approvedDates = approvedAll.map((c) => day(feedbackOf(c)?.approved_at)).filter(Boolean);
  const analysesCur = analysisDates.filter(inCurrent).length;
  const analysesPrev = analysisDates.filter(inPrior).length;
  const approvedCur = approvedDates.filter(inCurrent).length;
  const approvedPrev = approvedDates.filter(inPrior).length;

  /** Weekly buckets over the last `weeks` weeks, oldest → newest; the newest ends tomorrow so
   *  today counts. Feeds the stat-tile sparklines. */
  const weekly = (dates: string[], weeks = 8) =>
    Array.from({ length: weeks }, (_, k) => {
      const i = weeks - 1 - k;
      const start = iso(daysAgo(7 * i + 6));
      const end = iso(daysAgo(7 * i - 1));
      return dates.filter((d) => d >= start && d < end).length;
    });

  // ── spending: the exact $ cost is stored per analysis, grouped by the month it was run ──
  const byCourse = new Map<string, number>();
  const spendByMonth = new Map<string, { count: number; cost: number }>();
  let totalCost = 0;
  for (const c of analyzed) {
    byCourse.set(c.courses?.name ?? "—", (byCourse.get(c.courses?.name ?? "—") ?? 0) + 1);
    const a = analysisOf(c);
    const cost = Number(a?.cost_usd ?? 0);
    totalCost += cost;
    const mk = day(a?.created_at || c.created_at || c.class_date).slice(0, 7);
    if (!mk) continue;
    const cur = spendByMonth.get(mk) ?? { count: 0, cost: 0 };
    cur.count += 1;
    cur.cost += cost;
    spendByMonth.set(mk, cur);
  }
  const thisMonth = spendByMonth.get(nowMonth) ?? { count: 0, cost: 0 };
  const avgCost = analyzed.length ? totalCost / analyzed.length : 0;
  const [ny, nm] = nowMonth.split("-").map(Number);
  const prevMonthKey = nm === 1 ? `${ny - 1}-12` : `${ny}-${String(nm - 1).padStart(2, "0")}`;
  const lastMonth = spendByMonth.get(prevMonthKey);
  const ringMonths: SpendMonth[] = [...spendByMonth.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-6)
    .map(([key, v]) => ({ key, label: prettyMonth(key), cost: v.cost, count: v.count, current: key === nowMonth }));

  // ── ratings pulse + the queue (the same rule the Needs-analysis page applies) ──
  const pulseRows = ratingRows.filter((r) => r.class_date >= from30);
  const priorRows = ratingRows.filter((r) => r.class_date < from30);
  const pulse = summarize(pulseRows);
  const prior = summarize(priorRows);
  const badSpark = weekly(ratingRows.filter(isBad).map((r) => r.class_date));

  const queue = ratingRows
    .filter(
      (r) =>
        r.class_date >= from45 &&
        (r.decision === "video" || r.decision === "transcript") &&
        (r.review_status === "new" || r.review_status === "notified" || r.review_status === "confirmed"),
    )
    .sort(byPriority);
  const urgent = queue.filter((r) => r.health_band === "urgent").length;
  const look = queue.filter((r) => r.health_band === "look").length;
  const topOfQueue = queue.slice(0, 3);
  const urgentByCourse = new Map<string, number>();
  for (const r of queue) {
    if (r.health_band !== "urgent") continue;
    const key = r.course_id ?? `label:${r.course_label}`;
    urgentByCourse.set(key, (urgentByCourse.get(key) ?? 0) + 1);
  }
  const pulseCourses: PulseRow[] = ratingsByCourse(pulseRows)
    .sort((a, b) => b.bad - a.bad || b.underBar - a.underBar || (a.avgRating ?? 9) - (b.avgRating ?? 9))
    .slice(0, 5)
    .map((c) => ({
      key: c.key,
      name: c.name,
      href: c.courseId ? `/ratings?course=${c.courseId}` : "/ratings",
      classes: c.n,
      below: c.bad,
      avgRating: c.avgRating,
      approval: c.approval,
      urgent: urgentByCourse.get(c.key) ?? 0,
    }));
  const pulseMax = Math.max(...pulseCourses.map((c) => c.below), 1);

  // ── the one-line status ─────────────────────────────────────────────────────
  const syncedMin = run?.finished_at ? Math.round((nowMs - +new Date(run.finished_at)) / 60000) : null;
  const syncLabel =
    syncedMin == null ? null : syncedMin < 1 ? "just now" : syncedMin < 60 ? `${syncedMin} min ago` : `${Math.round(syncedMin / 60)}h ago`;
  const statusBits: string[] = [];
  if (urgent > 0) statusBits.push(`${urgent} urgent ${plural(urgent, "class needs", "classes need")} a decision`);
  else if (look > 0) statusBits.push(`${look} ${plural(look, "class needs", "classes need")} a look`);
  else statusBits.push("the queue is clear");
  if (awaiting.length > 0) statusBits.push(`${awaiting.length} ${plural(awaiting.length, "draft awaits", "drafts await")} review`);
  if (syncLabel) statusBits.push(`last sync ${syncLabel}`);
  const statusSentence = statusBits.join(" · ");

  // ── needs-you-now rows ──────────────────────────────────────────────────────
  type Need = { key: string; icon: LucideIcon; tone: string; label: string; sub: string; count: number; href: string };
  const needs: Need[] = [];
  if (urgent > 0)
    needs.push({ key: "urgent", icon: TriangleAlert, tone: "text-destructive", label: "Urgent — video analysis", sub: "Health Score under 70", count: urgent, href: "/ratings" });
  if (look > 0)
    needs.push({ key: "look", icon: CircleAlert, tone: "text-warning", label: "Needs a look", sub: "under a bar, with enough voices", count: look, href: "/ratings" });
  if (awaiting.length > 0)
    needs.push({
      key: "drafts", icon: Hourglass, tone: "text-warning", label: "Drafts awaiting your approval", sub: "review, tweak, approve",
      count: awaiting.length, href: awaiting.length === 1 ? `/feedback/${awaiting[0].id}` : "/feedback",
    });
  if (reclass > 0)
    needs.push({ key: "reclass", icon: RefreshCcw, tone: "text-destructive", label: "Re-class flagged", sub: "PM to decide", count: reclass, href: "/feedback" });

  // ── recent activity: analyses, approvals, sends — and the ones still running ──
  type Event = { key: string; at: number; kind: EventKind; c: ClassRow };
  const events: Event[] = [];
  for (const c of classes) {
    const a = analysisOf(c);
    const f = feedbackOf(c);
    if (a?.created_at) events.push({ key: `a-${c.id}`, at: +new Date(a.created_at), kind: "analysis", c });
    else if (c.status === "analyzing") events.push({ key: `r-${c.id}`, at: +new Date(c.created_at), kind: "analyzing", c });
    else if (c.status === "failed") events.push({ key: `x-${c.id}`, at: +new Date(c.updated_at ?? c.created_at), kind: "failed", c });
    if (f?.approved_at && (f.status === "approved" || f.status === "sent"))
      events.push({ key: `ok-${c.id}`, at: +new Date(f.approved_at), kind: "approved", c });
    if (f?.sent_at && f.status === "sent") events.push({ key: `s-${c.id}`, at: +new Date(f.sent_at), kind: "sent", c });
  }
  const recent = events
    .filter((e) => Number.isFinite(e.at))
    .sort((a, b) => b.at - a.at)
    .slice(0, 8);
  const ago = (ms: number) => {
    const m = Math.max(0, Math.round((nowMs - ms) / 60000));
    if (m < 1) return "just now";
    if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.round(h / 24);
    if (d < 7) return `${d}d ago`;
    return new Date(ms).toLocaleDateString("en-US", { day: "numeric", month: "short" });
  };

  const staff = user.role !== "learner";

  return (
    <div className="space-y-8">
      {/* ── greeting + status ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <Greeting name={user.name.split(" ")[0]} status={statusSentence}>
          {health.ok ? (
            <span className="inline-flex items-center gap-1.5 text-xs">
              <span className="bg-success inline-block size-2 rounded-full" aria-hidden />
              AI engine online{health.video ? " · video ready" : ""}
            </span>
          ) : (
            <span className="text-muted-foreground/80 inline-flex items-center gap-1.5 text-xs">
              <span className="bg-warning inline-block size-2 rounded-full" aria-hidden />
              AI engine waking up — the first analysis may take an extra minute
            </span>
          )}
        </Greeting>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <Link href="/ratings">
              <ListChecks className="size-4" aria-hidden /> Open queue
            </Link>
          </Button>
          {staff && (
            <Button asChild>
              <Link href="/feedback/new">
                <Plus className="size-4" aria-hidden /> New analysis
              </Link>
            </Button>
          )}
        </div>
      </div>

      {/* ── KPI row ───────────────────────────────────────────────────────── */}
      <Stagger className="grid grid-cols-12 gap-4" step={0.07}>
        <StaggerItem className="col-span-12 sm:col-span-6 xl:col-span-3">
          <StatTile
            className="h-full"
            label="Classes analyzed"
            icon={MessageSquareText}
            count={{ value: analyzed.length }}
            note={`${analysesCur} in the last 30 days`}
            delta={deltaOf(analysesCur - analysesPrev, "vs prior 30d", true)}
            sparkline={<Sparkline values={weekly(analysisDates)} />}
          />
        </StaggerItem>
        <StaggerItem className="col-span-12 sm:col-span-6 xl:col-span-3">
          <StatTile
            className="h-full"
            label="Awaiting review"
            icon={Hourglass}
            tone={awaiting.length > 0 ? "warning" : "default"}
            count={{ value: awaiting.length }}
            note={reclass > 0 ? `drafts ready · ${reclass} re-class flagged` : "drafts ready to approve"}
          />
        </StaggerItem>
        <StaggerItem className="col-span-12 sm:col-span-6 xl:col-span-3">
          <StatTile
            className="h-full"
            label="Approved"
            icon={BadgeCheck}
            count={{ value: approvedAll.length }}
            note={`${approvedCur} in the last 30 days`}
            delta={deltaOf(approvedCur - approvedPrev, "vs prior 30d", true)}
            sparkline={<Sparkline values={weekly(approvedDates)} accent="var(--success)" />}
          />
        </StaggerItem>
        <StaggerItem className="col-span-12 sm:col-span-6 xl:col-span-3">
          <StatTile
            className="h-full"
            label={`Below ${GOOD} · 30 days`}
            icon={TrendingDown}
            tone={pulse.bad > 0 ? "destructive" : "default"}
            count={{ value: pulse.bad }}
            note={pulse.underBar > 0 ? `${pulse.underBar} under ${APPROVAL_BAR}% approval` : pulse.bad === 0 ? "none flagged by rating" : "rated classes"}
            delta={deltaOf(pulse.bad - prior.bad, "vs prior 30d", false)}
            sparkline={<Sparkline values={badSpark} accent="var(--viz-bad)" />}
          />
        </StaggerItem>
      </Stagger>

      {/* ── needs you now · ratings pulse ─────────────────────────────────── */}
      <div className="grid grid-cols-12 gap-6">
        <Reveal className="col-span-12 xl:col-span-5">
          <Panel
            title="Needs you now"
            icon={Activity}
            description="Flagged by the team rule in the last 45 days, plus drafts waiting on you."
          >
            {needs.length === 0 ? (
              <div className="flex items-center gap-3 py-4">
                <span className="bg-success/10 text-success flex size-9 shrink-0 items-center justify-center rounded-full">
                  <ListChecks className="size-4" aria-hidden />
                </span>
                <div>
                  <div className="text-[13px] font-medium">Nothing needs you right now</div>
                  <div className="text-muted-foreground text-xs">Every flagged class is handled and no drafts are waiting.</div>
                </div>
              </div>
            ) : (
              <Stagger className="divide-y" step={0.06}>
                {needs.map((n) => {
                  const Icon = n.icon;
                  return (
                    <StaggerItem key={n.key}>
                      <Link
                        href={n.href}
                        className="group -mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-accent/40"
                      >
                        <span className="bg-muted flex size-8 shrink-0 items-center justify-center rounded-lg">
                          <Icon className={cn("size-4", n.tone)} aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">{n.label}</span>
                          <span className="text-muted-foreground block truncate text-xs">{n.sub}</span>
                        </span>
                        <CountUp value={n.count} duration={0.9} className="text-lg font-semibold tracking-tight" />
                        <ChevronRight
                          className="text-muted-foreground/50 group-hover:text-foreground size-4 shrink-0 transition-colors"
                          aria-hidden
                        />
                      </Link>
                    </StaggerItem>
                  );
                })}
              </Stagger>
            )}

            {topOfQueue.length > 0 && (
              <div className="mt-4 border-t pt-3">
                <div className="text-muted-foreground mb-1.5 text-[11px] font-medium tracking-wide uppercase">Top of the queue</div>
                <Stagger className="space-y-0.5" step={0.06} delay={0.2}>
                  {topOfQueue.map((r) => (
                    <StaggerItem key={r.id}>
                      <Link
                        href={`/ratings?${r.course_id ? `course=${r.course_id}&` : ""}focus=${r.id}`}
                        className="-mx-2 flex items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-accent/40"
                      >
                        <span className={cn("w-10 shrink-0 text-[13px] font-semibold", r.rating < GOOD && "text-destructive")} data-numeric>
                          {r.rating.toFixed(2)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">{r.topic || r.session_kind}</span>
                          <span className="text-muted-foreground block truncate text-xs">
                            {r.course_name ?? r.course_label}
                            {r.instructor ? ` · ${r.instructor}` : ""} · {prettyDate(r.class_date)}
                          </span>
                        </span>
                        <PriorityChip
                          band={r.health_band}
                          className={r.health_band === "urgent" ? "halo-urgent rounded-md" : undefined}
                        />
                      </Link>
                    </StaggerItem>
                  ))}
                </Stagger>
              </div>
            )}
          </Panel>
        </Reveal>

        <Reveal className="col-span-12 xl:col-span-7" delay={0.05}>
          <Panel
            title="Ratings pulse — by course"
            icon={TrendingDown}
            description={`Classes rated below ${GOOD} in the last 30 days, the share of each room that would have the instructor back, and what is urgent right now.`}
            action={
              <Button asChild variant="ghost" size="sm">
                <Link href="/ratings">
                  Open queue <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              </Button>
            }
          >
            {pulseCourses.length === 0 ? (
              <div className="text-muted-foreground flex flex-col items-center gap-2 py-8 text-center text-sm">
                <Activity className="size-5" aria-hidden />
                No ratings synced in the last 30 days — run Sync now on the queue page.
              </div>
            ) : (
              <>
                <PulseBars rows={pulseCourses} max={pulseMax} />
                <div className="mt-3 border-t pt-3">
                  <Link href="/ratings" className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs">
                    <span>
                      <span className="text-foreground font-semibold" data-numeric>{pulse.bad}</span> below {GOOD}
                      {pulse.underBar > 0 && (
                        <>
                          {" "}· <span className="text-foreground font-semibold" data-numeric>{pulse.underBar}</span> under {APPROVAL_BAR}%
                        </>
                      )}{" "}
                      across {pulse.n} rated {plural(pulse.n, "class", "classes")} in 30 days
                    </span>
                    <ArrowRight className="size-3.5 shrink-0" aria-hidden />
                  </Link>
                </div>
              </>
            )}
          </Panel>
        </Reveal>

        {/* ── spend · activity ────────────────────────────────────────────── */}
        <Reveal className="col-span-12 xl:col-span-5">
          <Panel title="AI spending" icon={CircleDollarSign} description="Exact cost, tracked per analysis.">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <div className="text-xl font-semibold tracking-tight">
                  <CountUp value={thisMonth.cost} decimals={2} prefix="$" />
                </div>
                <div className="text-muted-foreground text-[11px]">
                  this month
                  {lastMonth && (
                    <>
                      {" "}·{" "}
                      <span className={cn(thisMonth.cost > lastMonth.cost ? "text-foreground" : "text-success")} data-numeric>
                        {thisMonth.cost > lastMonth.cost ? "+" : "−"}${Math.abs(thisMonth.cost - lastMonth.cost).toFixed(2)}
                      </span>{" "}
                      vs {prettyMonth(prevMonthKey)}
                    </>
                  )}
                </div>
              </div>
              <div>
                <div className="text-xl font-semibold tracking-tight">
                  <CountUp value={totalCost} decimals={2} prefix="$" />
                </div>
                <div className="text-muted-foreground text-[11px]">all time · {analyzed.length} {plural(analyzed.length, "analysis", "analyses")}</div>
              </div>
              <div>
                <div className="text-xl font-semibold tracking-tight">
                  <CountUp value={avgCost} decimals={2} prefix="$" />
                </div>
                <div className="text-muted-foreground text-[11px]">avg / class</div>
              </div>
            </div>
            {ringMonths.length > 0 && (
              <div className="mt-5 border-t pt-4">
                <div className="text-muted-foreground mb-3 text-[11px] font-medium tracking-wide uppercase">
                  By month · ring = share of the busiest month
                </div>
                <SpendRings months={ringMonths} />
              </div>
            )}
            {byCourse.size > 0 && (
              <div className="mt-5 border-t pt-4">
                <div className="text-muted-foreground mb-2 text-[11px] font-medium tracking-wide uppercase">Analyses by course</div>
                <div className="flex flex-wrap gap-1.5">
                  {[...byCourse.entries()]
                    .sort((a, b) => b[1] - a[1])
                    .map(([name, n]) => (
                      <Badge key={name} variant="secondary">
                        {name} · <span data-numeric>{n}</span>
                      </Badge>
                    ))}
                </div>
              </div>
            )}
          </Panel>
        </Reveal>

        <Reveal className="col-span-12 xl:col-span-7" delay={0.05}>
          <Panel
            title="Recent activity"
            icon={Activity}
            description="The latest analyses, approvals and sends."
            action={
              <Button asChild variant="ghost" size="sm">
                <Link href="/feedback">
                  View all <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              </Button>
            }
          >
            {recent.length === 0 ? (
              <div className="text-muted-foreground flex flex-col items-center gap-3 py-8 text-center text-sm">
                <MessageSquareText className="size-5" aria-hidden />
                No analyses yet.
                {staff && (
                  <Button asChild size="sm">
                    <Link href="/feedback/new">Run your first analysis</Link>
                  </Button>
                )}
              </div>
            ) : (
              <Stagger className="relative" step={0.05}>
                <div aria-hidden className="bg-border absolute top-4 bottom-4 left-4 w-px -translate-x-px" />
                {recent.map((ev) => {
                  const meta = EVENT[ev.kind];
                  const Icon = meta.icon;
                  const rc = analysisOf(ev.c)?.reclass;
                  const cost = Number(analysisOf(ev.c)?.cost_usd ?? 0);
                  return (
                    <StaggerItem key={ev.key}>
                      <Link
                        href={`/feedback/${ev.c.id}`}
                        className="group relative -mr-2 flex items-start gap-3 rounded-lg py-2 pr-2 transition-colors hover:bg-accent/40"
                      >
                        <span
                          className="ring-card relative z-10 mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ring-4"
                          style={{ background: `color-mix(in oklch, ${meta.token} 12%, var(--card))`, color: meta.token }}
                        >
                          <Icon className={cn("size-3.5", ev.kind === "analyzing" && "animate-spin")} aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2">
                            <span className="truncate text-[13px] font-medium">{ev.c.topic}</span>
                            {ev.kind === "analysis" && rc && (
                              <Badge variant={rc === "yes" ? "destructive" : rc === "maybe" ? "warning" : "secondary"} className="uppercase">
                                {rc}
                              </Badge>
                            )}
                          </span>
                          <span className="text-muted-foreground block truncate text-xs">
                            {meta.label} · {ev.c.courses?.name ?? "—"} · {ev.c.instructors?.name ?? "—"}
                            {ev.kind === "analysis" && cost > 0 && (
                              <>
                                {" "}· <span className="text-foreground/80 font-medium" data-numeric>${cost.toFixed(2)}</span>
                              </>
                            )}
                          </span>
                        </span>
                        <span className="text-muted-foreground shrink-0 pt-0.5 text-[11px]" data-numeric>
                          {ago(ev.at)}
                        </span>
                      </Link>
                    </StaggerItem>
                  );
                })}
              </Stagger>
            )}
          </Panel>
        </Reveal>
      </div>
    </div>
  );
}
