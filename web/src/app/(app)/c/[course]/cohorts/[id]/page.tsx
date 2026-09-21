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
import { ClassTable } from "@/components/analytics/class-table";
import { RetentionCell } from "@/components/analytics/cohort-table";
import { Delta, Empty, Kpi, Section } from "@/components/analytics/ui";
import { classDrawerFor, classHrefPrefix } from "@/components/analytics/class-drawer-slot";
import { classRowOf } from "@/components/analytics/curriculum-views";
import { getActiveConfig } from "@/lib/scoring";
import {
  ALL_TRACKS,
  COHORT_WEEKS,
  addDays,
  byCohort,
  cohortWeekOf,
  curriculumMap,
  fetchScored,
  fmtPct,
  fmtScore,
  hasRealTopic,
  instructorKey,
  loadCohorts,
  mean,
  medianJourney,
  one,
  parseCohortId,
  plural,
  prettyDate,
  today,
  topicKey,
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

/** One cohort's run: the score journey, the room and the reach week by week, and every class
 *  as a row that opens the drawer. */
export default async function CohortPage({ params, searchParams }: Props) {
  const [{ course: slug, id }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const key = parseCohortId(id);
  const classId = one(sp, "class") || undefined;
  const to = today();
  const from = addDays(to, -365);
  const [rows, cohortNames, active] = await Promise.all([fetchScored({ from, to, courseId: ws.courseId }), loadCohorts(ws.courseId), getActiveConfig()]);
  const cohorts = byCohort(rows, cohortNames);
  const me = cohorts.find((c) => c.ref.key === key);
  if (!me) notFound();

  const base = hrefIn(ws.slug, `/cohorts/${encodeURIComponent(id)}`);
  const moduleHref = (k: string) => hrefIn(ws.slug, `/modules/${encodeURIComponent(k)}`);
  const instructorHref = (k: string) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(k)}`);
  const run = curriculumMap(rows, cohortNames, { cohortKeys: new Set([key]), track: ALL_TRACKS, links: { module: moduleHref } }).cohorts[0];

  const audience = me.ref.audience ?? null;
  const earlier = cohorts.filter((c) => c.ref.key !== key && c.firstDate < me.firstDate).sort((a, b) => b.firstDate.localeCompare(a.firstDate));
  const sameAudience = earlier.filter((c) => (c.ref.audience ?? null) === audience);
  const referenceSet = sameAudience.length ? sameAudience : earlier;
  const reference = medianJourney(referenceSet);
  const lastThree = earlier.slice(0, 3);
  const weeks = me.weeks;
  const labels = weeks.map((w) => `W${w.week}`);
  const weekNow = Math.min(me.weekNow, weeks.length);
  const refAvg = mean(referenceSet.map((c) => c.avgScore).filter((v): v is number => v != null));
  const refAttended = mean(referenceSet.map((c) => c.avgAttended).filter((v): v is number => v != null));
  const refLabel = `vs ${referenceSet.length} earlier ${sameAudience.length && audience ? `${audience} ` : ""}${plural(referenceSet.length, "cohort")}`;
  const attendedByWeek = labels.map((_, i) => run?.weeks[i]?.attended ?? null);
  const maxRoom = Math.max(0, ...attendedByWeek.filter((v): v is number => v != null));

  const openPrefix = classHrefPrefix(base, "");
  const classRows = me.rows.map((r) =>
    classRowOf(r, {
      href: `${openPrefix}${encodeURIComponent(r.id)}`,
      week: cohortWeekOf(r, me.firstDate),
      moduleHref: hasRealTopic(r) ? moduleHref(topicKey(r)) : undefined,
      instructorHref: instructorHref(instructorKey(r)),
      version: active.version,
    }),
  );
  const drawer = classId ? await classDrawerFor({ id: classId, closeHref: base, slug: ws.slug, rows }) : null;

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
            {run?.track && run.track !== "other" && <span>{run.trackLabel} track</span>}
            <span>started {me.ref.start ?? prettyDate(me.firstDate)}</span>
            <span>
              week {weekNow} of {COHORT_WEEKS}
              {run?.active ? " · running" : ""}
            </span>
            <span>
              {me.n} rated {plural(me.n, "class", "classes")}
            </span>
            {run?.size != null && <span>{run.size} learners at most</span>}
          </span>
        }
        actions={
          <Link href={hrefIn(ws.slug, "/cohorts")} className="text-muted-foreground hover:text-foreground text-[13px]">
            ← All cohorts
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Avg score" value={fmtScore(me.avgScore)} sub={refAvg != null ? <Delta value={me.avgScore == null ? null : me.avgScore - refAvg} suffix={refLabel} /> : "no earlier cohort"} />
        <Kpi label="Band mix" value={<BandStripOf counts={me.counts} className="w-full" height="h-2" />} sub={`${me.counts.bad} bad · ${me.counts.average} average`} />
        <Kpi label="Instructor approval" value={<span className={me.approval != null && me.approval < 80 ? "text-destructive" : ""}>{fmtPct(me.approval)}</span>} sub={me.votes ? `${me.votes} learners answered` : "no approval answers"} />
        <Kpi label="Rated / attended" value={fmtPct(me.reach)} sub="share of the room that rated" />
        <Kpi
          label="Avg attended"
          value={me.avgAttended == null ? "—" : Math.round(me.avgAttended)}
          sub={refAttended != null ? <Delta value={me.avgAttended == null ? null : me.avgAttended - refAttended} suffix={refLabel} /> : "learners in the room per class"}
        />
        <Kpi
          label="Retention"
          value={<RetentionCell value={run?.retention ?? null} />}
          sub={run?.firstAttended != null && run.lastAttended != null ? <span data-numeric>{run.firstAttended} in the first module → {run.lastAttended} in the last</span> : "needs two modules with attendance"}
        />
      </div>

      <ChartCard
        title="The journey"
        subtitle={`Score by cohort week · live and review · grey = median of ${referenceSet.length} earlier ${sameAudience.length ? (audience ?? "") + " " : ""}${plural(referenceSet.length, "cohort")} at the same week`}
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

      <ChartCard
        title="How many attended, and how many rated, by week"
        subtitle="How many learners came, and how many of them rated · the 40% line dashed"
        table={{
          headers: ["Week", "Attended", "Rated / attended", "Classes"],
          rows: weeks.map((w, i) => [labels[i], attendedByWeek[i] == null ? "—" : Math.round(attendedByWeek[i]!), fmtPct(w.reach), w.n]),
        }}
      >
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="text-muted-foreground px-1 pt-1 text-[11px] font-medium">Learners in the room</div>
            <LineChart labels={labels} series={[{ name: "Attended", values: attendedByWeek }]} yDomain={[0, Math.max(10, Math.ceil((maxRoom * 1.15) / 5) * 5)]} decimals={0} height={190} area />
          </div>
          <div>
            <div className="text-muted-foreground px-1 pt-1 text-[11px] font-medium">Share of the room that rated</div>
            <LineChart labels={labels} series={[{ name: "Rated / attended", values: weeks.map((w) => w.reach) }]} threshold={40} thresholdLabel="40% bar" yDomain={[0, 100]} unit="%" decimals={0} height={190} colors={["var(--chart-3)"]} />
          </div>
        </div>
      </ChartCard>

      <Section title="Every class" subtitle="The run in order — module, instructor, the rating over who rated and who came, the score · a row opens the class" flush>
        <ClassTable rows={classRows} show={{ week: true, module: true, kind: true }} initialSort={{ key: "date", dir: "asc" }} activeId={classId} emptyText="No rated classes for this cohort yet." />
      </Section>

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
      {drawer}
    </div>
  );
}
