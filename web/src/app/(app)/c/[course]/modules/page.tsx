import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { MatrixHeatmap, type MatrixCell } from "@/components/charts/matrix-heatmap";
import { SmallMultiples } from "@/components/charts/small-multiples";
import { BAND_META } from "@/lib/sentiment";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { DataTable, Empty, Section } from "@/components/analytics/ui";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import {
  applyScope,
  avgScore,
  byCohort,
  byInstructor,
  byMonth,
  byTopic,
  byWeek,
  cohortFirstDates,
  daysBetween,
  fetchScored,
  fmtPct,
  fmtScore,
  inCurriculumOrder,
  loadCohorts,
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

function Tag({ tag }: { tag: "content" | "delivery" | null }) {
  if (!tag) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="inline-flex items-center rounded border px-1.5 py-px text-[10.5px] font-medium"
      style={{ color: tag === "content" ? BAND_META.bad.text : BAND_META.average.text, borderColor: tag === "content" ? BAND_META.bad.color : BAND_META.average.color }}
      title={tag === "content" ? "Low across two or more instructors — the material" : "Low for one instructor, fine for the others — the delivery"}
    >
      {tag}
    </span>
  );
}

export default async function ModulesPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const [rowsAll, cohortNames] = await Promise.all([fetchScored({ from: scope.from, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const rows = applyScope(rowsAll, scope, cohortNames);
  const topics = inCurriculumOrder(byTopic(rows, cohortFirstDates(rowsAll, cohortNames)).filter((t) => t.n >= 2));
  const base = hrefIn(ws.slug, "/modules");
  const q = scopeQuery(scope);
  const href = (key: string) => hrefIn(ws.slug, `/modules/${encodeURIComponent(key)}`) + q;
  const cohortOptions = byCohort(rowsAll, cohortNames).map((c) => ({ key: c.ref.key, name: c.ref.name }));
  const instructorOptions = byInstructor(rowsAll).map((i) => ({ key: i.key, name: i.name }));

  // ── module × instructor matrix ──
  const instructors = byInstructor(rows.filter((r) => topics.some((t) => t.key === topicKey(r))))
    .filter((i) => i.n >= 2)
    .sort((a, b) => b.n - a.n)
    .slice(0, 24);
  const cells: MatrixCell[] = [];
  for (const t of topics.slice(0, 40)) {
    for (const i of instructors) {
      const list = t.rows.filter((r) => instructorKey(r) === i.key);
      if (list.length === 0) continue;
      const v = avgScore(list);
      cells.push({ row: t.key, col: i.key, value: v, n: list.length, note: `${i.name} · ${fmtPct(list.length ? list.filter((r) => r.approval_pct != null && r.approval_pct >= 80).length / list.length * 100 : null)} of classes clear the approval bar` });
    }
  }

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
      <PageHeader title="Modules" description={`${topics.length} modules with 2+ classes, in curriculum order · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`} />
      <ScopeBar basePath={base} scope={scope} cohorts={cohortOptions} instructors={instructorOptions} />

      <Section title="Every module" subtitle="content = low across two or more instructors · delivery = low for one of several · best SME needs two instructors with repeat classes" flush>
        {topics.length === 0 ? (
          <Empty>No module has two rated classes in this period — most rows still carry the generic session label.</Empty>
        ) : (
          <DataTable>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-right">#</TableHead>
                <TableHead>Module</TableHead>
                <TableHead>Tag</TableHead>
                <TableHead className="text-right">Classes</TableHead>
                <TableHead className="text-right">Instructors</TableHead>
                <TableHead>Avg score</TableHead>
                <TableHead>Band mix</TableHead>
                <TableHead className="text-right">Approval</TableHead>
                <TableHead>Best-known SME</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topics.map((t, i) => (
                <TableRow key={t.key} className="relative">
                  <TableNum className="text-muted-foreground">{t.order != null ? `W${Math.round(t.order)}` : i + 1}</TableNum>
                  <TableCell className="max-w-72">
                    <Link href={href(t.key)} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={t.name}>
                      {t.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Tag tag={t.tag} />
                  </TableCell>
                  <TableNum className="text-muted-foreground">{t.n}</TableNum>
                  <TableNum className="text-muted-foreground">{t.instructors.length}</TableNum>
                  <TableCell>
                    <AvgScorePill score={t.avgScore} />
                  </TableCell>
                  <TableCell>
                    <BandStripOf counts={t.counts} className="w-20" />
                  </TableCell>
                  <TableNum className={t.approval != null && t.approval < 80 ? "text-destructive font-semibold" : ""}>{fmtPct(t.approval)}</TableNum>
                  <TableCell className="max-w-48 truncate">
                    {t.bestSme ? (
                      <>
                        <Link href={hrefIn(ws.slug, `/instructors/${encodeURIComponent(t.bestSme.key)}`) + q} className="hover:text-primary relative z-[1]">
                          {t.bestSme.name}
                        </Link>
                        <span className="text-muted-foreground" data-numeric>
                          {" "}· {fmtScore(t.bestSme.avgScore)}
                        </span>
                      </>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </DataTable>
        )}
      </Section>

      {cells.length > 0 && (
        <Section title="Module × instructor" subtitle="Average score per pair, with the number of classes · dashed = a single class · arrow keys move between cells" flush>
          <MatrixHeatmap
            rows={topics.slice(0, 40).map((t) => ({ key: t.key, label: t.name, href: href(t.key) }))}
            cols={instructors.map((i) => ({ key: i.key, label: i.name, href: hrefIn(ws.slug, `/instructors/${encodeURIComponent(i.key)}`) + q }))}
            cells={cells}
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
