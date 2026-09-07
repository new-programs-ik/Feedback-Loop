import type { Metadata } from "next";
import Link from "next/link";
import { Download } from "lucide-react";
import { hrefIn, listCourses } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { PrintButton } from "@/components/ui/print-button";
import { ShareButton } from "@/components/analytics/share-button";
import { RankedMovers } from "@/components/charts/ranked-movers";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { CourseSquare, DataTable, Delta, Empty, Section } from "@/components/analytics/ui";
import { WorstClasses } from "@/components/analytics/worst-classes";
import { HeadlineTiles, LoopFunnel, PeriodTabs, PrintStyles } from "@/components/analytics/report-blocks";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import {
  byCourse,
  fetchScored,
  fmtPct,
  instructorName,
  loadLoop,
  loopFunnel,
  movers,
  outcomesFor,
  prettyDate,
  prettyDateYear,
  previousWindow,
  queueCounts,
  reportPeriod,
  scoreSummary,
  topicKey,
  type SearchParams,
} from "@/lib/analytics";
import { instructorKey, latestRatedDate } from "@/lib/ratings";

export const metadata: Metadata = { title: "Reports" };

export default async function TeamReportsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const win = reportPeriod(sp, await latestRatedDate(null));
  const { period, from, to, label } = win;
  const prev = previousWindow(from, to);
  const [courses, rows, prevRows, loop] = await Promise.all([listCourses(), fetchScored({ from, to }), fetchScored({ from: prev.from, to: prev.to }), loadLoop(null)]);
  const cur = scoreSummary(rows);
  const before = scoreSummary(prevRows);
  const queue = queueCounts(rows);
  const byId = new Map(courses.map((c) => [c.id, c]));
  const prevByCourse = new Map(byCourse(prevRows).map((c) => [c.key, c]));
  const courseRows = byCourse(rows).sort((a, b) => (b.badShare ?? 0) - (a.badShare ?? 0) || b.counts.bad - a.counts.bad);
  const minClasses = period === "week" ? 2 : 3;
  const instructorMovers = movers(prevRows, rows, instructorKey, instructorName, minClasses, (key) => `/team/instructors/${encodeURIComponent(key)}`);
  const moduleMovers = movers(prevRows, rows, (r) => `${r.course_id ?? r.course_label}|${topicKey(r)}`, (r) => r.topic.trim(), minClasses, (_, r) => (r.course_slug ? hrefIn(r.course_slug, `/modules/${encodeURIComponent(topicKey(r))}`) : undefined));
  const funnel = loopFunnel(rows, loop);
  const outcomes = outcomesFor(rows, loop);
  const qs = new URLSearchParams({ period });
  if (period === "custom") {
    qs.set("from", from);
    qs.set("to", to);
  } else qs.set("at", from);

  return (
    <div className="report-page space-y-4">
      <PrintStyles />
      <PageHeader
        title={`All courses — ${label.toLowerCase()} report`}
        description={`${prettyDateYear(from)} – ${prettyDateYear(to)} · compared with ${prettyDate(prev.from)} – ${prettyDate(prev.to)} · generated live from the synced ratings`}
        actions={
          <>
            <Button asChild variant="outline" size="sm" data-print-hide>
              <a href={`/team/reports/export?${qs}`}>
                <Download aria-hidden /> CSV
              </a>
            </Button>
            <ShareButton courseId={null} period={{ kind: period, from, to, label }} />
            <PrintButton />
          </>
        }
      />
      <PeriodTabs basePath="/team/reports" period={period} from={from} to={to} prev={win.prev} next={win.next} stale={win.stale} />

      {rows.length === 0 ? (
        <Section>
          <Empty>No rated classes in this period.</Empty>
        </Section>
      ) : (
        <>
          <HeadlineTiles cur={cur} prev={before} queue={queue} />

          <Section title="By course" subtitle="Worst band share first · Δ vs the previous period · a row opens the course report" flush>
            <DataTable>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Course</TableHead>
                  <TableHead className="text-right">Classes</TableHead>
                  <TableHead>Avg score</TableHead>
                  <TableHead>Band mix</TableHead>
                  <TableHead className="text-right">Δ</TableHead>
                  <TableHead className="text-right">Approval</TableHead>
                  <TableHead className="text-right">Reach</TableHead>
                  <TableHead className="text-right">Bad</TableHead>
                  <TableHead className="text-right">Average</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {courseRows.map((c) => {
                  const info = c.courseId ? byId.get(c.courseId) : undefined;
                  const p = prevByCourse.get(c.key);
                  return (
                    <TableRow key={c.key} className="relative">
                      <TableCell className="max-w-64">
                        <span className="flex items-center gap-2">
                          {info && <CourseSquare color={info.color} initials={info.initials} size={22} />}
                          {c.slug ? (
                            <Link href={`${hrefIn(c.slug, "/reports")}?${qs}`} className="hover:text-primary truncate font-medium after:absolute after:inset-0">
                              {c.name}
                            </Link>
                          ) : (
                            <span className="truncate font-medium">{c.name}</span>
                          )}
                        </span>
                      </TableCell>
                      <TableNum className="text-muted-foreground">{c.n}</TableNum>
                      <TableCell>
                        <AvgScorePill score={c.avgScore} />
                      </TableCell>
                      <TableCell>
                        <BandStripOf counts={c.counts} className="w-20" />
                      </TableCell>
                      <TableNum>
                        <Delta value={c.avgScore == null || p?.avgScore == null ? null : c.avgScore - p.avgScore} />
                      </TableNum>
                      <TableNum className={c.approval != null && c.approval < 80 ? "text-destructive font-semibold" : ""}>{fmtPct(c.approval)}</TableNum>
                      <TableNum className="text-muted-foreground">{fmtPct(c.reach)}</TableNum>
                      <TableNum className={c.counts.bad ? "text-destructive font-semibold" : "text-muted-foreground"}>{c.counts.bad}</TableNum>
                      <TableNum className="text-muted-foreground">{c.counts.average}</TableNum>
                    </TableRow>
                  );
                })}
              </TableBody>
            </DataTable>
          </Section>

          <div className="report-section grid gap-4 xl:grid-cols-2">
            <Section title="Instructors that moved" subtitle={`At least ${minClasses} classes in both periods`}>
              <RankedMovers items={instructorMovers} limit={5} />
            </Section>
            <Section title="Modules that moved" subtitle={`Per course · at least ${minClasses} classes in both periods`}>
              <RankedMovers items={moduleMovers} limit={5} />
            </Section>
          </div>

          <Section className="report-break" title="Worst classes" subtitle="Across every course · why, and what happened to each" flush>
            <WorstClasses rows={rows} limit={12} showCourse outcomes={outcomes} />
          </Section>

          <Section title="Loop outcomes" subtitle="Flagged → confirmed → analysed → approved → sent, with the median days per step">
            <LoopFunnel f={funnel} feedbackHref="/team/queue" />
          </Section>
        </>
      )}
    </div>
  );
}
