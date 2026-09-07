import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { SmallMultiples } from "@/components/charts/small-multiples";
import { BAND_META } from "@/lib/sentiment";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { DataTable, Delta, Empty, Kpi, Section } from "@/components/analytics/ui";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import {
  COHORT_WEEKS,
  addDays,
  byCohort,
  fetchScored,
  fmtPct,
  fmtScore,
  loadCohorts,
  medianJourney,
  parseCohortId,
  prettyDate,
  today,
  type SearchParams,
} from "@/lib/analytics";

type Props = { params: Promise<{ course: string; id: string }>; searchParams: Promise<SearchParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const key = parseCohortId(id);
  return { title: key.startsWith("key:") ? key.slice(4).replace(/-/g, " ") : "Cohort" };
}

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color, label: "Bad" },
  { from: 60, to: 75, color: BAND_META.average.color, label: "Average" },
  { from: 75, to: 90, color: BAND_META.good.color, label: "Good" },
  { from: 90, to: 100, color: BAND_META.excellent.color, label: "Excellent" },
];

export default async function CohortPage({ params }: Props) {
  const { course: slug, id } = await params;
  const ws = await resolveWorkspace(slug);
  const key = parseCohortId(id);
  const to = today();
  const from = addDays(to, -365);
  const [rows, cohortNames] = await Promise.all([fetchScored({ from, to, courseId: ws.courseId }), loadCohorts(ws.courseId)]);
  const cohorts = byCohort(rows, cohortNames);
  const me = cohorts.find((c) => c.ref.key === key);
  if (!me) notFound();

  const audience = me.ref.audience ?? null;
  const earlier = cohorts.filter((c) => c.ref.key !== key && c.firstDate < me.firstDate).sort((a, b) => b.firstDate.localeCompare(a.firstDate));
  const sameAudience = earlier.filter((c) => (c.ref.audience ?? null) === audience);
  const referenceSet = sameAudience.length ? sameAudience : earlier;
  const reference = medianJourney(referenceSet);
  const lastThree = earlier.slice(0, 3);
  const weeks = me.weeks;
  const labels = weeks.map((w) => `W${w.week}`);
  const weekNow = Math.min(me.weekNow, weeks.length);
  const overall = fmtScore(me.avgScore);
  const refAvg = referenceSet.length ? referenceSet.reduce((a, c) => a + (c.avgScore ?? 0), 0) / referenceSet.length : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{me.ref.name}</span>
            <AvgScorePill score={me.avgScore} />
          </span>
        }
        description={
          <span className="flex flex-wrap gap-x-3">
            {me.ref.region && <span>{me.ref.region}</span>}
            <span>started {me.ref.start ?? prettyDate(me.firstDate)}</span>
            <span>
              week {weekNow} of {COHORT_WEEKS}
            </span>
            <span>
              {me.n} rated {me.n === 1 ? "class" : "classes"}
            </span>
          </span>
        }
        actions={
          <Link href={hrefIn(ws.slug, "/cohorts")} className="text-muted-foreground hover:text-foreground text-[13px]">
            ← All cohorts
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label="Avg score" value={overall} sub={refAvg != null ? <Delta value={me.avgScore == null ? null : me.avgScore - refAvg} suffix={`vs ${sameAudience.length ? "earlier " + (audience ?? "") : "earlier"} cohorts`} /> : "no earlier cohort"} />
        <Kpi label="Band mix" value={<BandStripOf counts={me.counts} className="w-full" height="h-2" />} sub={`${me.counts.bad} bad · ${me.counts.average} average`} />
        <Kpi label="Approval" value={<span className={me.approval != null && me.approval < 80 ? "text-destructive" : ""}>{fmtPct(me.approval)}</span>} sub={me.votes ? `${me.votes} votes` : "no votes"} />
        <Kpi label="Reach" value={fmtPct(me.reach)} sub="share of the room that rated" />
      </div>

      <ChartCard
        title="The journey"
        subtitle={`Score by cohort week · live and review · grey = median of ${referenceSet.length} earlier ${sameAudience.length ? (audience ?? "") + " " : ""}${referenceSet.length === 1 ? "cohort" : "cohorts"} at the same week`}
        legend={[
          { label: "Live", color: "var(--chart-1)" },
          { label: "Review", color: "var(--chart-2)" },
        ]}
        table={{
          headers: ["Week", "Live", "Review", "Reference", "Modules"],
          rows: weeks.map((w, i) => [labels[i], fmtScore(w.live), fmtScore(w.review), fmtScore(reference[i]), w.topics.join(", ")]),
        }}
      >
        <LineChart
          labels={labels}
          series={[
            { name: "Live", values: weeks.map((w) => w.live) },
            { name: "Review", values: weeks.map((w) => w.review) },
          ]}
          reference={{ name: "earlier cohorts", values: reference }}
          xAnnotations={weeks.map((w) => w.topics[0] ?? null)}
          yDomain={[40, 100]}
          bands={ZONES}
          decimals={0}
          height={260}
        />
      </ChartCard>

      <Section title="Week by week" subtitle="Modules, instructors, the live and review pills, reach" flush>
        <DataTable>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-right">Week</TableHead>
              <TableHead>Modules</TableHead>
              <TableHead>Instructors</TableHead>
              <TableHead>Live</TableHead>
              <TableHead>Review</TableHead>
              <TableHead className="text-right">Reach</TableHead>
              <TableHead className="text-right">Classes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {weeks
              .filter((w) => w.n > 0 || w.week <= weekNow)
              .map((w) => (
                <TableRow key={w.week} className={w.week === weekNow ? "bg-accent/30" : undefined}>
                  <TableNum className="font-medium">{w.week}</TableNum>
                  <TableCell className="text-muted-foreground max-w-64 truncate" title={w.topics.join(", ")}>
                    {w.topics.join(", ") || "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-48 truncate" title={w.instructors.join(", ")}>
                    {w.instructors.join(", ") || "—"}
                  </TableCell>
                  <TableCell>{w.live != null ? <AvgScorePill score={w.live} label="live" /> : <span className="text-muted-foreground">—</span>}</TableCell>
                  <TableCell>{w.review != null ? <AvgScorePill score={w.review} label="review" /> : <span className="text-muted-foreground">—</span>}</TableCell>
                  <TableNum className="text-muted-foreground">{fmtPct(w.reach)}</TableNum>
                  <TableNum className="text-muted-foreground">{w.n}</TableNum>
                </TableRow>
              ))}
          </TableBody>
        </DataTable>
      </Section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Against the last three cohorts" subtitle="Same axis, same weeks">
          {lastThree.length === 0 ? (
            <Empty className="px-0">No earlier cohort in the last year.</Empty>
          ) : (
            <SmallMultiples
              items={[me, ...lastThree].map((c) => ({
                key: c.ref.key,
                title: c.ref.key === key ? `${c.ref.name} (this)` : c.ref.name,
                subtitle: c.ref.start ?? prettyDate(c.firstDate),
                href: c.ref.key === key ? undefined : hrefIn(ws.slug, `/cohorts/${encodeURIComponent(c.ref.key)}`),
                headline: fmtScore(c.avgScore),
                values: c.weeks.map((w) => w.score),
                reference,
                accent: c.ref.key === key ? "var(--chart-1)" : "var(--chart-7)",
              }))}
              labels={labels}
              yDomain={[40, 100]}
              bands={ZONES}
              minWidth={200}
            />
          )}
        </Section>
        <ChartCard title="Reach by week" subtitle="Share of the room that rated · the 40% bar" table={{ headers: ["Week", "Reach", "Classes"], rows: weeks.map((w, i) => [labels[i], fmtPct(w.reach), w.n]) }}>
          <LineChart labels={labels} series={[{ name: "Reach", values: weeks.map((w) => w.reach) }]} threshold={40} thresholdLabel="40% bar" yDomain={[0, 100]} unit="%" decimals={0} height={200} />
        </ChartCard>
      </div>
    </div>
  );
}
