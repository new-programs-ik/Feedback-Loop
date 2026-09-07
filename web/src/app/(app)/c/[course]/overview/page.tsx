import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { StackedBars } from "@/components/charts/stacked-bars";
import { HBars } from "@/components/charts/h-bars";
import { ScatterChart } from "@/components/charts/scatter-chart";
import { SmallMultiples } from "@/components/charts/small-multiples";
import { CalendarHeatmap } from "@/components/charts/calendar-heatmap";
import { BAND_META, BAND_ORDER } from "@/lib/sentiment";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { AvgScorePill, BandStripOf, CompareBullet } from "@/components/analytics/score";
import { Delta, Empty, Kpi, Section } from "@/components/analytics/ui";
import { Leaderboard } from "@/components/analytics/leaderboard";
import { WorstClasses } from "@/components/analytics/worst-classes";
import { InsightsStrip } from "@/components/analytics/insights-strip";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { DataTable } from "@/components/analytics/ui";
import {
  ALL_TRACKS,
  COHORT_WEEKS,
  activeCohortKeys,
  applyScope,
  byCohort,
  byDay,
  byInstructor,
  byTopic,
  byWeek,
  cohortFirstDates,
  curriculumMap,
  fetchScored,
  fmtPct,
  fmtScore,
  instructorName,
  isLive,
  isReview,
  loadCohorts,
  mapWindowStart,
  medianJourney,
  prettyDate,
  previousWindow,
  queueCounts,
  readScope,
  scopeQuery,
  scoreSummary,
  type SearchParams,
} from "@/lib/analytics";

export const metadata: Metadata = { title: "Overview" };

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color, label: "Bad" },
  { from: 60, to: 75, color: BAND_META.average.color, label: "Average" },
  { from: 75, to: 90, color: BAND_META.good.color, label: "Good" },
  { from: 90, to: 100, color: BAND_META.excellent.color, label: "Excellent" },
];

export default async function OverviewPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const prev = previousWindow(scope.from, scope.to);
  // One read covers the period, the period before it and the year the curriculum map needs.
  const wideFrom = mapWindowStart(prev.from, scope.to);
  const [wide, cohortNames] = await Promise.all([fetchScored({ from: wideFrom, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const rowsAll = wide.filter((r) => r.class_date >= scope.from);
  const prevAll = wide.filter((r) => r.class_date >= prev.from && r.class_date <= prev.to);
  const rows = applyScope(rowsAll, scope, cohortNames);
  const prevRows = applyScope(prevAll, scope, cohortNames);
  const cur = scoreSummary(rows);
  const before = scoreSummary(prevRows);
  const queue = queueCounts(rows);
  const prevQueue = queueCounts(prevRows);
  const base = hrefIn(ws.slug, "/overview");
  const q = scopeQuery(scope);

  // ── weekly line + band mix ──
  const weeks = byWeek(rows, scope.from, scope.to);
  const weekLabels = weeks.map((w) => w.label);

  // ── instructors ──
  const instructors = byInstructor(rows).sort((a, b) => (b.avgScore ?? -1) - (a.avgScore ?? -1));
  const prevScores = new Map(byInstructor(prevRows).map((i) => [i.key, i.avgScore]));
  const instructorOptions = instructors.filter((i) => i.n >= 1).map((i) => ({ key: i.key, name: i.name }));

  // ── cohorts ──
  const cohorts = byCohort(rowsAll, cohortNames).sort((a, b) => b.n - a.n);
  const cohortOptions = cohorts.map((c) => ({ key: c.ref.key, name: c.ref.name }));
  const cohortRef = medianJourney(cohorts);
  const cohortPanels = cohorts.slice(0, 8).map((c) => ({
    key: c.ref.key,
    title: c.ref.name,
    subtitle: `week ${Math.min(c.weekNow, COHORT_WEEKS)} of ${COHORT_WEEKS} · ${c.n} ${c.n === 1 ? "class" : "classes"}`,
    href: hrefIn(ws.slug, `/cohorts/${encodeURIComponent(c.ref.key)}`),
    headline: fmtScore(c.avgScore),
    values: c.weeks.map((w) => w.score),
    reference: cohortRef,
  }));

  // ── modules ──
  const topics = byTopic(rows, cohortFirstDates(rowsAll, cohortNames)).filter((t) => t.n >= 3 && t.avgScore != null);
  const hotspots = [...topics].sort((a, b) => a.avgScore! - b.avgScore!).slice(0, 8);

  // ── this course, right now: the curriculum map's top sentences (cohorts active in the period, whole runs) ──
  const wideRows = applyScope(wide, { ...scope, cohort: undefined }, cohortNames);
  const activeKeys = scope.cohort ? new Set([scope.cohort]) : activeCohortKeys(wideRows, scope.from, scope.to, cohortNames);
  const map = curriculumMap(wideRows, cohortNames, {
    cohortKeys: activeKeys,
    track: ALL_TRACKS,
    links: {
      module: (key) => hrefIn(ws.slug, `/modules/${encodeURIComponent(key)}`) + q,
      instructor: (key) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q,
      map: hrefIn(ws.slug, "/cohorts") + q,
    },
  });

  // ── live vs review ──
  const kinds = [
    { label: "Live classes", rows: rows.filter(isLive) },
    { label: "Test reviews", rows: rows.filter(isReview) },
  ].map((k) => ({ ...k, s: scoreSummary(k.rows) }));

  // ── reach vs score ──
  const scatter = rows.filter((r) => r.participation_pct != null && r.score != null);
  const points = scatter.map((r) => [Number(r.participation_pct), r.score!, r.band === "bad" || r.band === "average" ? 1 : 0] as [number, number, number]);
  const pointLabels = scatter.map((r) => `${r.topic || r.session_kind} · ${instructorName(r)} · ${prettyDate(r.class_date)}`);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Overview"
        description={`${ws.courseName} · ${prettyDate(scope.from)} – ${prettyDate(scope.to)} · vs the previous ${prev.span} days`}
      />
      <ScopeBar basePath={base} scope={scope} cohorts={cohortOptions} instructors={instructorOptions} />

      {rowsAll.length === 0 ? (
        <Section>
          <Empty
            action={
              <Link href={`${base}?range=custom&from=2026-01-01&to=${scope.to}`} className="text-primary text-[13px] hover:underline">
                Show everything since January
              </Link>
            }
          >
            No rated classes for {ws.courseName} in this period.
          </Empty>
        </Section>
      ) : (
        <>
          {/* ── KPI row ── */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
            <Kpi label="Classes rated" value={cur.n} sub={<Delta value={cur.n - before.n} suffix={`vs prior ${prev.span}d`} />} />
            <Kpi label="Avg score" value={<AvgScorePill score={cur.avgScore} />} sub={<Delta value={cur.avgScore == null || before.avgScore == null ? null : cur.avgScore - before.avgScore} unit=" pts" />} />
            <Kpi
              label="Band mix"
              value={<BandStripOf counts={cur.counts} className="w-full" height="h-2" />}
              sub={
                <span data-numeric>
                  {BAND_ORDER.map((b) => `${cur.counts[b]} ${BAND_META[b].short.toLowerCase()}`).join(" · ")}
                </span>
              }
            />
            <Kpi
              label="Approval"
              value={<span className={cur.approval != null && cur.approval < 80 ? "text-destructive" : ""}>{fmtPct(cur.approval)}</span>}
              sub={<Delta value={cur.approval == null || before.approval == null ? null : cur.approval - before.approval} unit=" pts" suffix="bar 80%" />}
            />
            <Kpi label="Reach" value={fmtPct(cur.reach)} sub={<Delta value={cur.reach == null || before.reach == null ? null : cur.reach - before.reach} unit=" pts" suffix="of the room rated" />} />
            <Kpi
              label="Attended per class"
              value={cur.avgAttended == null ? "—" : Math.round(cur.avgAttended)}
              sub={<Delta value={cur.avgAttended == null || before.avgAttended == null ? null : cur.avgAttended - before.avgAttended} suffix="learners in the room" />}
            />
            <Kpi
              label="Open queue"
              value={
                <Link href={hrefIn(ws.slug, "/queue")} className="hover:text-primary">
                  {queue.total}
                </Link>
              }
              sub={
                <>
                  <span data-numeric>
                    {queue.video} bad · {queue.transcript} average
                  </span>
                  <Delta value={queue.total - prevQueue.total} goodWhen="down" />
                </>
              }
            />
          </div>

          {/* ── this course, right now ── */}
          {map.cohorts.length >= 2 && map.insights.length > 0 && (
            <InsightsStrip title="This course, right now" subtitle="The three things the cohorts say first — where the room shrinks, where the rating dips, who lifts it. The map has the rest." insights={map.insights} limit={3} />
          )}

          {/* ── weekly score + band mix ── */}
          <div className="grid gap-4 xl:grid-cols-2">
            <ChartCard
              title="Score by week"
              subtitle="Average Class Sentiment Score · the four band zones shaded"
              table={{ headers: ["Week", "Avg score", "Classes", "Approval"], rows: weeks.map((w) => [w.label, fmtScore(w.avgScore), w.n, fmtPct(w.approval)]) }}
            >
              <LineChart labels={weekLabels} series={[{ name: "Avg score", values: weeks.map((w) => w.avgScore) }]} yDomain={[40, 100]} bands={ZONES} decimals={0} height={220} area />
            </ChartCard>
            <ChartCard
              title="Band mix by week"
              subtitle="Share of classes in each band · counts in the table"
              legend={BAND_ORDER.map((b) => ({ label: BAND_META[b].label, color: BAND_META[b].color }))}
              table={{ headers: ["Week", ...BAND_ORDER.map((b) => BAND_META[b].label), "Unbanded"], rows: weeks.map((w) => [w.label, ...BAND_ORDER.map((b) => w.counts[b]), w.counts.none]) }}
            >
              <StackedBars
                labels={weekLabels}
                segments={BAND_ORDER.map((b) => ({ name: BAND_META[b].label, color: BAND_META[b].color }))}
                values={weeks.map((w) => BAND_ORDER.map((b) => w.counts[b]))}
                normalize
                height={220}
              />
            </ChartCard>
          </div>

          {/* ── worst classes ── */}
          <Section title="Worst classes" subtitle="Lowest scores in the period · a row opens the class" flush actions={<Link href={hrefIn(ws.slug, "/classes") + q} className="text-primary text-xs hover:underline">All classes</Link>}>
            <WorstClasses rows={rows} limit={8} />
          </Section>

          {/* ── leaderboard ── */}
          <Section
            title="Instructors"
            subtitle="At least 3 classes · the bullet compares with the course average"
            flush
            actions={<Link href={hrefIn(ws.slug, "/instructors") + q} className="text-primary text-xs hover:underline">Full leaderboard</Link>}
          >
            <Leaderboard items={instructors} reference={cur.avgScore} previous={prevScores} hrefFor={(key) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q} limit={10} />
          </Section>

          <div className="grid gap-4 xl:grid-cols-2">
            {/* ── live vs review ── */}
            <Section title="Live vs review" subtitle="Is it the class or the review?" flush>
              <DataTable>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Kind</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                    <TableHead>Avg score</TableHead>
                    <TableHead>vs course</TableHead>
                    <TableHead className="text-right">Approval</TableHead>
                    <TableHead className="text-right">Reach</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {kinds.map((k) => (
                    <TableRow key={k.label}>
                      <TableCell className="font-medium">{k.label}</TableCell>
                      <TableNum className="text-muted-foreground">{k.s.n}</TableNum>
                      <TableCell>
                        <AvgScorePill score={k.s.avgScore} />
                      </TableCell>
                      <TableCell>
                        <CompareBullet value={k.s.avgScore} reference={cur.avgScore} />
                      </TableCell>
                      <TableNum className={k.s.approval != null && k.s.approval < 80 ? "text-destructive font-semibold" : ""}>{fmtPct(k.s.approval)}</TableNum>
                      <TableNum className="text-muted-foreground">{fmtPct(k.s.reach)}</TableNum>
                    </TableRow>
                  ))}
                </TableBody>
              </DataTable>
            </Section>

            {/* ── module hot-spots ── */}
            <Section title="Module hot-spots" subtitle="Lowest-scoring modules with 3+ classes, coloured by band" actions={<Link href={hrefIn(ws.slug, "/modules") + q} className="text-primary text-xs hover:underline">All modules</Link>}>
              {hotspots.length === 0 ? (
                <Empty className="px-0">No module has 3 scored classes in this period.</Empty>
              ) : (
                <HBars
                  items={hotspots.map((t) => ({
                    label: t.name,
                    value: Math.round(t.avgScore!),
                    sub: `${t.n} classes · ${t.instructors.length} ${t.instructors.length === 1 ? "instructor" : "instructors"}${t.tag ? ` · ${t.tag}` : ""}`,
                    color: t.band ? BAND_META[t.band].color : "var(--band-none)",
                    href: hrefIn(ws.slug, `/modules/${encodeURIComponent(t.key)}`) + q,
                  }))}
                  maxValue={100}
                  format={(v) => String(v)}
                />
              )}
            </Section>
          </div>

          {/* ── cohorts ── */}
          <Section title="Cohorts" subtitle={`Score by cohort week · grey = the median of every cohort · week n of ${COHORT_WEEKS}`} actions={<Link href={hrefIn(ws.slug, "/cohorts")} className="text-primary text-xs hover:underline">All cohorts</Link>}>
            {cohortPanels.length === 0 ? (
              <Empty className="px-0">No cohort could be read from the sheet&apos;s cohort text yet.</Empty>
            ) : (
              <SmallMultiples items={cohortPanels} labels={Array.from({ length: COHORT_WEEKS }, (_, i) => `W${i + 1}`)} yDomain={[40, 100]} bands={ZONES} />
            )}
          </Section>

          {/* ── reach vs score ── */}
          <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
            <ChartCard
              title="Reach vs score"
              subtitle="Are low scores just thin turnout? Every class by the share of the room that rated it"
              legend={[
                { label: "Good / Excellent", color: "var(--chart-1)" },
                { label: "Average / Bad", color: BAND_META.bad.color },
              ]}
            >
              {points.length === 0 ? (
                <Empty className="px-0">No class in this period carries attendance.</Empty>
              ) : (
                <ScatterChart
                  points={points}
                  labels={pointLabels}
                  yDomain={[40, 100]}
                  threshold={60}
                  bar={40}
                  cornerSide="left"
                  height={300}
                  xLabel="share of attendees who rated the class"
                  xValueLabel="reach"
                  yLabel="score"
                  lineLabel="score 60 — Bad below this"
                  barLabel="40% reach"
                  cornerLabel="low score on a thin turnout"
                  yLines={[
                    { at: 75, label: "Good" },
                    { at: 90, label: "Excellent" },
                  ]}
                  colors={["var(--chart-1)", BAND_META.bad.color]}
                  ariaLabel="Every class plotted by score against the share of attendees who rated it."
                />
              )}
            </ChartCard>
            <Section title="Calendar" subtitle="Average score per day · do bad classes cluster on certain days?">
              <CalendarHeatmap days={byDay(rows)} from={scope.from} to={scope.to} />
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
