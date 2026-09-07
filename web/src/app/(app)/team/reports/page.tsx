import type { Metadata } from "next";
import { Download } from "lucide-react";
import { hrefIn, listCourses } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { PrintButton } from "@/components/ui/print-button";
import { ShareButton } from "@/components/analytics/share-button";
import { RankedMovers } from "@/components/charts/ranked-movers";
import { Empty, Section } from "@/components/analytics/ui";
import { CoursesTable, WorstClassesTable } from "@/components/analytics/sortable-tables";
import { avgAttended, classRow, courseRow, worstOf } from "@/components/analytics/table-rows";
import { HeadlineTiles, LoopFunnel, PeriodTabs, PrintStyles } from "@/components/analytics/report-blocks";
import {
  byCourse,
  classReason,
  drawerHref,
  fetchScored,
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
  const attended = avgAttended(rows);
  const queue = queueCounts(rows);
  const qs = new URLSearchParams({ period });
  if (period === "custom") {
    qs.set("from", from);
    qs.set("to", to);
  } else qs.set("at", from);

  // ── by course: aggregate here, hand the client table slim rows (it sorts on the spot) ──
  const byId = new Map(courses.map((c) => [c.id, c]));
  const prevByCourse = new Map(byCourse(prevRows).map((c) => [c.key, c]));
  const courseRows = byCourse(rows)
    .sort((a, b) => (b.badShare ?? 0) - (a.badShare ?? 0) || b.counts.bad - a.counts.bad)
    .map((c) => {
      const info = c.courseId ? byId.get(c.courseId) : undefined;
      return courseRow(c, {
        href: c.slug ? `${hrefIn(c.slug, "/reports")}?${qs}` : null,
        previous: prevByCourse.get(c.key)?.avgScore,
        color: info?.color,
        initials: info?.initials,
      });
    });
  const minClasses = period === "week" ? 2 : 3;
  const instructorMovers = movers(prevRows, rows, instructorKey, instructorName, minClasses, (key) => `/team/instructors/${encodeURIComponent(key)}`);
  const moduleMovers = movers(prevRows, rows, (r) => `${r.course_id ?? r.course_label}|${topicKey(r)}`, (r) => r.topic.trim(), minClasses, (_, r) => (r.course_slug ? hrefIn(r.course_slug, `/modules/${encodeURIComponent(topicKey(r))}`) : undefined));
  const funnel = loopFunnel(rows, loop);
  const outcomes = outcomesFor(rows, loop);
  const worst = worstOf(rows, 12).map((r) => classRow(r, { href: drawerHref(r), reason: classReason(r), instructor: instructorName(r), outcome: outcomes.get(r.id) ?? null }));

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
          <HeadlineTiles cur={cur} prev={before} queue={queue} attended={attended} />

          <Section title="By course" subtitle="Worst Bad share first · Δ vs the previous period · a row opens the course report" flush>
            <CoursesTable rows={courseRows} maxHeight="none" />
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
            <WorstClassesTable rows={worst} showCourse withOutcome maxHeight="none" />
          </Section>

          <Section title="Loop outcomes" subtitle="Flagged → confirmed → analysed → approved → sent, with the median days per step">
            <LoopFunnel f={funnel} feedbackHref="/team/queue" />
          </Section>
        </>
      )}
    </div>
  );
}
