import Link from "next/link";
import { ArrowLeft, GraduationCap, Star, ThumbsUp, TrendingDown, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { FilterBar, rangeToDates, type RangePreset } from "@/components/filter-bar";
import { StatTile } from "@/components/ui/stat-tile";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import {
  BandDot, Meter, Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow,
} from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { Sparkline } from "@/components/charts/sparkline";
import { approvalTone } from "@/components/priority-chip";
import {
  fetchRatings, byInstructor, byMonth, byCourse, smeTopics, summarize, worstClasses,
} from "@/lib/ratings";
import { APPROVAL_BAR, GOOD, voteLabel } from "@/lib/decision";
import { fmtMonth } from "@/components/charts/chart-kit";
import { SmeGalaxy } from "@/components/three/sme-galaxy";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";

export const metadata = { title: "Instructor Analytics" };

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));
const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);
const pretty = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

export default async function InstructorAnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string; sme?: string; sort?: string; course?: string }>;
}) {
  await requireUser();
  const sp = await searchParams;
  const range = (["7d", "30d", "90d", "month", "custom"].includes(sp.range ?? "") ? sp.range : "90d") as RangePreset;
  const { from, to } = rangeToDates(range, sp.from, sp.to);

  const supabase = await createClient();
  const [rows, coursesRes] = await Promise.all([
    fetchRatings({ from, to, courseId: sp.course || undefined }),
    supabase.from("courses").select("id, name").order("name"),
  ]);
  const courseList = coursesRes.data ?? [];
  const courseName = sp.course
    ? (courseList.find((c) => c.id === sp.course)?.name ?? "the selected course")
    : null;

  // Every href on this page carries the current scope (range, custom dates, course).
  const qs = () => {
    const p = new URLSearchParams();
    p.set("range", range);
    if (range === "custom") { p.set("from", from); p.set("to", to); }
    if (sp.course) p.set("course", sp.course);
    return p;
  };

  // ── drill-in: one SME ───────────────────────────────────────────────────────
  if (sp.sme) {
    const own = rows.filter((r) => r.instructor === sp.sme);
    const t = summarize(own);
    const months = byMonth(own);
    const topics = smeTopics(rows, sp.sme);
    const strong = topics.filter((x) => (x.avgRating ?? 0) >= GOOD);
    const weak = [...topics].reverse().filter((x) => (x.avgRating ?? 5) < GOOD);
    const courses = byCourse(own);
    const worst = worstClasses(own, 6);
    const politeRating = t.avgRating != null && t.avgRating >= GOOD && t.approval != null && t.approval < APPROVAL_BAR;
    const hardClass = t.avgRating != null && t.avgRating < GOOD && t.approval != null && t.approval >= APPROVAL_BAR;

    return (
      <div className="animate-in-up">
        <PageHeader
          title={
            <span className="flex items-center gap-2">
              <Button asChild variant="ghost" size="icon" className="-ml-2">
                <Link href={`/instructor-analytics?${qs()}`} aria-label="All instructors">
                  <ArrowLeft className="size-4" />
                </Link>
              </Button>
              {sp.sme}
            </span>
          }
          description={
            courseName
              ? `${t.n} rated classes in ${courseName} · ${from} → ${to}`
              : `${t.n} rated classes · ${from} → ${to}`
          }
        />
        {own.length === 0 ? (
          <div className="bg-card shadow-soft rounded-xl border">
            <EmptyState icon={GraduationCap} title="No rated classes for this instructor in the range"
                        description={courseName
                          ? `Nothing in ${courseName} here — widen the date range or clear the course filter to see their history.`
                          : "Widen the date range to see their history."} />
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" data-stagger>
              <StatTile label="Classes rated" value={t.n} icon={GraduationCap} />
              <StatTile label="Average rating" value={fmtAvg(t.avgRating)} icon={Star}
                        sparkline={<Sparkline values={months.map((m) => m.avgRating).filter((v): v is number => v != null)} />} />
              <StatTile label="Would have them back" value={fmtPct(t.approval)} icon={ThumbsUp}
                        tone={t.approval != null && t.approval < APPROVAL_BAR ? "destructive" : "default"}
                        note={t.votes > 0
                          ? `${t.votes.toLocaleString()} votes · ${t.underBar} ${t.underBar === 1 ? "class" : "classes"} under ${APPROVAL_BAR}%`
                          : "no votes recorded"} />
              <StatTile label={`Below ${GOOD}`} value={t.bad} icon={TrendingDown}
                        tone={t.bad > 0 ? "destructive" : "success"}
                        note={t.badShare != null ? `${Math.round(t.badShare * 100)}% of their classes` : undefined} />
              <StatTile label="Avg participation" value={fmtPct(t.avgParticipation)} icon={Users} />
            </div>

            {politeRating && (
              <Callout tone="warn" title="Polite rating — the room rates the class fine but would rather have someone else" className="mt-4">
                Averages <b>{fmtAvg(t.avgRating)}</b> across {t.n} classes, yet only{" "}
                <b>{Math.round(t.approval!)}%</b> of {t.votes.toLocaleString()} votes would have this instructor
                back — under the {APPROVAL_BAR}% bar. The rating rule alone never sees this; the vote is an
                instructor question, and here the room is answering it.
              </Callout>
            )}
            {hardClass && (
              <Callout tone="ok" title="Hard class, good teacher — low ratings the room does not pin on the instructor" className="mt-4">
                Averages <b>{fmtAvg(t.avgRating)}</b> across {t.n} classes, but{" "}
                <b>{Math.round(t.approval!)}%</b> of {t.votes.toLocaleString()} votes would still have this
                instructor back. The rating says something went wrong; the vote says where not to look first —
                the room is not asking for a different instructor, so start with the content and the difficulty.
              </Callout>
            )}

            {months.length >= 2 && (
              <ChartCard className="mt-4" title="Rating trend" subtitle="Monthly average, against the 4.55 line"
                table={{ headers: ["Month", "Avg rating", "Approval", "Classes"], rows: months.map((m) => [fmtMonth(m.month), fmtAvg(m.avgRating), fmtPct(m.approval), m.n]) }}>
                <LineChart
                  labels={months.map((m) => fmtMonth(m.month))}
                  series={[{ name: "Avg rating", values: months.map((m) => m.avgRating) }]}
                  yDomain={[3.8, 5]}
                  threshold={GOOD}
                  thresholdLabel={String(GOOD)}
                  height={200}
                  area
                />
              </ChartCard>
            )}

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
                <div className="px-4 pt-3.5 pb-1">
                  <h3 className="text-[13px] font-semibold">Strong topics</h3>
                  <p className="text-muted-foreground text-xs">Where this SME performs — candidates for more allocation</p>
                </div>
                <Table>
                  <TableBody>
                    {strong.slice(0, 6).map((x) => (
                      <TableRow key={x.topic}>
                        <TableCell className="max-w-64 truncate font-medium">{x.topic}</TableCell>
                        <TableNum><BandDot tone="good" />{fmtAvg(x.avgRating)}</TableNum>
                        <TableNum className="text-muted-foreground">
                          {x.approval != null ? <><BandDot tone={approvalTone(x.approval)} />{Math.round(x.approval)}% back</> : "—"}
                        </TableNum>
                        <TableNum className="text-muted-foreground">{x.n} classes</TableNum>
                      </TableRow>
                    ))}
                    {strong.length === 0 && (
                      <TableRow><TableCell className="text-muted-foreground">Not enough per-topic data yet.</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
              <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
                <div className="px-4 pt-3.5 pb-1">
                  <h3 className="text-[13px] font-semibold">Improvement areas</h3>
                  <p className="text-muted-foreground text-xs">Topics rated below {GOOD} — targeted coaching, not generic feedback</p>
                </div>
                <Table>
                  <TableBody>
                    {weak.slice(0, 6).map((x) => (
                      <TableRow key={x.topic}>
                        <TableCell className="max-w-64 truncate font-medium">{x.topic}</TableCell>
                        <TableNum><BandDot tone="bad" />{fmtAvg(x.avgRating)}</TableNum>
                        <TableNum className="text-muted-foreground">
                          {x.approval != null ? <><BandDot tone={approvalTone(x.approval)} />{Math.round(x.approval)}% back</> : "—"}
                        </TableNum>
                        <TableNum className="text-muted-foreground">{x.n} classes</TableNum>
                      </TableRow>
                    ))}
                    {weak.length === 0 && (
                      <TableRow><TableCell className="text-muted-foreground">No below-{GOOD} topics in this range. 🎉</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
                <div className="px-4 pt-3.5 pb-1"><h3 className="text-[13px] font-semibold">By course</h3></div>
                <Table>
                  <TableBody>
                    {courses.map((c) => (
                      <TableRow key={c.key}>
                        <TableCell className="font-medium">{c.name}</TableCell>
                        <TableNum>{fmtAvg(c.avgRating)}</TableNum>
                        <TableNum className="text-muted-foreground">
                          {c.approval != null ? <><BandDot tone={approvalTone(c.approval)} />{Math.round(c.approval)}% back</> : "—"}
                        </TableNum>
                        <TableNum className="text-muted-foreground">{c.n} classes</TableNum>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
                <div className="px-4 pt-3.5 pb-1"><h3 className="text-[13px] font-semibold">Lowest-rated classes</h3></div>
                <Table>
                  <TableBody>
                    {worst.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="text-destructive font-semibold" data-numeric>{r.rating.toFixed(2)}</TableCell>
                        <TableCell className="max-w-56 truncate">{r.topic || r.session_kind}</TableCell>
                        <TableNum className="text-muted-foreground">{voteLabel(r.yes_votes, r.no_votes) ?? "—"}</TableNum>
                        <TableNum className="text-muted-foreground">{pretty(r.class_date)}</TableNum>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          </>
        )}
      </div>
    );
  }

  // ── index: every SME ────────────────────────────────────────────────────────
  const smes = byInstructor(rows).filter((s) => s.name !== "(unknown)" && s.n >= 3);
  const sort = sp.sort ?? "bad";
  smes.sort((a, b) =>
    sort === "name" ? a.name.localeCompare(b.name)
    : sort === "classes" ? b.n - a.n
    : sort === "rating" ? (a.avgRating ?? 9) - (b.avgRating ?? 9)
    : sort === "approval" ? (a.approval ?? 101) - (b.approval ?? 101)
    : b.bad - a.bad,
  );
  const months = byMonth(rows);
  const sparkFor = (name: string) => {
    const own = rows.filter((r) => r.instructor === name);
    const m = new Map(byMonth(own).map((x) => [x.month, x.avgRating]));
    return months.map((x) => m.get(x.month)).filter((v): v is number => v != null);
  };
  const sortHref = (key: string) => {
    const p = qs();
    p.set("sort", key);
    return `/instructor-analytics?${p}`;
  };
  const smeHref = (name: string) => {
    const p = qs();
    p.set("sme", name);
    return `/instructor-analytics?${p}`;
  };

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Instructor Analytics"
        description={`Every SME with 3+ rated classes · click a row for their per-topic strengths, improvement areas and the room's vote · ${from} → ${to}`}
      />
      <FilterBar
        basePath="/instructor-analytics"
        range={range}
        from={from}
        to={to}
        courseId={sp.course}
        courses={courseList}
        extra={sp.sort ? { sort: sp.sort } : undefined}
      />
      {smes.length > 0 && (
        <SmeGalaxy
          points={smes.map((s) => ({
            name: s.name, n: s.n, avgRating: s.avgRating, approval: s.approval, avgParticipation: s.avgParticipation, bad: s.bad,
          }))}
          query={qs().toString()}
        />
      )}
      {smes.length === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          <EmptyState icon={GraduationCap} title="No instructor data in this range"
                      description={courseName
                        ? `Nothing in ${courseName} here — widen the date range or clear the course filter. SMEs need at least 3 rated classes to appear.`
                        : "Widen the date range — SMEs need at least 3 rated classes to appear."} />
        </div>
      ) : (
        <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead><Link href={sortHref("name")} className="hover:text-foreground">Instructor</Link></TableHead>
                <TableHead className="text-right"><Link href={sortHref("classes")} className="hover:text-foreground">Classes</Link></TableHead>
                <TableHead className="text-right"><Link href={sortHref("rating")} className="hover:text-foreground">Avg rating</Link></TableHead>
                <TableHead className="text-right"><Link href={sortHref("approval")} className="hover:text-foreground">Approval</Link></TableHead>
                <TableHead className="text-right"><Link href={sortHref("bad")} className="hover:text-foreground">Below {GOOD}</Link></TableHead>
                <TableHead>Participation</TableHead>
                <TableHead>Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {smes.map((s) => {
                const share = Math.round((s.badShare ?? 0) * 100);
                return (
                  <TableRow key={s.name} className="relative">
                    <TableCell className="font-medium">
                      <Link href={smeHref(s.name)} className="hover:text-primary after:absolute after:inset-0">
                        {s.name}
                      </Link>
                    </TableCell>
                    <TableNum className="text-muted-foreground">{s.n}</TableNum>
                    <TableNum>
                      <BandDot tone={s.avgRating != null && s.avgRating < GOOD ? "bad" : s.avgRating != null && s.avgRating < 4.7 ? "warn" : "good"} />
                      {fmtAvg(s.avgRating)}
                    </TableNum>
                    <TableNum className={s.approval != null && s.approval < APPROVAL_BAR ? "text-destructive font-semibold" : ""}>
                      {s.approval != null ? <><BandDot tone={approvalTone(s.approval)} />{Math.round(s.approval)}%</> : <span className="text-muted-foreground">—</span>}
                    </TableNum>
                    <TableNum>
                      {s.bad > 0 ? (
                        <span className="bg-destructive/8 text-destructive inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold">
                          {s.bad}<span className="font-medium opacity-70">· {share}%</span>
                        </span>
                      ) : (
                        <span className="text-muted-foreground">0</span>
                      )}
                    </TableNum>
                    <TableCell>{s.avgParticipation != null ? <Meter value={s.avgParticipation} /> : "—"}</TableCell>
                    <TableCell><Sparkline values={sparkFor(s.name)} width={84} /></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
