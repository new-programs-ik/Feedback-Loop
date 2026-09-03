import Link from "next/link";
import { ArrowRight, BookOpen, ChevronRight, Download, Star, TrendingDown, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { FilterBar, rangeToDates, type RangePreset } from "@/components/filter-bar";
import { StatTile } from "@/components/ui/stat-tile";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import {
  BandDot, Meter, SortHead, Table, TableActions, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow,
} from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { StackedBars } from "@/components/charts/stacked-bars";
import { Sparkline } from "@/components/charts/sparkline";
import { CountUp } from "@/components/motion/count-up";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { approvalTone } from "@/components/priority-chip";
import { fetchRatings, byCourse, byMonth, summarize } from "@/lib/ratings";
import { APPROVAL_BAR, GOOD } from "@/lib/decision";
import { fmtMonth } from "@/components/charts/chart-kit";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";

export const metadata = { title: "Course Analytics" };

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));

/** Which way each column sorts when it is the active key (the URL carries only the key). */
const SORT_DIR: Record<string, "asc" | "desc"> = {
  name: "asc", classes: "desc", rating: "asc", approval: "asc", bad: "desc", participation: "asc",
};

export default async function CourseAnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string; course?: string; sort?: string }>;
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

  // Delta baseline: the equal-length period immediately before.
  const spanDays = Math.max(1, Math.round((+new Date(to) - +new Date(from)) / 86400000));
  const prevFrom = new Date(+new Date(from) - spanDays * 86400000).toISOString().slice(0, 10);
  const prevRows = await fetchRatings({ from: prevFrom, to: from, courseId: sp.course || undefined });

  const total = summarize(rows);
  const prev = summarize(prevRows);
  const months = byMonth(rows);
  const monthLabels = months.map((m) => fmtMonth(m.month));
  const ratingSpark = months.map((m) => m.avgRating).filter((v): v is number => v != null);
  const badShareSpark = months
    .map((m) => (m.badShare != null ? m.badShare * 100 : null))
    .filter((v): v is number => v != null);

  const courses = byCourse(rows);
  const sort = sp.sort && sp.sort in SORT_DIR ? sp.sort : "bad";
  courses.sort((a, b) =>
    sort === "name" ? a.name.localeCompare(b.name)
    : sort === "classes" ? b.n - a.n
    : sort === "rating" ? (a.avgRating ?? 9) - (b.avgRating ?? 9)
    : sort === "participation" ? (a.avgParticipation ?? 0) - (b.avgParticipation ?? 0)
    : sort === "approval" ? (a.approval ?? 101) - (b.approval ?? 101)
    : b.bad - a.bad,
  );
  const sparkFor = (courseKey: string) => {
    const c = courses.find((x) => x.key === courseKey);
    if (!c) return [];
    const m = new Map(byMonth(c.rows).map((x) => [x.month, x.avgRating]));
    return months.map((x) => m.get(x.month)).filter((v): v is number => v != null);
  };

  const ratingDelta =
    total.avgRating != null && prev.avgRating != null ? total.avgRating - prev.avgRating : null;
  const badDelta =
    total.badShare != null && prev.badShare != null ? (total.badShare - prev.badShare) * 100 : null;
  const partDelta =
    total.avgParticipation != null && prev.avgParticipation != null
      ? total.avgParticipation - prev.avgParticipation
      : null;

  const qs = () => {
    const p = new URLSearchParams();
    p.set("range", range);
    if (range === "custom") { p.set("from", from); p.set("to", to); }
    if (sp.course) p.set("course", sp.course);
    return p;
  };
  const sortHref = (key: string) => {
    const p = qs();
    p.set("sort", key);
    return `/course-analytics?${p}`;
  };
  /** The same window, scoped to one course, on the Reports page. */
  const reportHref = (courseId: string) =>
    `/reports?${new URLSearchParams({ range: "custom", from, to, course: courseId })}`;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Course Analytics"
        description={`Every course's ratings, judged by the team rule · ${from} → ${to}`}
        actions={
          <Button asChild variant="outline" size="sm">
            <a href={`/course-analytics/export?${qs()}`}>
              <Download className="size-3.5" aria-hidden /> Export CSV
            </a>
          </Button>
        }
      />
      <FilterBar
        basePath="/course-analytics"
        range={range}
        from={from}
        to={to}
        courseId={sp.course}
        courses={coursesRes.data ?? []}
      />

      {rows.length === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          <EmptyState
            icon={BookOpen}
            title="No rated classes in this range"
            description="Data arrives from the ratings sheet sync — pick a wider range, or run Sync now on the Needs-analysis page."
            action={
              <Button asChild variant="outline" size="sm">
                <Link href="/course-analytics?range=90d">Show the last 90 days</Link>
              </Button>
            }
          />
        </div>
      ) : (
        <>
          <Stagger className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" step={0.06}>
            <StaggerItem>
              <StatTile
                label="Classes rated"
                count={{ value: total.n }}
                icon={BookOpen}
                note={`${Math.round(total.n / (spanDays / 7))} per week`}
              />
            </StaggerItem>
            <StaggerItem>
              <StatTile
                label="Average rating"
                count={total.avgRating == null ? undefined : { value: total.avgRating, decimals: 2 }}
                value={total.avgRating == null ? "—" : undefined}
                icon={Star}
                sparkline={<Sparkline values={ratingSpark} />}
                delta={
                  ratingDelta == null
                    ? undefined
                    : {
                        text: Math.abs(ratingDelta).toFixed(2),
                        suffix: `vs prior ${spanDays}d`,
                        good: ratingDelta >= 0,
                        direction: ratingDelta >= 0 ? "up" : "down",
                      }
                }
              />
            </StaggerItem>
            <StaggerItem>
              <StatTile
                label={`Below ${GOOD}`}
                value={
                  <>
                    <CountUp value={total.bad} />
                    <span className="text-muted-foreground text-[15px] font-medium">
                      {" "}· {Math.round((total.badShare ?? 0) * 100)}%
                    </span>
                  </>
                }
                icon={TrendingDown}
                sparkline={<Sparkline values={badShareSpark} accent="var(--viz-bad)" />}
                delta={
                  badDelta == null
                    ? undefined
                    : {
                        text: `${Math.abs(badDelta).toFixed(1)} pts`,
                        suffix: `share vs prior ${spanDays}d`,
                        good: badDelta <= 0,
                        direction: badDelta >= 0 ? "up" : "down",
                      }
                }
              />
            </StaggerItem>
            <StaggerItem>
              <StatTile
                label="Avg participation"
                count={total.avgParticipation == null ? undefined : { value: Math.round(total.avgParticipation), suffix: "%" }}
                value={total.avgParticipation == null ? "—" : undefined}
                icon={Users}
                delta={
                  partDelta == null
                    ? undefined
                    : {
                        text: `${Math.abs(partDelta).toFixed(0)} pts`,
                        suffix: "share of attendees who rated",
                        good: partDelta >= 0,
                        direction: partDelta >= 0 ? "up" : "down",
                      }
                }
              />
            </StaggerItem>
          </Stagger>

          <Reveal className="bg-card shadow-soft mt-4 overflow-hidden rounded-xl border" delay={0.1}>
            <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3.5 pb-2.5">
              <h3 className="text-[13px] font-semibold tracking-[-0.01em]">By course</h3>
              <span className="text-muted-foreground text-[11px]">click a column to sort · a row opens its report</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <SortHead href={sortHref("name")} active={sort === "name"} dir={SORT_DIR.name}>Course</SortHead>
                  <SortHead href={sortHref("classes")} active={sort === "classes"} dir={SORT_DIR.classes} align="right">Classes</SortHead>
                  <SortHead href={sortHref("rating")} active={sort === "rating"} dir={SORT_DIR.rating} align="right">Avg rating</SortHead>
                  <SortHead href={sortHref("approval")} active={sort === "approval"} dir={SORT_DIR.approval} align="right">Approval</SortHead>
                  <SortHead href={sortHref("bad")} active={sort === "bad"} dir={SORT_DIR.bad} align="right">Below {GOOD}</SortHead>
                  <SortHead href={sortHref("participation")} active={sort === "participation"} dir={SORT_DIR.participation}>Participation</SortHead>
                  <TableHead>90-day trend</TableHead>
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {courses.map((c) => {
                  const share = Math.round((c.badShare ?? 0) * 100);
                  return (
                    <TableRow key={c.key} className="hover:bg-accent/40">
                      <TableCell className="font-medium">{c.name}</TableCell>
                      <TableNum className="text-muted-foreground">{c.n}</TableNum>
                      <TableNum>
                        <BandDot tone={c.avgRating != null && c.avgRating < GOOD ? "bad" : c.avgRating != null && c.avgRating < 4.7 ? "warn" : "good"} />
                        {fmtAvg(c.avgRating)}
                      </TableNum>
                      <TableNum className={c.approval != null && c.approval < APPROVAL_BAR ? "text-destructive font-semibold" : ""}>
                        {c.approval != null ? (
                          <><BandDot tone={approvalTone(c.approval)} />{Math.round(c.approval)}%</>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableNum>
                      <TableNum>
                        {c.bad > 0 ? (
                          <span className="bg-destructive/8 text-destructive inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold">
                            {c.bad}
                            <span className="font-medium opacity-70">· {share}%</span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">0</span>
                        )}
                      </TableNum>
                      <TableCell>
                        {c.avgParticipation != null ? <Meter value={c.avgParticipation} /> : "—"}
                      </TableCell>
                      <TableCell><Sparkline values={sparkFor(c.key)} width={84} /></TableCell>
                      <TableActions>
                        {c.courseId && (
                          <>
                            {/* Reveals on row hover (always present for keyboard + touch). */}
                            <Link
                              href={reportHref(c.courseId)}
                              className="text-primary inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 focus-visible:opacity-100 hover:underline [@media(hover:none)]:opacity-100"
                            >
                              View report <ArrowRight className="size-3" aria-hidden />
                            </Link>
                            <Link
                              href={`/course-analytics?range=${range}&course=${c.courseId}`}
                              aria-label={`Filter to ${c.name}`}
                              title={`Filter this page to ${c.name}`}
                              className="text-muted-foreground/60 hover:text-foreground hover:bg-accent inline-flex size-7 items-center justify-center rounded-md transition-colors"
                            >
                              <ChevronRight className="size-4" />
                            </Link>
                          </>
                        )}
                      </TableActions>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Reveal>

          <Reveal className="mt-4" delay={0.05}>
            <ChartCard
              title={`Fine vs below ${GOOD}, per month`}
              subtitle="Counts of rated classes · the label is the share below the line"
              legend={[
                { label: `Rated ${GOOD}+`, color: "var(--viz-good)" },
                { label: `Below ${GOOD}`, color: "var(--viz-bad)" },
              ]}
              table={{
                headers: ["Month", `Rated ${GOOD}+`, `Below ${GOOD}`, "Share below"],
                rows: months.map((m) => [
                  fmtMonth(m.month),
                  m.n - m.bad,
                  m.bad,
                  m.badShare != null ? `${Math.round(m.badShare * 100)}%` : "—",
                ]),
              }}
            >
              <StackedBars
                labels={monthLabels}
                height={190}
                segments={[
                  { name: `Rated ${GOOD}+`, color: "var(--viz-good)" },
                  { name: `Below ${GOOD}`, color: "var(--viz-bad)" },
                ]}
                values={months.map((m) => [m.n - m.bad, m.bad])}
                topLabels={months.map((m) =>
                  m.badShare != null ? `${Math.round((m.badShare ?? 0) * 100)}%` : null,
                )}
              />
            </ChartCard>
          </Reveal>
        </>
      )}
    </div>
  );
}
