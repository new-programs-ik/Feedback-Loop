import Link from "next/link";
import { Lightbulb, Puzzle, Trophy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Callout, SectionHeader } from "@/components/ui/callout";
import {
  BandDot, Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow,
} from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { StackedBars } from "@/components/charts/stacked-bars";
import { Histogram } from "@/components/charts/histogram";
import { ScatterChart } from "@/components/charts/scatter-chart";
import { Sparkline } from "@/components/charts/sparkline";
import {
  fetchRatings, byCourse, byMonth, bands, byTopic, bestSmePerTopic, summarize, isBad,
} from "@/lib/ratings";
import { GOOD, MIN_VOICES, PARTICIPATION_BAR } from "@/lib/decision";
import { fmtMonth } from "@/components/charts/chart-kit";
import { requireUser } from "@/lib/session";

export const metadata = { title: "Insights" };

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));

const VISION: { title: string; body: string; status: "live" | "building" | "planned" }[] = [
  { title: "SME strengths & improvement areas by topic",
    body: "Per-instructor topic records show where each SME shines and where they need targeted coaching — instead of generic feedback.",
    status: "live" },
  { title: "Modules that rate low across every instructor",
    body: "When a module underperforms no matter who teaches it, the problem is the content, structure or difficulty — not the SME. The module watchlist detects exactly this.",
    status: "live" },
  { title: "Rating & engagement patterns across the course journey",
    body: "Do ratings start high and decline in later modules? Where does the drop begin, and is it difficulty, fatigue or design? Needs module-sequence data (cohort schedules) joined to ratings — next data integration.",
    status: "building" },
  { title: "Best SME–module alignment",
    body: "Historical performance already names the best-known SME per module. Over time this becomes an optimized SME-to-module allocation system.",
    status: "live" },
  { title: "Learner-level rating analytics",
    body: "With raw learner-level ratings (via the Metabase integration), we can spot consistently dissatisfied learners, what drives it, and who needs intervention — the learner analytics layer.",
    status: "planned" },
  { title: "SME performance patterns for hiring, demo evaluation & training",
    body: "Train the AI on what our best SMEs do — clarity, examples, pacing, engagement — then score hiring demos against those benchmarks and give existing SMEs the same targeted analysis automatically. The analysis engine that reads classes today is the foundation.",
    status: "planned" },
];

export default async function InsightsPage() {
  await requireUser();
  const today = new Date().toISOString().slice(0, 10);
  const rows = await fetchRatings({ from: "2026-01-01", to: today });
  const total = summarize(rows);
  const months = byMonth(rows);
  const first = months[0];
  const last = months[months.length - 1];

  // ── computed narrative (the report habit: numbers live inside sentences) ────
  const good = rows.filter((r) => !isBad(r));
  const bad = rows.filter(isBad);
  const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  const partOf = (list: typeof rows) =>
    avg(list.map((r) => r.participation_pct).filter((v): v is number => v != null).map(Number));
  const gapPts = partOf(good) - partOf(bad);
  const above80 = rows.filter((r) => (r.participation_pct ?? 0) >= 80).length;
  const above80Pct = (above80 / Math.max(total.n, 1)) * 100;
  const worstMonth = [...months].sort((a, b) => (b.badShare ?? 0) - (a.badShare ?? 0))[0];
  const attended = rows.reduce((a, r) => a + (r.attended ?? 0), 0);
  const rated = rows.reduce((a, r) => a + (r.num_ratings ?? 0), 0);

  const watchlist = byTopic(rows, 4)
    .filter((t) => t.instructors >= 2 && (t.avgRating ?? 5) < GOOD)
    .sort((a, b) => (a.avgRating ?? 5) - (b.avgRating ?? 5))
    .slice(0, 8);
  const bestPairs = bestSmePerTopic(rows, 2).slice(0, 8);
  const scatterPoints = rows
    .filter((r) => r.participation_pct != null)
    .map((r) => [Number(r.participation_pct), r.rating, isBad(r) ? 1 : 0] as [number, number, number]);

  // ── the course dimension ────────────────────────────────────────────────────
  const courseAgg = byCourse(rows);
  // The course carrying the largest share of this year's below-GOOD classes (for section 2).
  const topBadCourse = courseAgg.filter((c) => c.bad > 0).sort((a, b) => b.bad - a.bad)[0];
  // Small multiples: every course with a readable sample, worst bad-share first. Each card
  // carries ONE sentence chosen by its own monthly data.
  const courseCards = courseAgg
    .filter((c) => c.n >= 10)
    .sort((a, b) => (b.badShare ?? 0) - (a.badShare ?? 0))
    .map((c) => {
      const monthly = byMonth(c.rows);
      const spark = monthly.map((m) => Math.round((m.badShare ?? 0) * 100));
      // Worst month; ties break toward the latest month so a repeat-of-the-peak reads as worsening.
      const worst = [...monthly].sort(
        (a, b) => (b.badShare ?? 0) - (a.badShare ?? 0) || b.month.localeCompare(a.month),
      )[0];
      const latest = monthly[monthly.length - 1];
      const worstPct = worst ? Math.round((worst.badShare ?? 0) * 100) : 0;
      const latestPct = latest ? Math.round((latest.badShare ?? 0) * 100) : 0;
      const worsening =
        monthly.length >= 2 && !!worst && !!latest && worstPct > 10 && worst.month === latest.month;
      const sentence =
        !worst || monthly.length < 2
          ? "Too few months on record to read a trend yet."
          : worstPct <= 10
            ? `Healthy all year — no month above 10% below ${GOOD}.`
            : worsening
              ? `Worsening — the latest month, ${fmtMonth(worst.month)}, is its worst yet at ${worstPct}%.`
              : `Peaked at ${worstPct}% in ${fmtMonth(worst.month)}; ${latestPct}% in the latest month.`;
      return { ...c, spark, worsening, sentence };
    });

  return (
    <div className="animate-in-up mx-auto max-w-4xl">
      {/* ── editorial header, the report's voice ── */}
      <div className="text-primary mb-2 text-[10.5px] font-bold tracking-[0.14em] uppercase">
        Interview Kickstart · New Programs · live study
      </div>
      <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em]">
        What {total.n.toLocaleString()} rated classes actually tell us
      </h1>
      <p className="text-muted-foreground mt-2 max-w-2xl text-[14.5px] leading-relaxed">
        Every live class and test review since January, straight from the ratings sheet — recomputed
        on every sync, so this page is never out of date. <b className="text-foreground">{attended.toLocaleString()}</b>{" "}
        learners sat in a class; <b className="text-foreground">{rated.toLocaleString()}</b> of them rated one.
      </p>

      {/* stat strip */}
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-stagger>
        {[
          { v: total.n.toLocaleString(), l: "classes rated since January" },
          { v: `${Math.round((total.badShare ?? 0) * 100)}%`, l: `rated below ${GOOD}`, bad: true },
          { v: `${Math.round(total.avgParticipation ?? 0)}%`, l: "typical participation — half the room" },
          { v: `${above80Pct.toFixed(1)}%`, l: "of classes ever reach 80% participation", bad: true },
        ].map((s) => (
          <div key={s.l} className="bg-card shadow-soft rounded-xl border p-4">
            <div className={`text-[26px] leading-none font-semibold tracking-[-0.02em] ${s.bad ? "text-destructive" : ""}`} data-numeric>
              {s.v}
            </div>
            <div className="text-muted-foreground mt-1.5 text-xs">{s.l}</div>
          </div>
        ))}
      </div>

      <SectionHeader n={1} title="Participation tells you how much to trust a score — not whether the class was good" />
      <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
        Well-rated and badly-rated classes are rated at almost the same rate — the two groups sit
        just <b className="text-foreground">{Math.abs(gapPts).toFixed(1)} points apart</b> in average
        participation. And only <b className="text-foreground">{above80} of {total.n.toLocaleString()}</b>{" "}
        classes ever reached 80% — which is why the old 80% rule never fired once. The flat cloud
        below is the whole argument:
      </p>
      <ChartCard
        title="Every class since January"
        subtitle={`Rating against participation · the shaded corner — below ${GOOD} with a representative sample — is what earns a video analysis`}
        legend={[
          { label: `Rated ${GOOD}+`, color: "var(--chart-1)" },
          { label: `Below ${GOOD}`, color: "var(--viz-bad)" },
        ]}
      >
        <ScatterChart points={scatterPoints} threshold={GOOD} bar={PARTICIPATION_BAR} />
      </ChartCard>
      <Callout tone="ok" title="The rule this data produced" className="mt-3">
        Rating <b>{GOOD}+</b> → no analysis · fewer than <b>{MIN_VOICES} ratings</b> → watch only ·
        below {GOOD} with <b>≥ {PARTICIPATION_BAR}%</b> of the room rating → video analysis · under{" "}
        {PARTICIPATION_BAR}% → transcript · any escalation → video. Every threshold on this page was
        measured, not guessed — and the app&apos;s <Link href="/ratings" className="text-primary font-medium">Needs-analysis queue</Link>{" "}
        applies it automatically.
      </Callout>

      <SectionHeader n={2} title="The trend leadership should watch" />
      {worstMonth && first && last && (
        <Callout tone="warn" title="Low-rated classes are climbing" className="mb-3">
          The share of classes rated below {GOOD} has risen from{" "}
          <b>{Math.round((first.badShare ?? 0) * 100)}% in {fmtMonth(first.month)}</b> to{" "}
          <b>{Math.round((last.badShare ?? 0) * 100)}% in {fmtMonth(last.month)}</b>
          {worstMonth.month === last.month
            ? " — the worst month on record, and the strongest argument for this system existing."
            : ` (peak: ${Math.round((worstMonth.badShare ?? 0) * 100)}% in ${fmtMonth(worstMonth.month)}).`}
          {" "}Participation stayed flat all year, so this is a real quality trend — not a change in
          who fills in ratings.
          {topBadCourse && bad.length > 0 && (
            <>
              {" "}And it is concentrated: <b>{topBadCourse.name}</b> carries the largest share of the
              problem — <b>{topBadCourse.bad} of the {bad.length}</b> classes rated below {GOOD} this
              year ({Math.round((topBadCourse.bad / bad.length) * 100)}%).
            </>
          )}
        </Callout>
      )}
      <ChartCard
        title={`Fine vs below ${GOOD}, by month`}
        subtitle="Counts of rated classes · the label is the share below the line"
        legend={[
          { label: `Rated ${GOOD}+`, color: "var(--viz-good)" },
          { label: `Below ${GOOD}`, color: "var(--viz-bad)" },
        ]}
        table={{
          headers: ["Month", `${GOOD}+`, "Below", "Share"],
          rows: months.map((m) => [fmtMonth(m.month), m.n - m.bad, m.bad,
            m.badShare != null ? `${Math.round(m.badShare * 100)}%` : "—"]),
        }}
      >
        <StackedBars
          labels={months.map((m) => fmtMonth(m.month))}
          height={200}
          segments={[
            { name: `Rated ${GOOD}+`, color: "var(--viz-good)" },
            { name: `Below ${GOOD}`, color: "var(--viz-bad)" },
          ]}
          values={months.map((m) => [m.n - m.bad, m.bad])}
          topLabels={months.map((m) => (m.badShare != null ? `${Math.round(m.badShare * 100)}%` : null))}
        />
      </ChartCard>

      <SectionHeader n={3} title="How all ratings spread" />
      <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
        Most classes land at 4.75 or above — <b className="text-foreground">{bands(rows)[4]?.count.toLocaleString()}</b>{" "}
        of them. The {GOOD} line separates the healthy middle from the{" "}
        <b className="text-foreground">{bad.length}</b> that need a look.
      </p>
      <ChartCard
        title="Rating bands, worst → best"
        subtitle={`The ${GOOD} line and the ${PARTICIPATION_BAR}% / ${MIN_VOICES}-voice rule were set from this distribution`}
        table={{ headers: ["Band", "Classes"], rows: bands(rows).map((b) => [b.label.replace("|", " — "), b.count]) }}
      >
        <Histogram bands={bands(rows)} height={200} />
      </ChartCard>

      <SectionHeader n={4} title="How each course is doing" />
      <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
        The trend in section 2 is not spread evenly. Every course with at least{" "}
        <b className="text-foreground">10 rated classes</b>, worst first — the pill is its share of
        classes below {GOOD}, the line is that share month by month.
      </p>
      {courseCards.length === 0 ? (
        <p className="text-muted-foreground text-[13px]">
          No course has reached 10 rated classes yet — this view fills in as the sheet grows.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2" data-stagger>
          {courseCards.map((c) => (
            <div key={c.key} className="bg-card shadow-soft rounded-xl border p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="min-w-0 truncate text-[13px] font-semibold" title={c.name}>
                  {c.courseId ? (
                    <Link href={`/course-analytics?course=${c.courseId}`} className="hover:text-primary">
                      {c.name}
                    </Link>
                  ) : (
                    c.name
                  )}
                </h3>
                <span
                  className={`inline-flex shrink-0 items-center rounded-full px-2 py-px text-[11px] font-semibold ${
                    (c.badShare ?? 0) > (total.badShare ?? 0)
                      ? "bg-destructive/10 text-destructive"
                      : "bg-success/10 text-success"
                  }`}
                  data-numeric
                >
                  {Math.round((c.badShare ?? 0) * 100)}% below {GOOD}
                </span>
              </div>
              <p className="text-muted-foreground mt-1 text-xs">
                <b className="text-foreground font-semibold" data-numeric>{c.n}</b> classes · avg{" "}
                <b className="text-foreground font-semibold" data-numeric>{fmtAvg(c.avgRating)}</b>
              </p>
              {c.spark.length >= 2 && (
                <div className="mt-2.5 flex items-center gap-2">
                  <Sparkline
                    values={c.spark}
                    width={110}
                    height={26}
                    accent={c.worsening ? "var(--viz-bad)" : "var(--chart-1)"}
                  />
                  <span className="text-muted-foreground text-[10.5px]">
                    % below {GOOD}, by month
                  </span>
                </div>
              )}
              <p className="text-muted-foreground mt-2 text-xs leading-relaxed">{c.sentence}</p>
            </div>
          ))}
        </div>
      )}

      <SectionHeader n={5} title="Content problems vs instructor problems — the data can tell them apart" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
          <div className="flex items-start gap-2.5 px-4 pt-4 sm:px-5">
            <span className="bg-warning/15 text-warning flex size-8 shrink-0 items-center justify-center rounded-lg">
              <Puzzle className="size-4" aria-hidden />
            </span>
            <div>
              <h3 className="text-[13px] font-semibold">Module watchlist — likely content issues</h3>
              <p className="text-muted-foreground text-xs">
                Rated below {GOOD} across <b>two or more different SMEs</b> — pointing at the material, not the person.
              </p>
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Module</TableHead>
                <TableHead className="text-right">Avg</TableHead>
                <TableHead className="text-right">Classes</TableHead>
                <TableHead className="text-right">SMEs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {watchlist.map((t) => (
                <TableRow key={t.topic}>
                  <TableCell className="max-w-60 truncate font-medium">{t.topic}</TableCell>
                  <TableNum><BandDot tone="bad" />{fmtAvg(t.avgRating)}</TableNum>
                  <TableNum className="text-muted-foreground">{t.n}</TableNum>
                  <TableNum className="text-muted-foreground">{t.instructors}</TableNum>
                </TableRow>
              ))}
              {watchlist.length === 0 && (
                <TableRow><TableCell className="text-muted-foreground">No multi-SME low modules found — a good sign.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
          <div className="flex items-start gap-2.5 px-4 pt-4 sm:px-5">
            <span className="bg-success/15 text-success flex size-8 shrink-0 items-center justify-center rounded-lg">
              <Trophy className="size-4" aria-hidden />
            </span>
            <div>
              <h3 className="text-[13px] font-semibold">Best-known SME per module</h3>
              <p className="text-muted-foreground text-xs">
                Highest average among SMEs with repeat classes on the module — the seed of the allocation map.
              </p>
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Module</TableHead>
                <TableHead>Best SME</TableHead>
                <TableHead className="text-right">Avg</TableHead>
                <TableHead className="text-right">Of</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bestPairs.map((p) => (
                <TableRow key={p.topic}>
                  <TableCell className="max-w-52 truncate font-medium">{p.topic}</TableCell>
                  <TableCell className="max-w-40 truncate">
                    <Link href={`/instructor-analytics?sme=${encodeURIComponent(p.instructor)}`} className="hover:text-primary">
                      {p.instructor}
                    </Link>
                  </TableCell>
                  <TableNum><BandDot tone="good" />{p.avgRating.toFixed(2)}</TableNum>
                  <TableNum className="text-muted-foreground">{p.contenders} SMEs</TableNum>
                </TableRow>
              ))}
              {bestPairs.length === 0 && (
                <TableRow><TableCell className="text-muted-foreground">Needs more repeat SME-module pairs.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <SectionHeader n={6} title="Where this goes — the SME & Learner Intelligence System" />
      <div className="bg-card shadow-soft rounded-xl border p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="bg-primary/12 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
            <Lightbulb className="size-4.5" aria-hidden />
          </span>
          <p className="text-muted-foreground text-[13px] leading-relaxed">
            The long-term goal is to move from tracking ratings to a system that decides better —
            SME allocation, content improvement, learner intervention, training, and hiring.
          </p>
        </div>
        <ol className="mt-4 grid gap-3 lg:grid-cols-2">
          {VISION.map((v, i) => (
            <li key={v.title} className="surface-inset rounded-lg border p-3.5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[13px] font-semibold">
                  <span className="text-muted-foreground mr-1.5" data-numeric>{i + 1}.</span>
                  {v.title}
                </p>
                <Badge
                  variant={v.status === "live" ? "success" : v.status === "building" ? "warning" : "secondary"}
                  className="shrink-0 capitalize"
                >
                  {v.status}
                </Badge>
              </div>
              <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">{v.body}</p>
            </li>
          ))}
        </ol>
        <p className="text-muted-foreground mt-4 text-xs leading-relaxed">
          The questions this system will answer: who is the best SME for each topic · where does each
          SME need improvement · which modules need content work · where in the journey do ratings
          and attendance start declining · which learners are consistently dissatisfied and why ·
          what makes our highest-performing SMEs different — and how to use that for hiring,
          evaluation, training and allocation.
        </p>
      </div>
    </div>
  );
}
