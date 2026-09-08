import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { BAND_META } from "@/lib/sentiment";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { ClassTable } from "@/components/analytics/class-table";
import { ModuleInstructorTable, type ModuleInstructorRow } from "@/components/analytics/module-instructor-table";
import { Delta, Empty, Kpi, Section } from "@/components/analytics/ui";
import { classDrawerFor, classHrefPrefix } from "@/components/analytics/class-drawer-slot";
import { axisLabels, classRowOf, firstCohortOf } from "@/components/analytics/curriculum-views";
import { getActiveConfig } from "@/lib/scoring";
import {
  RATING_LINE,
  applyScope,
  byCohort,
  byInstructor,
  byWeek,
  cohortFirstDates,
  fetchScored,
  fmtPct,
  fmtScore,
  instructorKey,
  loadCohorts,
  mapWindowStart,
  mean,
  moduleFixers,
  one,
  parseTopicId,
  plural,
  prettyDate,
  readScope,
  rowsForTopic,
  scopeQuery,
  scoreSummary,
  shortCohortName,
  type SearchParams,
} from "@/lib/analytics";

type Props = { params: Promise<{ course: string; id: string }>; searchParams: Promise<SearchParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: parseTopicId(id).name ?? "Module" };
}

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color, label: "Bad" },
  { from: 60, to: 75, color: BAND_META.average.color, label: "Average" },
  { from: 75, to: 90, color: BAND_META.good.color, label: "Good" },
  { from: 90, to: 100, color: BAND_META.excellent.color, label: "Excellent" },
];

/** One module: who teaches it and how it goes for each of them, how it has gone cohort after
 *  cohort (a fix over time shows as a rising line), and every class as a row that opens the
 *  drawer. */
export default async function ModulePage({ params, searchParams }: Props) {
  const [{ course: slug, id }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const parsed = parseTopicId(id);
  const classId = one(sp, "class") || undefined;
  const wideFrom = mapWindowStart(scope.from, scope.to);
  const [wide, cohortNames, active] = await Promise.all([fetchScored({ from: wideFrom, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId), getActiveConfig()]);
  const rowsAll = wide.filter((r) => r.class_date >= scope.from);
  const scoped = applyScope(rowsAll, scope, cohortNames);
  const own = rowsForTopic(scoped, parsed);
  const name = own[0]?.topic.trim() ?? parsed.name ?? "Module";
  const t = scoreSummary(own);
  const course = scoreSummary(scoped);
  const base = hrefIn(ws.slug, `/modules/${encodeURIComponent(id)}`);
  const q = scopeQuery(scope);
  const instructorHref = (key: string) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q;
  const cohortHref = (key: string) => hrefIn(ws.slug, `/cohorts/${encodeURIComponent(key)}`);

  // ── by instructor: the fixers table ──
  const fix = moduleFixers({ rows: own }, { instructor: instructorHref });
  const aggs = new Map(byInstructor(own).map((i) => [i.key, i]));
  const instructorRows: ModuleInstructorRow[] = fix.instructors.map((i) => ({
    key: i.key,
    name: i.name,
    href: i.href ?? instructorHref(i.key),
    n: i.n,
    avgScore: aggs.get(i.key)?.avgScore ?? null,
    rating: i.rating,
    attended: i.attended,
    reach: i.reach,
    delta: i.delta,
    verdict: i.verdict,
    approval: aggs.get(i.key)?.approval ?? null,
  }));

  // ── by cohort, in the order the cohorts started: does the module get better over time? ──
  const firstDates = cohortFirstDates(wide, cohortNames);
  const cohorts = byCohort(own, cohortNames)
    .map((c) => ({ c, start: firstDates.get(c.ref.key) ?? c.firstDate, rating: mean(c.rows.map((r) => r.rating).filter((v) => v > 0)) }))
    .sort((a, b) => a.start.localeCompare(b.start));
  const cohortNamesShort = cohorts.map((x) => shortCohortName(x.c.ref, 40));
  const cohortLabels = axisLabels(cohortNamesShort);
  const weeks = byWeek(own, scope.from, scope.to);

  // ── every class ──
  const openPrefix = classHrefPrefix(base, q);
  const classRows = own.map((r) => {
    const ref = firstCohortOf(r, cohortNames);
    return classRowOf(r, {
      href: `${openPrefix}${encodeURIComponent(r.id)}`,
      cohort: ref?.name,
      cohortHref: ref ? cohortHref(ref.key) : undefined,
      instructorHref: instructorHref(instructorKey(r)),
      version: active.version,
    });
  });
  const drawer = classId ? await classDrawerFor({ id: classId, closeHref: base + q, slug: ws.slug, rows: wide }) : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{name}</span>
            <AvgScorePill score={t.avgScore} />
          </span>
        }
        description={`${t.n} rated ${plural(t.n, "class", "classes")} · ${fix.instructors.length} ${plural(fix.instructors.length, "instructor")} · ${cohorts.length} ${plural(cohorts.length, "cohort")} · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`}
        actions={
          <Link href={hrefIn(ws.slug, "/modules") + q} className="text-muted-foreground hover:text-foreground text-[13px]">
            ← All modules
          </Link>
        }
      />
      <ScopeBar basePath={base} scope={scope} show={{ cohort: false, instructor: false, kind: true, band: true }} />

      {own.length === 0 ? (
        <Section>
          <Empty>No rated classes of this module in the period — widen the period.</Empty>
        </Section>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Avg score" value={<AvgScorePill score={t.avgScore} />} sub={<Delta value={t.avgScore == null || course.avgScore == null ? null : t.avgScore - course.avgScore} unit=" pts" suffix="vs course" />} />
            <Kpi
              label="Avg rating"
              value={<span className={fix.avgRating != null && fix.avgRating < RATING_LINE ? "text-destructive" : ""}>{fix.avgRating == null ? "—" : fix.avgRating.toFixed(2)}</span>}
              sub={<Delta value={fix.avgRating == null || course.avgRating == null ? null : fix.avgRating - course.avgRating} decimals={2} suffix="vs course" />}
            />
            <Kpi label="Attended per class" value={t.avgAttended == null ? "—" : Math.round(t.avgAttended)} sub={<Delta value={t.avgAttended == null || course.avgAttended == null ? null : t.avgAttended - course.avgAttended} suffix="vs course" />} />
            <Kpi label="Rated / attended" value={fmtPct(t.reach)} sub={<Delta value={t.reach == null || course.reach == null ? null : t.reach - course.reach} unit=" pts" suffix="of those who attended rated" />} />
            <Kpi label="Approval" value={<span className={t.approval != null && t.approval < 80 ? "text-destructive" : ""}>{fmtPct(t.approval)}</span>} sub={t.votes ? `${t.votes} votes` : "no votes"} />
            <Kpi label="Band mix" value={<BandStripOf counts={t.counts} className="w-full" height="h-2" />} sub={`${t.counts.bad} bad · ${t.counts.average} average`} />
          </div>

          <Section title="By instructor" subtitle="Who should teach this next time? Rating, room and reach for each · lifts = 0.15 above the module's average with two or more classes, struggles = 0.15 under" flush>
            <ModuleInstructorTable rows={instructorRows} moduleAvg={fix.avgRating} />
          </Section>

          <div className="grid gap-4 xl:grid-cols-2">
            <ChartCard
              title="Rating by cohort"
              subtitle="Cohorts in the order they started — a module that got fixed climbs from left to right · the 4.55 line dashed"
              table={{
                headers: ["Cohort", "Started", "Avg rating", "Classes"],
                rows: cohorts.map((x, i) => [cohortNamesShort[i], x.c.ref.start ?? prettyDate(x.start), x.rating == null ? "—" : x.rating.toFixed(2), x.c.n]),
              }}
            >
              {cohorts.length === 0 ? (
                <Empty className="px-2">No cohort could be read for these classes.</Empty>
              ) : (
                <LineChart
                  labels={cohortLabels}
                  series={[{ name: "Avg rating", values: cohorts.map((x) => x.rating) }]}
                  xAnnotations={cohorts.map((x) => x.c.ref.start ?? prettyDate(x.start))}
                  tooltipTitles={cohorts.map((x) => x.c.ref.name)}
                  labelStep={cohorts.length <= 10 ? 1 : undefined}
                  threshold={RATING_LINE}
                  thresholdLabel="4.55 line"
                  decimals={2}
                  height={220}
                />
              )}
            </ChartCard>
            <ChartCard title="Score by week" subtitle="Average score of this module's classes" table={{ headers: ["Week", "Avg score", "Classes"], rows: weeks.map((w) => [w.label, fmtScore(w.avgScore), w.n]) }}>
              <LineChart labels={weeks.map((w) => w.label)} series={[{ name: name, values: weeks.map((w) => w.avgScore) }]} yDomain={[40, 100]} bands={ZONES} decimals={0} height={220} />
            </ChartCard>
          </div>

          <Section title="Every class" subtitle="Cohort, date, instructor, the rating over who rated and who came, the score · a row opens the class · click a column to sort" flush>
            <ClassTable rows={classRows} show={{ module: false, cohort: true, kind: true, approval: true }} initialSort={{ key: "date", dir: "desc" }} activeId={classId} />
          </Section>
        </>
      )}
      {drawer}
    </div>
  );
}
