import Link from "next/link";
import { BookOpen, ChevronRight, Star, TrendingDown, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { FilterBar, rangeToDates, type RangePreset } from "@/components/filter-bar";
import { StatTile } from "@/components/ui/stat-tile";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { StackedBars } from "@/components/charts/stacked-bars";
import { Sparkline } from "@/components/charts/sparkline";
import { fetchRatings, byCourse, byMonth, summarize } from "@/lib/ratings";
import { GOOD } from "@/lib/decision";
import { fmtMonth } from "@/components/charts/chart-kit";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";

export const metadata = { title: "Course Analytics" };

const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);
const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));

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

  const courses = byCourse(rows);
  const sort = sp.sort ?? "bad";
  courses.sort((a, b) =>
    sort === "name" ? a.name.localeCompare(b.name)
    : sort === "classes" ? b.n - a.n
    : sort === "rating" ? (a.avgRating ?? 9) - (b.avgRating ?? 9)
    : sort === "participation" ? (a.avgParticipation ?? 0) - (b.avgParticipation ?? 0)
    : b.bad - a.bad,
  );
  // per-course monthly avg-rating sparkline over the SAME month buckets
  const sparkFor = (courseKey: string) => {
    const c = courses.find((x) => x.key === courseKey);
    if (!c) return [];
    const m = new Map(byMonth(c.rows).map((x) => [x.month, x.avgRating]));
    return months.map((x) => m.get(x.month)).filter((v): v is number => v != null);
  };

  const delta =
    total.avgRating != null && prev.avgRating != null
      ? total.avgRating - prev.avgRating
      : null;

  const sortHref = (key: string) => {
    const p = new URLSearchParams();
    p.set("range", range);
    if (range === "custom") { p.set("from", from); p.set("to", to); }
    if (sp.course) p.set("course", sp.course);
    p.set("sort", key);
    return `/course-analytics?${p}`;
  };

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Course Analytics"
        description="Every course's ratings from the live sheet — synced automatically, judged by the team rule."
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
          />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-stagger>
            <StatTile label="Classes rated" value={total.n} icon={BookOpen} note={`${from} → ${to}`} />
            <StatTile
              label="Average rating"
              value={fmtAvg(total.avgRating)}
              icon={Star}
              delta={
                delta == null
                  ? undefined
                  : { text: `${delta >= 0 ? "+" : ""}${delta.toFixed(2)} vs previous ${spanDays}d`, good: delta >= 0 }
              }
            />
            <StatTile
              label={`Below ${GOOD}`}
              value={total.bad}
              icon={TrendingDown}
              tone={total.bad > 0 ? "destructive" : "success"}
              note={total.badShare != null ? `${Math.round(total.badShare * 100)}% of classes` : undefined}
            />
            <StatTile
              label="Avg participation"
              value={fmtPct(total.avgParticipation)}
              icon={Users}
              note="share of attendees who rated"
            />
          </div>

          <div className="bg-card shadow-soft mt-4 overflow-hidden rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead><Link href={sortHref("name")} className="hover:text-foreground">Course</Link></TableHead>
                  <TableHead className="text-right"><Link href={sortHref("classes")} className="hover:text-foreground">Classes</Link></TableHead>
                  <TableHead className="text-right"><Link href={sortHref("rating")} className="hover:text-foreground">Avg rating</Link></TableHead>
                  <TableHead className="text-right"><Link href={sortHref("bad")} className="hover:text-foreground">Below {GOOD}</Link></TableHead>
                  <TableHead className="text-right"><Link href={sortHref("participation")} className="hover:text-foreground">Participation</Link></TableHead>
                  <TableHead>Trend</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {courses.map((c) => (
                  <TableRow key={c.key}>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableNum>{c.n}</TableNum>
                    <TableNum className={c.avgRating != null && c.avgRating < GOOD ? "text-destructive font-semibold" : ""}>
                      {fmtAvg(c.avgRating)}
                    </TableNum>
                    <TableNum>
                      {c.bad > 0 ? (
                        <span className="text-destructive font-semibold">
                          {c.bad}
                          <span className="text-muted-foreground font-normal"> ({Math.round((c.badShare ?? 0) * 100)}%)</span>
                        </span>
                      ) : (
                        "0"
                      )}
                    </TableNum>
                    <TableNum>{fmtPct(c.avgParticipation)}</TableNum>
                    <TableCell><Sparkline values={sparkFor(c.key)} /></TableCell>
                    <TableCell className="w-8">
                      {c.courseId && (
                        <Link
                          href={`/course-analytics?range=${range}&course=${c.courseId}`}
                          aria-label={`Filter to ${c.name}`}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <ChevronRight className="size-4" />
                        </Link>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <ChartCard
            className="mt-4"
            title={`Fine vs below ${GOOD}, per month`}
            subtitle="Counts of rated classes; the label is the share below the line"
            legend={[
              { label: `Rated ${GOOD}+`, color: "var(--success)" },
              { label: `Below ${GOOD}`, color: "var(--destructive)" },
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
              segments={[
                { name: `Rated ${GOOD}+`, color: "var(--success)" },
                { name: `Below ${GOOD}`, color: "var(--destructive)" },
              ]}
              values={months.map((m) => [m.n - m.bad, m.bad])}
              topLabels={months.map((m) =>
                m.badShare != null ? `${Math.round((m.badShare ?? 0) * 100)}%` : null,
              )}
            />
          </ChartCard>
        </>
      )}
    </div>
  );
}
