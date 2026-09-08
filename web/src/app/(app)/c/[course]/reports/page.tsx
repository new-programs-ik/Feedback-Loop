import type { Metadata } from "next";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { PrintButton } from "@/components/ui/print-button";
import { ShareButton } from "@/components/analytics/share-button";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { RankedMovers } from "@/components/charts/ranked-movers";
import { BAND_META } from "@/lib/sentiment";
import { Download } from "lucide-react";
import { Empty, Section } from "@/components/analytics/ui";
import { Leaderboard } from "@/components/analytics/leaderboard";
import { CohortsTable, ModulesTable, WorstClassesTable } from "@/components/analytics/sortable-tables";
import { avgAttended, classRow, cohortRow, moduleRow, worstOf } from "@/components/analytics/table-rows";
import { HeadlineTiles, LoopFunnel, PeriodTabs, PrintStyles } from "@/components/analytics/report-blocks";
import {
  byCohort,
  byDay,
  byInstructor,
  byTopic,
  byWeek,
  classReason,
  daysBetween,
  drawerHref,
  fetchScored,
  fmtScore,
  instructorName,
  loadCohorts,
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

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color, label: "Bad" },
  { from: 60, to: 75, color: BAND_META.average.color, label: "Average" },
  { from: 75, to: 90, color: BAND_META.good.color, label: "Good" },
  { from: 90, to: 100, color: BAND_META.excellent.color, label: "Excellent" },
];

export default async function ReportsPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const win = reportPeriod(sp, await latestRatedDate(ws.courseId));
  const { period, from, to, label } = win;
  const prev = previousWindow(from, to);
  const [rows, prevRows, loop, cohortNames] = await Promise.all([
    fetchScored({ from, to, courseId: ws.courseId }),
    fetchScored({ from: prev.from, to: prev.to, courseId: ws.courseId }),
    loadLoop(ws.courseId),
    loadCohorts(ws.courseId),
  ]);
  const cur = scoreSummary(rows);
  const before = scoreSummary(prevRows);
  const attended = avgAttended(rows);
  const queue = queueCounts(rows);
  const base = hrefIn(ws.slug, "/reports");
  const qs = new URLSearchParams({ period });
  if (period === "custom") {
    qs.set("from", from);
    qs.set("to", to);
  } else qs.set("at", from);
  const csvHref = `${hrefIn(ws.slug, "/reports/export")}?${qs}`;

  // ── score vs previous period, aligned by position ──
  const daily = daysBetween(from, to) <= 21;
  const curB = daily ? byDay(rows).sort((a, b) => a.date.localeCompare(b.date)) : byWeek(rows, from, to);
  const prevB = daily ? byDay(prevRows).sort((a, b) => a.date.localeCompare(b.date)) : byWeek(prevRows, prev.from, prev.to);
  const labels = daily
    ? Array.from({ length: daysBetween(from, to) + 1 }, (_, i) => prettyDate(new Date(+new Date(from + "T00:00:00Z") + i * 86400000).toISOString().slice(0, 10)))
    : (curB as ReturnType<typeof byWeek>).map((w) => w.label);
  const curValues = daily
    ? Array.from({ length: labels.length }, (_, i) => {
        const d = new Date(+new Date(from + "T00:00:00Z") + i * 86400000).toISOString().slice(0, 10);
        return (curB as ReturnType<typeof byDay>).find((x) => x.date === d)?.value ?? null;
      })
    : (curB as ReturnType<typeof byWeek>).map((w) => w.avgScore);
  const prevValues = daily
    ? Array.from({ length: labels.length }, (_, i) => {
        const d = new Date(+new Date(prev.from + "T00:00:00Z") + i * 86400000).toISOString().slice(0, 10);
        return (prevB as ReturnType<typeof byDay>).find((x) => x.date === d)?.value ?? null;
      })
    : (prevB as ReturnType<typeof byWeek>).map((w) => w.avgScore);

  // ── movers ──
  const minClasses = period === "week" ? 2 : 3;
  const instructorMovers = movers(prevRows, rows, instructorKey, instructorName, minClasses, (key) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`));
  const moduleMovers = movers(prevRows.filter((r) => r.topic), rows, topicKey, (r) => r.topic.trim(), minClasses, (key) => hrefIn(ws.slug, `/modules/${encodeURIComponent(key)}`));

  // ── the tables: aggregate here, hand the client tables slim rows (they sort on the spot) ──
  const instructors = byInstructor(rows).sort((a, b) => (b.avgScore ?? -1) - (a.avgScore ?? -1));
  const prevScores = new Map(byInstructor(prevRows).map((i) => [i.key, i.avgScore]));
  const cohorts = byCohort(rows, cohortNames)
    .sort((a, b) => b.n - a.n)
    .map((c) => cohortRow(c, hrefIn(ws.slug, `/cohorts/${encodeURIComponent(c.ref.key)}`)));
  const topics = byTopic(rows)
    .filter((t) => t.n >= 2)
    .sort((a, b) => (a.avgScore ?? 101) - (b.avgScore ?? 101))
    .slice(0, 10)
    .map((t) => moduleRow(t, hrefIn(ws.slug, `/modules/${encodeURIComponent(t.key)}`)));
  const funnel = loopFunnel(rows, loop);
  const outcomes = outcomesFor(rows, loop);
  const worst = worstOf(rows, 10).map((r) => classRow(r, { href: drawerHref(r), reason: classReason(r), instructor: instructorName(r), outcome: outcomes.get(r.id) ?? null }));

  return (
    <div className="report-page space-y-4">
      <PrintStyles />
      <PageHeader
        title={`${ws.courseName} — ${label.toLowerCase()} report`}
        description={`${prettyDateYear(from)} – ${prettyDateYear(to)} · compared with ${prettyDate(prev.from)} – ${prettyDate(prev.to)} · generated live from the synced ratings`}
        actions={
          <>
            <Button asChild variant="outline" size="sm" data-print-hide>
              <a href={csvHref}>
                <Download aria-hidden /> CSV
              </a>
            </Button>
            <ShareButton courseId={ws.courseId} period={{ kind: period, from, to, label }} />
            <PrintButton />
          </>
        }
      />
      <PeriodTabs basePath={base} period={period} from={from} to={to} prev={win.prev} next={win.next} stale={win.stale} />

      {rows.length === 0 ? (
        <Section>
          <Empty>No rated classes for {ws.courseName} in this period.</Empty>
        </Section>
      ) : (
        <>
          <HeadlineTiles cur={cur} prev={before} queue={queue} attended={attended} />

          <ChartCard
            className="report-section"
            title="Score vs the previous period"
            subtitle={`Average score by ${daily ? "day" : "week"} · grey = the previous period at the same position`}
            legend={[{ label: "This period", color: "var(--chart-1)" }]}
            table={{ headers: [daily ? "Day" : "Week", "This period", "Previous"], rows: labels.map((l, i) => [l, fmtScore(curValues[i]), fmtScore(prevValues[i])]) }}
          >
            <LineChart labels={labels} series={[{ name: "This period", values: curValues }]} reference={{ name: "previous period", values: prevValues }} yDomain={[40, 100]} bands={ZONES} decimals={0} height={220} />
          </ChartCard>

          <div className="report-section grid gap-4 xl:grid-cols-2">
            <Section title="Instructors that moved" subtitle={`Average score vs the previous period · at least ${minClasses} classes in both`}>
              <RankedMovers items={instructorMovers} limit={5} />
            </Section>
            <Section title="Modules that moved" subtitle={`At least ${minClasses} classes in both periods`}>
              <RankedMovers items={moduleMovers} limit={5} />
            </Section>
          </div>

          <Section className="report-break" title="Worst classes" subtitle="Lowest scores, why, and what happened to each" flush>
            <WorstClassesTable rows={worst} withOutcome maxHeight="none" />
          </Section>

          <Section title="Instructors" subtitle={`Everyone with ${minClasses}+ classes · Δ vs the previous period`} flush>
            <Leaderboard
              items={instructors}
              reference={cur.avgScore}
              previous={prevScores}
              hrefFor={(key) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`)}
              minClasses={minClasses}
              maxHeight="none"
            />
          </Section>

          <div className="report-section grid gap-4 xl:grid-cols-2">
            <Section title="Cohorts" subtitle="Most classes first" flush>
              {cohorts.length === 0 ? <Empty>No cohort could be read for this period.</Empty> : <CohortsTable rows={cohorts} maxHeight="none" />}
            </Section>
            <Section title="Modules" subtitle="Lowest first" flush>
              {topics.length === 0 ? <Empty>No module has two rated classes in this period.</Empty> : <ModulesTable rows={topics} maxHeight="none" />}
            </Section>
          </div>

          <Section title="Loop outcomes" subtitle="Flagged → confirmed → analysed → approved → sent, with the median days per step">
            <LoopFunnel f={funnel} feedbackHref={hrefIn(ws.slug, "/feedback")} />
          </Section>
        </>
      )}
    </div>
  );
}
