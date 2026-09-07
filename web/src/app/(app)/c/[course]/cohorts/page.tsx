import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { Sparkline } from "@/components/charts/sparkline";
import { SmallMultiples } from "@/components/charts/small-multiples";
import { BAND_META } from "@/lib/sentiment";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { DataTable, Empty, Section } from "@/components/analytics/ui";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import {
  COHORT_WEEKS,
  applyScope,
  byCohort,
  fetchScored,
  fmtScore,
  loadCohorts,
  medianJourney,
  prettyDate,
  readScope,
  scopeQuery,
  type SearchParams,
} from "@/lib/analytics";

export const metadata: Metadata = { title: "Cohorts" };

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color },
  { from: 60, to: 75, color: BAND_META.average.color },
  { from: 75, to: 90, color: BAND_META.good.color },
  { from: 90, to: 100, color: BAND_META.excellent.color },
];

export default async function CohortsPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const [rowsAll, cohortNames] = await Promise.all([fetchScored({ from: scope.from, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const rows = applyScope(rowsAll, { ...scope, cohort: undefined }, cohortNames);
  const cohorts = byCohort(rows, cohortNames).sort((a, b) => b.lastDate.localeCompare(a.lastDate));
  const reference = medianJourney(cohorts);
  const base = hrefIn(ws.slug, "/cohorts");
  const q = scopeQuery(scope);
  const href = (key: string) => hrefIn(ws.slug, `/cohorts/${encodeURIComponent(key)}`) + q;
  const labels = Array.from({ length: COHORT_WEEKS }, (_, i) => `W${i + 1}`);

  return (
    <div className="space-y-4">
      <PageHeader title="Cohorts" description={`${cohorts.length} ${cohorts.length === 1 ? "cohort" : "cohorts"} with rated classes · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`} />
      <ScopeBar basePath={base} scope={scope} show={{ cohort: false, kind: true, band: true, instructor: false }} />
      <Section title="Every cohort" subtitle={`Week n of ${COHORT_WEEKS} counts from the cohort's first rated class · the sparkline is the score by week`} flush>
        {cohorts.length === 0 ? (
          <Empty>No cohort could be read from this period&apos;s classes — the sheet&apos;s cohort text is empty or unparsed.</Empty>
        ) : (
          <DataTable>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Cohort</TableHead>
                <TableHead>Region</TableHead>
                <TableHead>Start</TableHead>
                <TableHead className="text-right">Week</TableHead>
                <TableHead className="text-right">Classes</TableHead>
                <TableHead>Avg score</TableHead>
                <TableHead>Band mix</TableHead>
                <TableHead>Journey</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cohorts.map((c) => (
                <TableRow key={c.ref.key} className="relative">
                  <TableCell className="max-w-72">
                    <Link href={href(c.ref.key)} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={c.ref.name}>
                      {c.ref.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{c.ref.region ?? "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{c.ref.start ?? prettyDate(c.firstDate)}</TableCell>
                  <TableNum>
                    {Math.min(c.weekNow, 99)} <span className="text-muted-foreground">of {COHORT_WEEKS}</span>
                  </TableNum>
                  <TableNum className="text-muted-foreground">{c.n}</TableNum>
                  <TableCell>
                    <AvgScorePill score={c.avgScore} />
                  </TableCell>
                  <TableCell>
                    <BandStripOf counts={c.counts} className="w-20" />
                  </TableCell>
                  <TableCell>
                    <Sparkline values={c.weeks.map((w) => w.score).filter((v): v is number => v != null)} width={84} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </DataTable>
        )}
      </Section>
      {cohorts.length > 1 && (
        <Section title="Side by side" subtitle="Score by cohort week on one axis · grey = the median of every cohort at that week">
          <SmallMultiples
            items={cohorts.slice(0, 12).map((c) => ({
              key: c.ref.key,
              title: c.ref.name,
              subtitle: `${c.ref.region ?? ""}${c.ref.region && c.ref.start ? " · " : ""}${c.ref.start ?? ""}`,
              href: href(c.ref.key),
              headline: fmtScore(c.avgScore),
              values: c.weeks.map((w) => w.score),
              reference,
            }))}
            labels={labels}
            yDomain={[40, 100]}
            bands={ZONES}
          />
        </Section>
      )}
    </div>
  );
}
