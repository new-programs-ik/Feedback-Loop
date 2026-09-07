import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { BAND_META } from "@/lib/sentiment";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { AvgScorePill, BandStripOf, ClassScorePill, CompareBullet } from "@/components/analytics/score";
import { DataTable, Delta, Empty, KindChip, Kpi, Section } from "@/components/analytics/ui";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import {
  applyScope,
  byCohort,
  byInstructor,
  byWeek,
  drawerHref,
  fetchScored,
  fmtPct,
  fmtScore,
  instructorName,
  loadCohorts,
  parseTopicId,
  prettyDate,
  readScope,
  rowsForTopic,
  scopeQuery,
  scoreSummary,
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

export default async function ModulePage({ params, searchParams }: Props) {
  const [{ course: slug, id }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const parsed = parseTopicId(id);
  const [rowsAll, cohortNames] = await Promise.all([fetchScored({ from: scope.from, to: scope.to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const scoped = applyScope(rowsAll, scope, cohortNames);
  const own = rowsForTopic(scoped, parsed);
  const name = own[0]?.topic.trim() ?? parsed.name ?? "Module";
  const t = scoreSummary(own);
  const course = scoreSummary(scoped);
  const instructors = byInstructor(own).sort((a, b) => (b.avgScore ?? -1) - (a.avgScore ?? -1));
  const cohorts = byCohort(own, cohortNames).sort((a, b) => b.lastDate.localeCompare(a.lastDate));
  const weeks = byWeek(own, scope.from, scope.to);
  const base = hrefIn(ws.slug, `/modules/${encodeURIComponent(id)}`);
  const q = scopeQuery(scope);
  const classes = [...own].sort((a, b) => b.class_date.localeCompare(a.class_date));

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{name}</span>
            <AvgScorePill score={t.avgScore} />
          </span>
        }
        description={`${t.n} rated ${t.n === 1 ? "class" : "classes"} · ${instructors.length} ${instructors.length === 1 ? "instructor" : "instructors"} · ${cohorts.length} ${cohorts.length === 1 ? "cohort" : "cohorts"} · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`}
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi label="Avg score" value={<AvgScorePill score={t.avgScore} />} sub={<Delta value={t.avgScore == null || course.avgScore == null ? null : t.avgScore - course.avgScore} unit=" pts" suffix="vs course" />} />
            <Kpi label="Band mix" value={<BandStripOf counts={t.counts} className="w-full" height="h-2" />} sub={`${t.counts.bad} bad · ${t.counts.average} average`} />
            <Kpi label="Approval" value={<span className={t.approval != null && t.approval < 80 ? "text-destructive" : ""}>{fmtPct(t.approval)}</span>} sub={t.votes ? `${t.votes} votes` : "no votes"} />
            <Kpi label="Reach" value={fmtPct(t.reach)} sub="share of the room that rated" />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Section title="By instructor" subtitle="Who should teach this next time?" flush>
              <DataTable>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Instructor</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                    <TableHead>Avg score</TableHead>
                    <TableHead>vs module</TableHead>
                    <TableHead className="text-right">Approval</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {instructors.map((i) => (
                    <TableRow key={i.key} className="relative">
                      <TableCell className="max-w-48">
                        <Link href={hrefIn(ws.slug, `/instructors/${encodeURIComponent(i.key)}`) + q} className="hover:text-primary block truncate font-medium after:absolute after:inset-0">
                          {i.name}
                        </Link>
                      </TableCell>
                      <TableNum className="text-muted-foreground">{i.n}</TableNum>
                      <TableCell>
                        <AvgScorePill score={i.avgScore} />
                      </TableCell>
                      <TableCell>
                        <CompareBullet value={i.avgScore} reference={t.avgScore} referenceLabel="module avg" />
                      </TableCell>
                      <TableNum className={i.approval != null && i.approval < 80 ? "text-destructive font-semibold" : ""}>{fmtPct(i.approval)}</TableNum>
                    </TableRow>
                  ))}
                </TableBody>
              </DataTable>
            </Section>
            <Section title="By cohort" flush>
              {cohorts.length === 0 ? (
                <Empty>No cohort could be read for these classes.</Empty>
              ) : (
                <DataTable>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Cohort</TableHead>
                      <TableHead className="text-right">Classes</TableHead>
                      <TableHead>Avg score</TableHead>
                      <TableHead className="text-right">Last class</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {cohorts.map((c) => (
                      <TableRow key={c.ref.key} className="relative">
                        <TableCell className="max-w-64">
                          <Link href={hrefIn(ws.slug, `/cohorts/${encodeURIComponent(c.ref.key)}`)} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={c.ref.name}>
                            {c.ref.name}
                          </Link>
                        </TableCell>
                        <TableNum className="text-muted-foreground">{c.n}</TableNum>
                        <TableCell>
                          <AvgScorePill score={c.avgScore} />
                        </TableCell>
                        <TableNum className="text-muted-foreground">{prettyDate(c.lastDate)}</TableNum>
                      </TableRow>
                    ))}
                  </TableBody>
                </DataTable>
              )}
            </Section>
          </div>

          <ChartCard title="Score by week" subtitle="Average score of this module's classes" table={{ headers: ["Week", "Avg score", "Classes"], rows: weeks.map((w) => [w.label, fmtScore(w.avgScore), w.n]) }}>
            <LineChart labels={weeks.map((w) => w.label)} series={[{ name: name, values: weeks.map((w) => w.avgScore) }]} yDomain={[40, 100]} bands={ZONES} decimals={0} height={200} />
          </ChartCard>

          <Section title="Every class" flush>
            <DataTable>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Score</TableHead>
                  <TableHead>Instructor</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead className="text-right">Rating</TableHead>
                  <TableHead className="text-right">Approval</TableHead>
                  <TableHead className="text-right">Rated</TableHead>
                  <TableHead className="text-right">Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {classes.map((r) => (
                  <TableRow key={r.id} className="relative">
                    <TableCell>
                      <ClassScorePill row={r} />
                    </TableCell>
                    <TableCell className="max-w-48 truncate">
                      <Link href={drawerHref(r)} className="hover:text-primary after:absolute after:inset-0">
                        {instructorName(r)}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <KindChip kind={r.session_kind} />
                    </TableCell>
                    <TableNum>{r.rating.toFixed(2)}</TableNum>
                    <TableNum className={r.approval_pct != null && r.approval_pct < 80 ? "text-destructive font-semibold" : "text-muted-foreground"}>{fmtPct(r.approval_pct)}</TableNum>
                    <TableNum className="text-muted-foreground">{r.num_ratings != null && r.attended != null ? `${r.num_ratings} of ${r.attended}` : "—"}</TableNum>
                    <TableNum className="text-muted-foreground">{prettyDate(r.class_date)}</TableNum>
                  </TableRow>
                ))}
              </TableBody>
            </DataTable>
          </Section>
        </>
      )}
    </div>
  );
}
