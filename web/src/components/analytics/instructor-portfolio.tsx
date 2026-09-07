import * as React from "react";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { HBars } from "@/components/charts/h-bars";
import { BAND_META } from "@/lib/sentiment";
import { AvgScorePill, BandStripOf, ClassScorePill, CompareBullet } from "@/components/analytics/score";
import { DataTable, Delta, Empty, Kpi, KindChip, Section } from "@/components/analytics/ui";
import {
  QUADRANT_META,
  beforeAfter,
  byMonth,
  byTopic,
  byWeek,
  drawerHref,
  feedbackEventsFor,
  fmtPct,
  fmtScore,
  instructorName,
  prettyDate,
  quadrantOf,
  scoreSummary,
  weekStart,
  type LoopClass,
  type Quadrant,
  type ScoredRating,
} from "@/lib/analytics";

const BAND_ZONES = [
  { from: 0, to: 60, color: BAND_META.bad.color, label: "Bad" },
  { from: 60, to: 75, color: BAND_META.average.color, label: "Average" },
  { from: 75, to: 90, color: BAND_META.good.color, label: "Good" },
  { from: 90, to: 100, color: BAND_META.excellent.color, label: "Excellent" },
];

/** One instructor's portfolio, shared by the course and team routes. `own` is the instructor's
 *  rows in the window; `all` is the course's (or team's) rows in the same window for the
 *  averages; `history` is the instructor's rows over a longer window for the trend and the
 *  before → after of AI feedback. */
export function InstructorPortfolio({
  id,
  own,
  all,
  history,
  loop,
  aliases,
  from,
  to,
  scopeLabel,
  backHref,
  modulesHrefFor,
}: {
  id: { instructorId: string | null; name: string | null };
  own: ScoredRating[];
  all: ScoredRating[];
  history: ScoredRating[];
  loop: LoopClass[];
  aliases: string[];
  from: string;
  to: string;
  scopeLabel: string;
  backHref: string;
  modulesHrefFor?: (topicKey: string) => string;
}) {
  const sample = own[0] ?? history[0];
  const name = sample ? instructorName(sample) : (id.name ?? "Instructor");
  const recorded = [...new Set([...aliases, ...history.map((r) => r.instructor.trim()), ...own.map((r) => r.instructor.trim())].filter((s) => s && s !== name))];
  const t = scoreSummary(own);
  const courseAvg = scoreSummary(all).avgScore;
  const courses = [...new Set(own.map((r) => r.course_name ?? r.course_label))];

  // ── trend: weekly over the history window, with markers where AI feedback was sent ──
  const historyFrom = history.length ? [...history].map((r) => r.class_date).sort()[0] : from;
  const weeks = byWeek(history, historyFrom < from ? historyFrom : from, to);
  const events = feedbackEventsFor(loop, id, [name, ...recorded]);
  const weekIndex = new Map(weeks.map((w, i) => [w.week, i]));
  const markers = events
    .map((e) => ({ index: weekIndex.get(weekStart(e.sentAt.slice(0, 10))) ?? -1, label: "feedback sent", color: "var(--foreground)" }))
    .filter((m) => m.index >= 0);
  const courseWeeks = byWeek(all, historyFrom < from ? historyFrom : from, to);

  // ── modules: this instructor vs the course's module average (diverging around 0) ──
  const courseTopics = new Map(byTopic(all).map((tp) => [tp.key, tp]));
  const ownTopics = byTopic(own)
    .filter((tp) => tp.n >= 1 && tp.avgScore != null)
    .map((tp) => {
      const ref = courseTopics.get(tp.key)?.avgScore ?? null;
      return { ...tp, ref, diff: ref == null ? null : tp.avgScore! - ref };
    })
    .filter((tp) => tp.diff != null)
    .sort((a, b) => b.diff! - a.diff!);

  // ── monthly approval vs the 80% bar ──
  const months = byMonth(history);

  // ── the four boxes ──
  const boxes: Record<Quadrant, number> = { fine: 0, polite: 0, hard: 0, fails: 0 };
  let voted = 0;
  for (const r of own) {
    const q = quadrantOf(r);
    if (q) {
      boxes[q] += 1;
      voted += 1;
    }
  }

  // ── best / worst five ──
  const scored = own.filter((r) => r.score != null);
  const best = [...scored].sort((a, b) => b.score! - a.score!).slice(0, 5);
  const worst = [...scored].sort((a, b) => a.score! - b.score!).slice(0, 5);

  // ── AI-feedback history with before → after ──
  const feedbackRows = events.map((e) => ({ ...e, ...beforeAfter(history, e.date, 3) }));

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span>{name}</span>
            <AvgScorePill score={t.avgScore} />
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {recorded.length > 0 && <span>also recorded as {recorded.join(", ")}</span>}
            {courses.length > 0 && <span>{courses.join(" · ")}</span>}
            <span>
              {t.n} {t.n === 1 ? "class" : "classes"} · {scopeLabel} · {prettyDate(from)} – {prettyDate(to)}
            </span>
          </span>
        }
        actions={
          <Link href={backHref} className="text-muted-foreground hover:text-foreground text-[13px]">
            ← All instructors
          </Link>
        }
      />

      {own.length === 0 ? (
        <Section>
          <Empty>No rated classes for this instructor in the range — widen the period.</Empty>
        </Section>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Classes" value={t.n} sub={`${own.filter((r) => r.session_kind === "Live Class").length} live · ${own.filter((r) => r.session_kind === "Test Review").length} reviews`} />
            <Kpi label="Avg score" value={<AvgScorePill score={t.avgScore} />} sub={courseAvg != null ? <Delta value={t.avgScore == null ? null : t.avgScore - courseAvg} suffix="vs course avg" /> : null} />
            <Kpi label="Band mix" value={<BandStripOf counts={t.counts} className="w-full" height="h-2" />} sub={`${t.counts.bad} bad · ${t.counts.average} average`} />
            <Kpi label="Approval" value={<span className={t.approval != null && t.approval < 80 ? "text-destructive" : ""}>{fmtPct(t.approval)}</span>} sub={t.votes > 0 ? `${t.votes} votes · bar 80%` : "no votes"} />
            <Kpi label="Reach" value={fmtPct(t.reach)} sub="share of the room that rated" />
            <Kpi label="vs course" value={<CompareBullet value={t.avgScore} reference={courseAvg} width={110} />} sub={courseAvg != null ? `course avg ${fmtScore(courseAvg)}` : "no course average"} />
          </div>

          <ChartCard
            title="Score trend"
            subtitle="Weekly average · grey = the course · ▼ = a week AI feedback was sent"
            legend={[{ label: name, color: "var(--chart-1)" }]}
            table={{
              headers: ["Week", "Score", "Course", "Classes"],
              rows: weeks.map((w, i) => [w.label, fmtScore(w.avgScore), fmtScore(courseWeeks[i]?.avgScore), w.n]),
            }}
          >
            <LineChart
              labels={weeks.map((w) => w.label)}
              series={[{ name, values: weeks.map((w) => w.avgScore) }]}
              reference={{ name: "course", values: courseWeeks.map((w) => w.avgScore) }}
              yDomain={[40, 100]}
              bands={BAND_ZONES}
              markers={markers}
              decimals={0}
              height={220}
            />
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Modules" subtitle="This instructor's module score against the course's module average">
              {ownTopics.length === 0 ? (
                <Empty className="px-0">No module has a course average to compare with yet.</Empty>
              ) : (
                <HBars
                  items={ownTopics.slice(0, 10).map((tp) => ({
                    label: tp.name,
                    value: tp.diff!,
                    sub: `${fmtScore(tp.avgScore)} vs ${fmtScore(tp.ref)} · ${tp.n} ${tp.n === 1 ? "class" : "classes"}`,
                    color: tp.diff! >= 0 ? "var(--chart-1)" : "var(--chart-2)",
                    href: modulesHrefFor?.(tp.key),
                  }))}
                  center={0}
                  format={(v) => v.toFixed(0)}
                />
              )}
            </Section>
            <ChartCard
              title="Monthly approval"
              subtitle="Share who would have this instructor back, against the 80% bar"
              table={{ headers: ["Month", "Approval", "Votes", "Classes"], rows: months.map((m) => [m.label, fmtPct(m.approval), m.votes, m.n]) }}
            >
              {months.filter((m) => m.approval != null).length >= 2 ? (
                <LineChart
                  labels={months.map((m) => m.label)}
                  series={[{ name: "approval", values: months.map((m) => m.approval) }]}
                  threshold={80}
                  thresholdLabel="80% bar"
                  yDomain={[40, 100]}
                  unit="%"
                  decimals={0}
                  height={200}
                />
              ) : (
                <Empty className="px-0">Not enough months with a vote yet.</Empty>
              )}
            </ChartCard>
          </div>

          <Section title="The four boxes" subtitle={voted ? `${voted} classes with a vote · rating 4.55 line × 80% approval bar` : "No votes recorded"}>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {(Object.keys(QUADRANT_META) as Quadrant[]).map((q) => (
                <div key={q} className="surface-inset rounded-lg border p-3">
                  <div className="text-[12px] font-semibold">{QUADRANT_META[q].label}</div>
                  <div className="mt-1 flex items-baseline gap-1.5">
                    <span className={q === "fails" ? "text-destructive text-[20px] leading-none font-semibold" : "text-[20px] leading-none font-semibold"} data-numeric>
                      {boxes[q]}
                    </span>
                    <span className="text-muted-foreground text-[11px]" data-numeric>
                      {voted ? Math.round((boxes[q] / voted) * 100) : 0}%
                    </span>
                  </div>
                  <p className="text-muted-foreground mt-1.5 text-[11px] leading-snug">{QUADRANT_META[q].note}</p>
                </div>
              ))}
            </div>
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Best five" flush>
              <ClassList rows={best} />
            </Section>
            <Section title="Worst five" flush>
              <ClassList rows={worst} />
            </Section>
          </div>

          <Section title="AI feedback" subtitle="Every note sent to this instructor, with the average of the next three classes" flush>
            {feedbackRows.length === 0 ? (
              <Empty>No AI feedback has been sent to this instructor yet.</Empty>
            ) : (
              <DataTable>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Sent</TableHead>
                    <TableHead>Class</TableHead>
                    <TableHead className="text-right">Before</TableHead>
                    <TableHead className="text-right">After</TableHead>
                    <TableHead className="text-right">Change</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {feedbackRows.map((f) => (
                    <TableRow key={f.classId}>
                      <TableNum className="text-muted-foreground text-left">{prettyDate(f.sentAt.slice(0, 10))}</TableNum>
                      <TableCell className="max-w-64 truncate">
                        <Link href={`/feedback/${f.classId}`} className="hover:text-primary font-medium">
                          {f.topic}
                        </Link>
                        <span className="text-muted-foreground block text-[10.5px]">class of {prettyDate(f.date)}</span>
                      </TableCell>
                      <TableNum>
                        {fmtScore(f.before)} <span className="text-muted-foreground text-[10.5px]">({f.nBefore})</span>
                      </TableNum>
                      <TableNum>
                        {fmtScore(f.after)} <span className="text-muted-foreground text-[10.5px]">({f.nAfter})</span>
                      </TableNum>
                      <TableNum>
                        <Delta value={f.before == null || f.after == null ? null : f.after - f.before} />
                      </TableNum>
                    </TableRow>
                  ))}
                </TableBody>
              </DataTable>
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function ClassList({ rows }: { rows: ScoredRating[] }) {
  if (rows.length === 0) return <Empty>No scored classes.</Empty>;
  return (
    <DataTable>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id} className="relative">
            <TableCell className="w-24">
              <ClassScorePill row={r} />
            </TableCell>
            <TableCell className="max-w-56">
              <Link href={drawerHref(r)} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={r.topic}>
                {r.topic || r.session_kind}
              </Link>
            </TableCell>
            <TableCell>
              <KindChip kind={r.session_kind} />
            </TableCell>
            <TableNum className="text-muted-foreground">{r.rating.toFixed(2)}</TableNum>
            <TableNum className="text-muted-foreground">{fmtPct(r.approval_pct)}</TableNum>
            <TableNum className="text-muted-foreground">{prettyDate(r.class_date)}</TableNum>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
