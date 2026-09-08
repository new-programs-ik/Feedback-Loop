import type { Metadata } from "next";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { SmallMultiples } from "@/components/charts/small-multiples";
import { BAND_META } from "@/lib/sentiment";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { InsightsStrip } from "@/components/analytics/insights-strip";
import { ModuleTable, type ModuleRow } from "@/components/analytics/module-table";
import { ModuleMatrix, type MatrixPair } from "@/components/analytics/module-matrix";
import { Empty, Section } from "@/components/analytics/ui";
import {
  ALL_TRACKS,
  activeCohortKeys,
  applyScope,
  avgScore,
  byCohort,
  byInstructor,
  byMonth,
  byTopic,
  byWeek,
  cohortFirstDates,
  curriculumMap,
  daysBetween,
  fetchScored,
  fmtPct,
  fmtScore,
  inCurriculumOrder,
  loadCohorts,
  mapWindowStart,
  mean,
  moduleFixers,
  plural,
  prettyDate,
  readScope,
  scopeQuery,
  topicKey,
  type SearchParams,
} from "@/lib/analytics";
import { instructorKey } from "@/lib/ratings";

export const metadata: Metadata = { title: "Modules" };

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color },
  { from: 60, to: 75, color: BAND_META.average.color },
  { from: 75, to: 90, color: BAND_META.good.color },
  { from: 90, to: 100, color: BAND_META.excellent.color },
];

/** Every module in curriculum order with the score, the raw numbers, how attendance and the
 *  rating move against the module before, and who teaches it best. The Δ columns and the
 *  sentences come from the curriculum map of the cohorts active in the period (their whole
 *  runs, so a module early in the course still has a "before"). */
export default async function ModulesPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const wideFrom = mapWindowStart(scope.from, scope.to);
  const [wide, cohortNames] = await Promise.all([fetchScored({ from: wideFrom, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const rowsAll = wide.filter((r) => r.class_date >= scope.from);
  const rows = applyScope(rowsAll, scope, cohortNames);
  const topics = inCurriculumOrder(byTopic(rows, cohortFirstDates(wide, cohortNames)).filter((t) => t.n >= 2));
  const base = hrefIn(ws.slug, "/modules");
  const q = scopeQuery(scope);
  const href = (key: string) => hrefIn(ws.slug, `/modules/${encodeURIComponent(key)}`) + q;
  const instructorHref = (key: string) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q;
  const cohortOptions = byCohort(rowsAll, cohortNames).map((c) => ({ key: c.ref.key, name: c.ref.name }));
  const instructorOptions = byInstructor(rowsAll).map((i) => ({ key: i.key, name: i.name }));

  // ── the map behind the Δ columns and the sentences: the cohorts active in the period, whole runs ──
  const wideRows = applyScope(wide, { ...scope, cohort: undefined }, cohortNames);
  const active = scope.cohort ? new Set([scope.cohort]) : activeCohortKeys(wideRows, scope.from, scope.to, cohortNames);
  const map = curriculumMap(wideRows, cohortNames, { cohortKeys: active, track: ALL_TRACKS, links: { module: href, instructor: instructorHref } });
  const drops = new Map(map.modules.map((m) => [m.key, m]));

  const tableRows: ModuleRow[] = topics.map((t, i) => {
    const fix = moduleFixers({ rows: t.rows }, { instructor: instructorHref });
    const seasoned = fix.instructors.filter((x) => x.n >= 2 && x.rating != null);
    const best = fix.instructors.length >= 2 && seasoned.length ? seasoned[0] : null;
    const worst = fix.struggles[0] ?? null;
    const d = drops.get(t.key);
    return {
      key: t.key,
      name: t.name,
      href: href(t.key),
      order: t.order,
      orderLabel: t.order != null ? `W${Math.round(t.order)}` : String(i + 1),
      tag: t.tag,
      n: t.n,
      instructors: t.instructors.length,
      avgScore: t.avgScore,
      counts: t.counts,
      avgRating: fix.avgRating,
      avgAttended: t.avgAttended,
      avgReach: t.reach,
      approval: t.approval,
      dropAttended: d?.dropAttended ?? null,
      dropPairs: d?.dropPairs ?? 0,
      dropRating: d?.dropRating ?? null,
      best: best ? { name: best.name, href: best.href ?? instructorHref(best.key), rating: best.rating!, n: best.n } : null,
      worst: worst ? { name: worst.name, href: worst.href ?? instructorHref(worst.key), rating: worst.rating!, n: worst.n } : null,
    };
  });

  // ── module × instructor ──
  const instructors = byInstructor(rows.filter((r) => topics.some((t) => t.key === topicKey(r))))
    .filter((i) => i.n >= 2)
    .sort((a, b) => b.n - a.n)
    .slice(0, 24);
  const pairs: MatrixPair[] = [];
  for (const t of topics.slice(0, 40)) {
    for (const i of instructors) {
      const list = t.rows.filter((r) => instructorKey(r) === i.key);
      if (list.length === 0) continue;
      const clear = list.filter((r) => r.approval_pct != null && r.approval_pct >= 80).length;
      pairs.push({
        row: t.key,
        col: i.key,
        n: list.length,
        score: avgScore(list),
        rating: mean(list.map((r) => r.rating).filter((v) => v > 0)),
        attended: mean(list.map((r) => r.attended).filter((v): v is number => v != null)),
        note: `${i.name} · ${fmtPct((clear / list.length) * 100)} of classes clear the approval bar`,
      });
    }
  }
  const courseAvgAttended = mean(rows.map((r) => r.attended).filter((v): v is number => v != null));

  // ── trend of the six weakest ──
  const weakest = topics.filter((t) => t.n >= 3 && t.avgScore != null).sort((a, b) => a.avgScore! - b.avgScore!).slice(0, 6);
  const useWeeks = daysBetween(scope.from, scope.to) <= 100;
  const buckets = useWeeks ? byWeek(rows, scope.from, scope.to).map((w) => ({ key: w.week, label: w.label })) : byMonth(rows).map((m) => ({ key: m.month, label: m.label }));
  const trendItems = weakest.map((t) => {
    const per = useWeeks ? new Map(byWeek(t.rows, scope.from, scope.to).map((w) => [w.week, w.avgScore])) : new Map(byMonth(t.rows).map((m) => [m.month, m.avgScore]));
    return { key: t.key, title: t.name, subtitle: `${t.n} classes`, href: href(t.key), headline: fmtScore(t.avgScore), values: buckets.map((b) => per.get(b.key) ?? null) };
  });

  return (
    <div className="space-y-4">
      <PageHeader title="Modules" description={`${topics.length} ${plural(topics.length, "module")} with 2+ classes, in curriculum order · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`} />
      <ScopeBar basePath={base} scope={scope} cohorts={cohortOptions} instructors={instructorOptions} />

      <InsightsStrip
        title="What stands out"
        subtitle={`Along the runs of the ${map.cohorts.length} ${plural(map.cohorts.length, "cohort")} with a class in this period — where the room shrinks, where the rating dips, who lifts it.`}
        insights={map.insights}
      />

      <Section
        title="Every module"
        subtitle="Score first, raw numbers beside it · Δ columns compare each module with the one each cohort took just before · content = low across two or more instructors, delivery = low for one of several"
        flush
      >
        {topics.length === 0 ? <Empty>No module has two rated classes in this period — most rows still carry the generic session label.</Empty> : <ModuleTable rows={tableRows} />}
      </Section>

      {pairs.length > 0 && (
        <Section title="Module × instructor" subtitle="Who has taught what, and how it went · the number of classes under each value · dashed = a single class · arrow keys move between cells" flush>
          <ModuleMatrix
            rows={topics.slice(0, 40).map((t) => ({ key: t.key, label: t.name, href: href(t.key) }))}
            cols={instructors.map((i) => ({ key: i.key, label: i.name, href: instructorHref(i.key) }))}
            pairs={pairs}
            courseAvgAttended={courseAvgAttended}
            rowHeader="Module"
            minN={2}
          />
        </Section>
      )}

      {trendItems.length > 0 && (
        <Section title="The six weakest, over time" subtitle={`Average score by ${useWeeks ? "week" : "month"} · a gap is a period without a class`}>
          <SmallMultiples items={trendItems} labels={buckets.map((b) => b.label)} yDomain={[40, 100]} bands={ZONES} />
        </Section>
      )}
    </div>
  );
}
