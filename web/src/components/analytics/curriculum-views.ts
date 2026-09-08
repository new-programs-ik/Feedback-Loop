import "server-only";
import type { MapCell, MapCohort, MapModule } from "@/components/charts/curriculum-map";
import type { CohortRow } from "@/components/analytics/cohort-table";
import type { ClassRow } from "@/components/analytics/class-table";
import type { JourneyAxisProps } from "@/components/analytics/journey-chart";
import {
  COHORT_WEEKS,
  cohortRefs,
  initialsOf,
  instructorName,
  prettyDate,
  type CohortRef,
  type CurriculumMap,
  type Journey,
  type JourneyAxis,
  type ScoredRating,
} from "@/lib/analytics";

/** The slim view-models the analytics pages hand to their client tables and charts. A page
 *  computes everything here on the server from the rows it already has; only plain objects
 *  with the fields a table shows (plus an href) cross into the client — never a ScoredRating. */

/** The curriculum map's rows and columns. */
export function mapPropsOf(map: CurriculumMap): { cohorts: MapCohort[]; modules: MapModule[] } {
  const modules: MapModule[] = map.modules.map((m) => ({
    key: m.key,
    name: m.name,
    short: m.short,
    href: m.href,
    order: m.order,
    n: m.n,
    avgRating: m.avgRating,
    avgAttended: m.avgAttended,
    dropAttended: m.dropAttended,
    dropPairs: m.dropPairs,
  }));
  const cohorts: MapCohort[] = map.cohorts.map((c) => {
    const cells: Record<string, MapCell> = {};
    for (const [key, cell] of Object.entries(c.cells)) {
      cells[key] = {
        openId: cell.classIds[0],
        sessions: cell.classIds.length,
        rating: cell.rating,
        rated: cell.rated,
        attended: cell.attended,
        reach: cell.reach,
        score: cell.score,
        band: cell.band,
        kinds: cell.kinds,
        instructors: cell.instructors,
        initials: cell.instructors.slice(0, 2).map(initialsOf).join("·"),
        dateLabel: cell.dates.map(prettyDate).join(" · "),
      };
    }
    return {
      key: c.key,
      name: c.name,
      href: c.href,
      startLabel: c.start ?? prettyDate(c.firstDate),
      trackLabel: c.trackLabel,
      size: c.size,
      retention: c.retention,
      firstAttended: c.firstAttended,
      active: c.active,
      lastOrder: c.lastOrder,
      cells,
    };
  });
  return { cohorts, modules };
}

/** The cohort table's rows: each cohort's whole run so far. */
export function cohortRowsOf(map: CurriculumMap): CohortRow[] {
  return map.cohorts.map((c) => ({
    key: c.key,
    name: c.name,
    href: c.href ?? "#",
    trackLabel: c.trackLabel,
    region: c.region,
    startLabel: c.start ?? prettyDate(c.firstDate),
    start: c.firstDate,
    weekNow: c.weekNow,
    weeksTotal: COHORT_WEEKS,
    active: c.active,
    n: c.n,
    avgScore: c.avgScore,
    counts: c.counts,
    avgRating: c.avgRating,
    avgAttended: c.avgAttended,
    avgReach: c.avgReach,
    retention: c.retention,
    size: c.size,
    spark: map.modules.map((m) => c.cells[m.key]?.attended).filter((v): v is number => v != null),
  }));
}

/** X labels cut to what fits: the line chart lays `n` labels over ~600 viewBox px at ~5.6 px a
 *  character, so eleven modules get ten characters each and six get eighteen. The full text
 *  goes to the tooltip. */
export function axisLabels(labels: string[], width = 600): string[] {
  const max = Math.max(6, Math.floor(width / Math.max(1, labels.length) / 5.6));
  return labels.map((l) => (l.length > max ? l.slice(0, max - 1).trimEnd() + "…" : l));
}

/** One metric of the journey for the chart: the `limit` most recent cohorts as lines, the
 *  median of every cohort in bold. */
export function journeyPropsOf(journey: Journey, metric: "attended" | "rating", limit = 10): { byModule: JourneyAxisProps; byWeek: JourneyAxisProps } {
  const pick = (axis: JourneyAxis): JourneyAxisProps => ({
    labels: axisLabels(axis.labels),
    names: axis.names.map((n, i) => n ?? axis.labels[i]),
    notes: axis.notes,
    cohorts: axis.cohorts.slice(0, limit).map((c) => ({ key: c.key, name: c.name, values: c[metric] })),
    median: axis.median[metric],
  });
  return { byModule: pick(journey.byModule), byWeek: pick(journey.byWeek) };
}

/** A class table row from a scored row. `href` opens the drawer; the rest are the links the
 *  row's inner cells carry. */
export function classRowOf(
  r: ScoredRating,
  x: { href: string; week?: number | null; moduleHref?: string; cohort?: string; cohortHref?: string; instructorHref?: string; version?: string | number | null },
): ClassRow {
  return {
    id: r.id,
    href: x.href,
    week: x.week ?? r.week_no ?? null,
    module: r.topic.trim() || r.session_kind,
    moduleHref: x.moduleHref,
    cohort: x.cohort,
    cohortHref: x.cohortHref,
    date: r.class_date,
    dateLabel: prettyDate(r.class_date),
    kind: r.session_kind,
    instructor: instructorName(r),
    instructorHref: x.instructorHref,
    rating: r.rating,
    rated: r.num_ratings,
    attended: r.attended,
    reach: r.participation_pct,
    approval: r.approval_pct,
    pill: {
      score: r.score,
      band: r.band,
      provisional: r.provisional,
      action: r.action,
      rows: r.breakdown,
      reason: r.reason,
      version: r.scored_by === "db" ? x.version : "preview",
    },
  };
}

/** The first cohort a class belongs to (its name and key), for a cohort column. */
export function firstCohortOf(r: ScoredRating, names?: Map<string, CohortRef>): CohortRef | null {
  return cohortRefs(r, names)[0] ?? null;
}
