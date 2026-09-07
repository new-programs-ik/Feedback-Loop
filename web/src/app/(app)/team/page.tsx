import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, listCourses } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { Sparkline } from "@/components/charts/sparkline";
import { SmallMultiples } from "@/components/charts/small-multiples";
import { RankedMovers } from "@/components/charts/ranked-movers";
import { MatrixHeatmap, type MatrixCell } from "@/components/charts/matrix-heatmap";
import { BAND_META } from "@/lib/sentiment";
import { queueCost } from "@/lib/class-score";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { CourseSquare, DataTable, Delta, Empty, Section } from "@/components/analytics/ui";
import { LoopFunnel } from "@/components/analytics/report-blocks";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import {
  addDays,
  ago,
  byCourse,
  byMonth,
  byWeek,
  fetchScored,
  fmtScore,
  instructorName,
  loadLoop,
  loadPendingSuggestions,
  loadSync,
  loopFunnel,
  movers,
  plural,
  prettyMonth,
  queueCounts,
  scoreSummary,
  today,
  topicKey,
  weekStart,
} from "@/lib/analytics";
import { instructorKey } from "@/lib/ratings";

export const metadata: Metadata = { title: "Overview" };

const ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color },
  { from: 60, to: 75, color: BAND_META.average.color },
  { from: 75, to: 90, color: BAND_META.good.color },
  { from: 90, to: 100, color: BAND_META.excellent.color },
];

export default async function TeamPage() {
  const to = today();
  const yearStart = `${to.slice(0, 4)}-01-01`;
  const twelveWeeks = weekStart(addDays(to, -77));
  const from = yearStart < twelveWeeks ? yearStart : twelveWeeks;
  const from30 = addDays(to, -29);
  const from60 = addDays(to, -59);
  const [courses, rows, loop, sync, pending] = await Promise.all([listCourses(), fetchScored({ from, to }), loadLoop(null), loadSync(), loadPendingSuggestions()]);

  const recent = rows.filter((r) => r.class_date >= from30);
  const prior = rows.filter((r) => r.class_date >= from60 && r.class_date < from30);
  const last45 = rows.filter((r) => r.class_date >= addDays(to, -44));
  const weeks = byWeek(rows.filter((r) => r.class_date >= twelveWeeks), twelveWeeks, to);
  const weekLabels = weeks.map((w) => w.label);

  // ── course cards ──
  const byId = new Map(courses.map((c) => [c.id, c]));
  const cards = byCourse(recent)
    .map((c) => {
      const info = c.courseId ? byId.get(c.courseId) : undefined;
      const prev = scoreSummary(prior.filter((r) => (r.course_id ?? `label:${r.course_label}`) === c.key));
      const spark = byWeek(
        rows.filter((r) => (r.course_id ?? `label:${r.course_label}`) === c.key && r.class_date >= twelveWeeks),
        twelveWeeks,
        to,
      ).map((w) => w.avgScore);
      const q = queueCounts(last45.filter((r) => (r.course_id ?? `label:${r.course_label}`) === c.key));
      return { ...c, info, prev, spark, queue: q };
    })
    .sort((a, b) => (b.badShare ?? 0) - (a.badShare ?? 0) || b.counts.bad - a.counts.bad);
  const quiet = courses.filter((c) => !cards.some((k) => k.courseId === c.id));

  // ── small multiples (every course on one axis) ──
  const panels = cards
    .filter((c) => c.spark.some((v) => v != null))
    .map((c) => ({
      key: c.key,
      title: c.name,
      subtitle: `${c.n} classes · 30 days`,
      href: c.slug ? hrefIn(c.slug, "/overview") : undefined,
      headline: fmtScore(c.avgScore),
      values: c.spark,
      reference: weeks.map((w) => w.avgScore),
    }));

  // ── movers, month over month ──
  const months = byMonth(rows);
  const thisMonth = months[months.length - 1];
  const lastMonth = months[months.length - 2];
  const instructorMovers = thisMonth && lastMonth ? movers(lastMonth.rows, thisMonth.rows, instructorKey, instructorName, 3, (key) => `/team/instructors/${encodeURIComponent(key)}`) : [];
  const moduleMovers =
    thisMonth && lastMonth
      ? movers(lastMonth.rows, thisMonth.rows, (r) => `${r.course_id ?? r.course_label}|${topicKey(r)}`, (r) => r.topic.trim(), 3, (_, r) => (r.course_slug ? hrefIn(r.course_slug, `/modules/${encodeURIComponent(topicKey(r))}`) : undefined))
      : [];

  // ── course × month matrix ──
  const monthKeys = months.map((m) => m.month);
  const cells: MatrixCell[] = [];
  const allCourses = byCourse(rows);
  for (const c of allCourses) {
    for (const m of byMonth(c.rows)) cells.push({ row: c.key, col: m.month, value: m.avgScore, n: m.n, note: `${m.counts.bad} bad · ${m.counts.average} average` });
  }

  // ── queue capacity ──
  const capacity = allCourses
    .map((c) => {
      const q = queueCounts(last45.filter((r) => (r.course_id ?? `label:${r.course_label}`) === c.key));
      const cost = queueCost(q.video, q.transcript);
      return { ...c, q, cost, age: q.oldest ? Math.max(0, Math.round((+new Date(to) - +new Date(q.oldest)) / 86400000)) : null };
    })
    .filter((c) => c.q.total > 0)
    .sort((a, b) => b.q.total - a.q.total);
  const totalQueue = capacity.reduce((a, c) => ({ v: a.v + c.q.video, t: a.t + c.q.transcript }), { v: 0, t: 0 });
  const totalCost = queueCost(totalQueue.v, totalQueue.t);

  // ── loop funnel + housekeeping ──
  const funnel = loopFunnel(recent, loop);
  const noHandler = courses.filter((c) => !c.handler);

  return (
    <div className="space-y-4">
      <PageHeader title="All courses" description={`Last 30 days against the 30 before · ${recent.length} rated ${plural(recent.length, "class", "classes")} across ${cards.length} ${plural(cards.length, "course")}`} />

      {/* ── housekeeping ── */}
      <p className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
        <span>Last sync {sync.finishedAt ? ago(sync.finishedAt) : "never"}{sync.status && sync.status !== "ok" ? ` (${sync.status})` : ""}</span>
        <span>
          {sync.unmapped.length} unmapped {plural(sync.unmapped.length, "label")}
          {sync.unmapped.length > 0 && (
            <>
              {" · "}
              <Link href="/admin/sync" className="text-primary hover:underline">
                map
              </Link>
            </>
          )}
        </span>
        <span>
          {noHandler.length} {plural(noHandler.length, "course")} without a handler
          {noHandler.length > 0 && (
            <>
              {" · "}
              <Link href="/admin/people" className="text-primary hover:underline">
                assign
              </Link>
            </>
          )}
        </span>
        <span>
          {pending == null ? "identity review not set up" : `${pending} duplicate ${plural(pending, "name")} waiting`}
          {pending ? (
            <>
              {" · "}
              <Link href="/admin/identity" className="text-primary hover:underline">
                review
              </Link>
            </>
          ) : null}
        </span>
      </p>

      {/* ── course cards ── */}
      {cards.length === 0 ? (
        <Section>
          <Empty>No rated classes in the last 30 days — run a sync.</Empty>
        </Section>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {cards.map((c) => (
            <div key={c.key} className="bg-card shadow-soft relative rounded-xl border p-3.5">
              <div className="flex items-start gap-2.5">
                {c.info && <CourseSquare color={c.info.color} initials={c.info.initials} />}
                <div className="min-w-0 flex-1">
                  {c.slug ? (
                    <Link href={hrefIn(c.slug, "/overview")} className="hover:text-primary line-clamp-2 block text-[13px] leading-[1.25] font-semibold after:absolute after:inset-0" title={c.name}>
                      {c.name}
                    </Link>
                  ) : (
                    <span className="line-clamp-2 block text-[13px] leading-[1.25] font-semibold">{c.name}</span>
                  )}
                </div>
                <AvgScorePill score={c.avgScore} />
              </div>
              <p className="text-muted-foreground mt-1.5 truncate text-[11px]" data-numeric title={c.info?.handler ?? "no handler set"}>
                {c.n} {plural(c.n, "class", "classes")} · {c.info?.handler ? `handler ${c.info.handler}` : "no handler"}
              </p>
              <div className="mt-3 flex items-center gap-3">
                <BandStripOf counts={c.counts} className="flex-1" height="h-2" />
                <Sparkline values={c.spark.filter((v): v is number => v != null)} width={72} />
              </div>
              <div className="text-muted-foreground mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[11px]">
                <Delta value={c.avgScore == null || c.prev.avgScore == null ? null : c.avgScore - c.prev.avgScore} unit=" pts" suffix="vs prior 30d" />
                <span data-numeric>
                  open: {c.queue.video} bad · {c.queue.transcript} average
                </span>
              </div>
            </div>
          ))}
          {quiet.map((c) => (
            <div key={c.id} className="bg-card/60 relative rounded-xl border border-dashed p-3.5">
              <div className="flex items-center gap-2.5">
                <CourseSquare color={c.color} initials={c.initials} />
                <div className="min-w-0 flex-1">
                  <Link href={hrefIn(c.slug, "/overview")} className="hover:text-primary block truncate text-[13px] font-semibold after:absolute after:inset-0">
                    {c.name}
                  </Link>
                  <span className="text-muted-foreground block text-[11px]">no rated classes in 30 days · {c.handler ?? "no handler"}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {panels.length > 0 && (
        <Section title="Every course, one axis" subtitle="Average score by week over the last 12 weeks · grey = all courses">
          <SmallMultiples items={panels} labels={weekLabels} yDomain={[40, 100]} bands={ZONES} />
        </Section>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Instructors that moved" subtitle={thisMonth && lastMonth ? `${prettyMonth(lastMonth.month)} → ${prettyMonth(thisMonth.month)} · at least 3 classes in both months` : "Needs two months of data"}>
          <RankedMovers items={instructorMovers} limit={6} />
        </Section>
        <Section title="Modules that moved" subtitle={thisMonth && lastMonth ? `${prettyMonth(lastMonth.month)} → ${prettyMonth(thisMonth.month)} · per course · at least 3 classes in both months` : "Needs two months of data"}>
          <RankedMovers items={moduleMovers} limit={6} />
        </Section>
      </div>

      {cells.length > 0 && (
        <Section title="Course × month" subtitle={`Average score per month since ${prettyMonth(monthKeys[0])} · is the decline continuing?`} flush>
          <MatrixHeatmap
            rows={allCourses.sort((a, b) => a.name.localeCompare(b.name)).map((c) => ({ key: c.key, label: c.name, href: c.slug ? hrefIn(c.slug, "/overview") : undefined }))}
            cols={monthKeys.map((m) => ({ key: m, label: prettyMonth(m) }))}
            cells={cells}
            rowHeader="Course"
            minN={3}
          />
        </Section>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Queue capacity" subtitle={`Open analyses from the last 45 days · ${totalCost.label}`} flush>
          {capacity.length === 0 ? (
            <Empty>The queue is clear.</Empty>
          ) : (
            <DataTable>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Course</TableHead>
                  <TableHead className="text-right">Videos</TableHead>
                  <TableHead className="text-right">Transcripts</TableHead>
                  <TableHead className="text-right">Time</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                  <TableHead className="text-right">Oldest</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {capacity.map((c) => (
                  <TableRow key={c.key} className="relative">
                    <TableCell className="max-w-48 truncate font-medium">
                      {c.slug ? (
                        <Link href={hrefIn(c.slug, "/queue")} className="hover:text-primary after:absolute after:inset-0">
                          {c.name}
                        </Link>
                      ) : (
                        c.name
                      )}
                    </TableCell>
                    <TableNum className={c.q.video ? "font-semibold" : "text-muted-foreground"}>{c.q.video}</TableNum>
                    <TableNum className={c.q.transcript ? "" : "text-muted-foreground"}>{c.q.transcript}</TableNum>
                    <TableNum className="text-muted-foreground">{c.cost.minutes < 60 ? `${Math.round(c.cost.minutes)} min` : `${(c.cost.minutes / 60).toFixed(1)} h`}</TableNum>
                    <TableNum className="text-muted-foreground">${c.cost.usd.toFixed(2)}</TableNum>
                    <TableNum className={c.age != null && c.age > 14 ? "text-destructive font-semibold" : "text-muted-foreground"}>{c.age == null ? "—" : `${c.age} d`}</TableNum>
                  </TableRow>
                ))}
              </TableBody>
            </DataTable>
          )}
        </Section>
        <Section title="Is the loop closing?" subtitle="Classes flagged in the last 30 days, step by step">
          <LoopFunnel f={funnel} feedbackHref="/team/queue" />
        </Section>
      </div>
    </div>
  );
}
