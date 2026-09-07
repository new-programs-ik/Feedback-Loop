import type { Metadata } from "next";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { SegmentedTabs } from "@/components/ui/tabs";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { CurriculumMap } from "@/components/charts/curriculum-map";
import { InsightsStrip } from "@/components/analytics/insights-strip";
import { JourneyChart } from "@/components/analytics/journey-chart";
import { CohortTable } from "@/components/analytics/cohort-table";
import { Empty, Section } from "@/components/analytics/ui";
import { classDrawerFor, classHrefPrefix } from "@/components/analytics/class-drawer-slot";
import { cohortRowsOf, journeyPropsOf, mapPropsOf } from "@/components/analytics/curriculum-views";
import {
  ALL_TRACKS,
  activeCohortKeys,
  applyScope,
  attendanceJourney,
  curriculumMap,
  fetchScored,
  loadCohorts,
  mapWindowStart,
  one,
  plural,
  prettyDate,
  readScope,
  scopeQuery,
  type SearchParams,
} from "@/lib/analytics";

export const metadata: Metadata = { title: "Cohorts" };

/** Every cohort of the course against every module: where the room shrinks, where the rating
 *  drops, and who lifts it. The period picks WHICH cohorts appear (those with a class in it);
 *  each cohort is then drawn over its whole run, so earlier modules are never blank just
 *  because the period starts after them. A course with parallel tracks (SWE / EM / PM …) is
 *  read one track at a time — the biggest first — or all together. */
export default async function CohortsPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const track = one(sp, "track") || undefined;
  const classId = one(sp, "class") || undefined;
  const wideFrom = mapWindowStart(scope.from, scope.to);
  const [wide, cohortNames] = await Promise.all([fetchScored({ from: wideFrom, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const wideRows = applyScope(wide, { ...scope, cohort: undefined }, cohortNames);
  const active = activeCohortKeys(wideRows, scope.from, scope.to, cohortNames);

  const base = hrefIn(ws.slug, "/cohorts");
  const q = scopeQuery(scope);
  const qTrack = scopeQuery(scope, "90d", { track });
  const map = curriculumMap(wideRows, cohortNames, {
    cohortKeys: active,
    track,
    links: {
      module: (key) => hrefIn(ws.slug, `/modules/${encodeURIComponent(key)}`) + q,
      instructor: (key) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q,
      cohort: (key) => hrefIn(ws.slug, `/cohorts/${encodeURIComponent(key)}`),
    },
  });
  const journey = attendanceJourney(map.cohorts, map.modules);
  const { cohorts, modules } = mapPropsOf(map);
  const tableRows = cohortRowsOf(map);
  const trackItems =
    map.tracks.length >= 2
      ? [
          { label: "All tracks", href: base + scopeQuery(scope, "90d", { track: ALL_TRACKS }), active: map.track === ALL_TRACKS },
          ...map.tracks.map((t) => ({ label: `${t.label} · ${t.cohorts}`, href: base + scopeQuery(scope, "90d", { track: t.track }), active: map.track === t.track })),
        ]
      : [];
  const shown = Math.min(10, map.cohorts.length);
  const drawer = classId ? await classDrawerFor({ id: classId, closeHref: base + qTrack, slug: ws.slug, rows: wide }) : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Cohorts"
        description={`${map.cohorts.length} ${plural(map.cohorts.length, "cohort")} with a class between ${prettyDate(scope.from)} and ${prettyDate(scope.to)} · ${map.modules.length} ${plural(map.modules.length, "module")} in curriculum order${map.track !== ALL_TRACKS ? ` · ${map.tracks.find((t) => t.track === map.track)?.label ?? map.track} track` : ""}`}
      />
      <ScopeBar basePath={base} scope={scope} show={{ cohort: false, kind: true, band: true, instructor: false }} extra={{ track }} />

      {wide.length === 0 ? (
        <Section>
          <Empty>No rated classes for {ws.courseName} in the last year.</Empty>
        </Section>
      ) : (
        <>
          {trackItems.length > 0 && (
            <div className="flex flex-wrap items-center gap-3" data-print-hide>
              <span className="text-muted-foreground text-xs">Track</span>
              <SegmentedTabs items={trackItems} ariaLabel="Track" />
              <span className="text-muted-foreground text-[11px]">A track is one audience — its cohorts take their own set of modules.</span>
            </div>
          )}

          <InsightsStrip title="What stands out" subtitle="Read from the map below — where the room shrinks, where the rating dips, who lifts the weak module." insights={map.insights} />

          <Section
            title="Every cohort, every module"
            subtitle="Which module loses the room and where the rating drops, cohort by cohort · each cell: the rating, then who rated over who came · a click opens the class"
            flush
          >
            <CurriculumMap cohorts={cohorts} modules={modules} hrefPrefix={classHrefPrefix(base, qTrack)} />
          </Section>

          {map.cohorts.length > 0 && map.modules.length > 0 && (
            <div className="grid gap-4 xl:grid-cols-2">
              <JourneyChart
                title="Attendance along the course"
                subtitle={`How many learners are in the room at each module · the ${shown} most recent ${plural(shown, "cohort")} · the median of all ${map.cohorts.length} in bold`}
                metric="attended"
                medianOf={map.cohorts.length}
                {...journeyPropsOf(journey, "attended", 10)}
              />
              <JourneyChart
                title="Rating along the course"
                subtitle={`Where the rating drops along the course · same cohorts, same axis · the 4.55 line dashed`}
                metric="rating"
                medianOf={map.cohorts.length}
                {...journeyPropsOf(journey, "rating", 10)}
              />
            </div>
          )}

          <Section title="Every cohort" subtitle="Each cohort's whole run so far — the score first, the raw numbers beside it · click a column to sort" flush>
            {tableRows.length === 0 ? <Empty>No cohort could be read from this period&apos;s classes — the sheet&apos;s cohort text is empty or unparsed.</Empty> : <CohortTable rows={tableRows} showTrack={map.track === ALL_TRACKS && map.tracks.length >= 2} />}
          </Section>
        </>
      )}
      {drawer}
    </div>
  );
}
