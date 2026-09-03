import Link from "next/link";
import { Lightbulb, Puzzle, Scale, TrendingDown, Trophy } from "lucide-react";
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
import { approvalTone } from "@/components/priority-chip";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { ReadingProgress } from "@/components/insights/reading-progress";
import { SectionNav, type InsightSection } from "@/components/insights/section-nav";
import { AccentReveal } from "@/components/insights/accent-reveal";
import { StatStrip } from "@/components/insights/stat-strip";
import { PRINT_SAFE as P } from "@/components/insights/print-safe";
import {
  fetchRatings, byCourse, byMonth, bands, byTopic, bestSmePerTopic, summarize, isBad,
} from "@/lib/ratings";
import {
  APPROVAL_BAR, BORDERLINE, GOOD, MIN_VOICES, PARTICIPATION_BAR, URGENT, WEIGHTS,
} from "@/lib/decision";
import { fmtMonth } from "@/components/charts/chart-kit";
import { requireUser } from "@/lib/session";
import { cn } from "@/lib/utils";

export const metadata = { title: "Insights" };

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));
const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);

/** The study's running order — the navigator, the headings and the anchors all read from here. */
const SECTIONS: InsightSection[] = [
  { id: "participation", n: 1, short: "Participation", title: "Participation tells you how much to trust a score — not whether the class was good" },
  { id: "vote", n: 2, short: "The vote", title: "The vote is not the rating" },
  { id: "trend", n: 3, short: "The trend", title: "The trend leadership should watch" },
  { id: "spread", n: 4, short: "How ratings spread", title: "How all ratings spread" },
  { id: "courses", n: 5, short: "By course", title: "How each course is doing" },
  { id: "content", n: 6, short: "Content vs instructor", title: "Content problems vs instructor problems — the data can tell them apart" },
  { id: "vision", n: 7, short: "Where this goes", title: "Where this goes — the SME & Learner Intelligence System" },
];
const sec = (id: string) => SECTIONS.find((s) => s.id === id)!;

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

/** A numbered part of the study: the anchor the navigator scrolls to and observes. */
function Section({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-28">
      {children}
    </section>
  );
}

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

  // ── the vote: the four corners of the rating × approval plane ───────────────
  const voted = rows.filter((r) => r.approval_pct != null);
  const under = (r: (typeof rows)[number]) => (r.approval_pct ?? 100) < APPROVAL_BAR;
  const fineBoth = voted.filter((r) => !isBad(r) && !under(r)).length;
  const failsBoth = voted.filter((r) => isBad(r) && under(r)).length;
  const hardGood = voted.filter((r) => isBad(r) && !under(r)).length;
  const polite = voted.filter((r) => !isBad(r) && under(r));
  const politeVoiced = polite.filter((r) => (r.num_ratings ?? 0) >= MIN_VOICES).length;
  const badVoted = voted.filter(isBad).length;
  const nobodySaidNo = voted.filter((r) => r.no_votes === 0).length;
  const noVotesInGood = voted.filter((r) => !isBad(r)).reduce((a, r) => a + (r.no_votes ?? 0), 0);
  const noVotesAll = voted.reduce((a, r) => a + (r.no_votes ?? 0), 0);
  const approvalPoints = voted.map(
    (r) => [Number(r.approval_pct), r.rating, isBad(r) || under(r) ? 1 : 0] as [number, number, number],
  );
  const quadrants = [
    { label: "Fine on both", n: fineBoth, note: `Rated ${GOOD}+ and ${APPROVAL_BAR}%+ would have the instructor back — no analysis.`, tone: "good" as const },
    { label: "Fails both", n: failsBoth, note: "Rated low and the room would rather have someone else — the videos concentrate here.", tone: "bad" as const },
    { label: "Hard class, good teacher", n: hardGood, note: "Rated low, instructor approved — analysed, but the vote says where not to look first.", tone: "warn" as const },
    { label: "Polite rating", n: polite.length, note: `Rated ${GOOD}+ yet under the ${APPROVAL_BAR}% bar — an instructor question the rating rule alone never sees.`, tone: "warn" as const },
  ];
  const underShare = (m: (typeof months)[number]) => (m.n ? Math.round((m.underBar / m.n) * 100) : 0);

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
  // The course carrying the largest share of this year's below-GOOD classes (for section 3).
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

  const ratingBands = bands(rows);

  return (
    <>
      <ReadingProgress />
      <div className="mx-auto max-w-4xl xl:grid xl:max-w-6xl xl:grid-cols-[168px_minmax(0,56rem)] xl:justify-center xl:gap-x-10">
        {/* ── editorial header, the report's voice ── */}
        <header className="xl:col-start-2">
          <Reveal className={P}>
            <div className="text-primary mb-2 text-[10.5px] font-bold tracking-[0.14em] uppercase">
              Interview Kickstart · New Programs · live study
            </div>
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] sm:text-[30px]">
              What{" "}
              <span className="text-gradient print:bg-none! print:text-foreground!" data-numeric>
                {total.n.toLocaleString()}
              </span>{" "}
              rated classes actually tell us
            </h1>
            <p className="text-muted-foreground mt-2 max-w-2xl text-[14.5px] leading-relaxed">
              Every live class and test review since January, straight from the ratings sheet — recomputed
              on every sync, so this page is never out of date. <b className="text-foreground">{attended.toLocaleString()}</b>{" "}
              learners sat in a class; <b className="text-foreground">{rated.toLocaleString()}</b> of them rated one
              {total.votes > 0 && total.votes === rated && (
                <> — and every rating came with a vote on whether they would have the instructor back</>
              )}
              {total.votes > 0 && total.votes !== rated && (
                <>
                  , and <b className="text-foreground">{total.votes.toLocaleString()}</b> said whether they would have the instructor back
                </>
              )}
              .
            </p>
          </Reveal>

          {/* stat strip */}
          <StatStrip
            className="mt-5"
            items={[
              { value: total.n, label: "classes rated since January" },
              { value: Math.round((total.badShare ?? 0) * 100), suffix: "%", label: `rated below ${GOOD}`, bad: true },
              { value: total.approval == null ? null : Math.round(total.approval), suffix: "%", label: "would have the instructor back", bad: total.approval != null && total.approval < APPROVAL_BAR },
              { value: Math.round(total.avgParticipation ?? 0), suffix: "%", label: "typical participation — half the room" },
              { value: above80Pct, decimals: 1, suffix: "%", label: "of classes ever reach 80% participation", bad: true },
            ]}
          />
        </header>

        {/* the navigator: left rail on xl, pill row under the topbar below that */}
        <SectionNav sections={SECTIONS} className="xl:col-start-1 xl:row-span-2 xl:row-start-1" />

        <article className="min-w-0 xl:col-start-2">
          {/* ── 1 ── */}
          <Section id="participation">
            <Reveal className={P}>
              <SectionHeader n={1} id="participation-title" title={sec("participation").title} />
              <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
                Well-rated and badly-rated classes are rated at almost the same rate — the two groups sit
                just <b className="text-foreground">{Math.abs(gapPts).toFixed(1)} points apart</b> in average
                participation. And only <b className="text-foreground">{above80} of {total.n.toLocaleString()}</b>{" "}
                classes ever reached 80% — which is why the old 80% rule never fired once. The flat cloud
                below is the whole argument:
              </p>
            </Reveal>
            <Reveal className={P} delay={0.05}>
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
            </Reveal>
            <AccentReveal className="mt-3">
              <Callout tone="ok" icon={Scale} title="What participation decides">
                Fewer than <b>{MIN_VOICES} ratings</b> → watch only, whatever the score · below {GOOD} → the class
                enters the queue · <b>≥ {PARTICIPATION_BAR}%</b> of the room rating → a video analysis, under{" "}
                {PARTICIPATION_BAR}% → a transcript read. Every threshold here was measured, not guessed — and
                section 2 adds the second signal that decides how urgent each case is.
              </Callout>
            </AccentReveal>
          </Section>

          {/* ── 2 ── */}
          <Section id="vote">
            <Reveal className={P}>
              <SectionHeader n={2} id="vote-title" title={sec("vote").title} />
              {voted.length === 0 && (
                <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
                  The ratings form also asks whether the room would have the instructor back. No votes have
                  synced yet — this section fills in once the sheet&apos;s Yes / No columns arrive.
                </p>
              )}
              {voted.length > 0 && (
                <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
                  Every rating form asks a second question: <i>would you want this instructor to take the
                  class again?</i> Across <b className="text-foreground">{voted.length.toLocaleString()}</b> classes
                  with a vote, <b className="text-foreground">{fmtPct(total.approval)}</b> of{" "}
                  {total.votes.toLocaleString()} answers say yes, and in{" "}
                  <b className="text-foreground">{Math.round((nobodySaidNo / voted.length) * 100)}%</b> of classes
                  nobody said no. The two signals move together but do not agree: the rating flags the class,
                  the vote flags the instructor. Of the <b className="text-foreground">{badVoted}</b> classes rated
                  under {GOOD}, <b className="text-foreground">{hardGood} ({badVoted ? Math.round((hardGood / badVoted) * 100) : 0}%)</b>{" "}
                  still cleared the {APPROVAL_BAR}% bar — the room found the class hard but did not blame the
                  teacher. And{" "}
                  {noVotesAll > 0 && (
                    <>
                      <b className="text-foreground">{Math.round((noVotesInGood / noVotesAll) * 100)}%</b>{" "}
                      of every &ldquo;no&rdquo; was cast in a class rated {GOOD} or better —{" "}
                    </>
                  )}
                  <b className="text-foreground">{polite.length}</b> classes were rated fine yet fell under the bar
                  ({politeVoiced} of them with {MIN_VOICES} or more votes). Two different questions, two different answers.
                </p>
              )}
            </Reveal>
            {voted.length > 0 && (
              <>
                <Reveal className={P} delay={0.05}>
                  <ChartCard
                    title="Every class with a vote"
                    subtitle={`Rating against the share who would have the instructor back · the ${GOOD} line and the ${APPROVAL_BAR}% bar cut the cloud into four · the shaded corner fails both; the two thin strips are where the signals disagree`}
                    legend={[
                      { label: "Clears both bars", color: "var(--chart-1)" },
                      { label: "Fails a bar", color: "var(--viz-bad)" },
                    ]}
                  >
                    <ScatterChart
                      points={approvalPoints}
                      threshold={GOOD}
                      bar={APPROVAL_BAR}
                      cornerSide="left"
                      xLabel="share of voters who would have the instructor back"
                      barLabel={`${APPROVAL_BAR}% bar`}
                      lineLabel={`rating ${GOOD} — below this we look`}
                      cornerLabel="fails both bars"
                      ariaLabel="Every class plotted by rating against the share who would have the instructor back. Most sit top-right; the shaded corner fails both bars; the strips beside it are where the two signals disagree."
                    />
                  </ChartCard>
                </Reveal>
                <Stagger className={cn("mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4", P)} step={0.07}>
                  {quadrants.map((q) => (
                    <StaggerItem key={q.label} className={P}>
                     <div className="bg-card shadow-soft hover-lift h-full rounded-xl border p-4">
                      <div className="text-[12.5px] font-semibold">
                        <BandDot tone={q.tone} />
                        {q.label}
                      </div>
                      <div className="mt-1.5 flex items-baseline gap-1.5">
                        <span className={cn("text-[24px] leading-none font-semibold tracking-[-0.02em]", q.tone === "bad" && "text-destructive")} data-numeric>
                          {q.n.toLocaleString()}
                        </span>
                        <span className="text-muted-foreground text-xs" data-numeric>
                          {Math.round((q.n / voted.length) * 100)}% of classes
                        </span>
                      </div>
                      <p className="text-muted-foreground mt-2 text-xs leading-relaxed">{q.note}</p>
                     </div>
                    </StaggerItem>
                  ))}
                </Stagger>
                <AccentReveal className="mt-3">
                  <Callout tone="ok" icon={Scale} title="Rule v2 — two bars decide if, the Health Score decides how urgent and how deep">
                    Rated below <b>{GOOD}</b>, <i>or</i> fewer than <b>{APPROVAL_BAR}%</b> would have the instructor
                    back (either one, with at least {MIN_VOICES} voices) → the class enters the queue. A Class Health
                    Score — rating <b>{Math.round(WEIGHTS.rating * 100)}%</b>, approval vote{" "}
                    <b>{Math.round(WEIGHTS.approval * 100)}%</b>, the instructor&apos;s track record{" "}
                    <b>{Math.round(WEIGHTS.track * 100)}%</b> — then sets the priority: <b>urgent</b> under {URGENT} goes
                    to video whatever the reach, <b>borderline</b> at {BORDERLINE}+ starts with a transcript, and in
                    between the {PARTICIPATION_BAR}% reach bar decides. A weighted score alone could not replace the
                    bars — it would let a liked instructor&apos;s perfect vote buy back a bad rating — so the bars stay
                    hard and the score does the two jobs an average is good at: ordering the{" "}
                    <Link href="/ratings" className="text-primary font-medium hover:underline">queue</Link> and choosing the depth.
                  </Callout>
                </AccentReveal>
              </>
            )}
          </Section>

          {/* ── 3 ── */}
          <Section id="trend">
            <Reveal className={P}>
              <SectionHeader n={3} id="trend-title" title={sec("trend").title} />
            </Reveal>
            {worstMonth && first && last && (
              <AccentReveal className="mb-3">
                <Callout tone="warn" icon={TrendingDown} title="Low-rated classes are climbing">
                  The share of classes rated below {GOOD} has risen from{" "}
                  <b>{Math.round((first.badShare ?? 0) * 100)}% in {fmtMonth(first.month)}</b> to{" "}
                  <b>{Math.round((last.badShare ?? 0) * 100)}% in {fmtMonth(last.month)}</b>
                  {worstMonth.month === last.month
                    ? " — the worst month on record, and the strongest argument for this system existing."
                    : ` (peak: ${Math.round((worstMonth.badShare ?? 0) * 100)}% in ${fmtMonth(worstMonth.month)}).`}
                  {" "}Participation stayed flat all year, so this is a real quality trend — not a change in
                  who fills in ratings.
                  {first.votes > 0 && last.votes > 0 && (
                    <>
                      {" "}The vote moves on the same slope: classes under the {APPROVAL_BAR}% approval bar went from{" "}
                      <b>{underShare(first)}% in {fmtMonth(first.month)}</b> to{" "}
                      <b>{underShare(last)}% in {fmtMonth(last.month)}</b> — the room is not just rating lower; it
                      is more often asking for a different instructor.
                    </>
                  )}
                  {topBadCourse && bad.length > 0 && (
                    <>
                      {" "}And it is concentrated: <b>{topBadCourse.name}</b> carries the largest share of the
                      problem — <b>{topBadCourse.bad} of the {bad.length}</b> classes rated below {GOOD} this
                      year ({Math.round((topBadCourse.bad / bad.length) * 100)}%).
                    </>
                  )}
                </Callout>
              </AccentReveal>
            )}
            <Reveal className={P} delay={0.05}>
              <ChartCard
                title={`Fine vs below ${GOOD}, by month`}
                subtitle="Counts of rated classes · the label is the share below the line"
                legend={[
                  { label: `Rated ${GOOD}+`, color: "var(--viz-good)" },
                  { label: `Below ${GOOD}`, color: "var(--viz-bad)" },
                ]}
                table={{
                  headers: ["Month", `${GOOD}+`, "Below", "Share", "Approval", `Under ${APPROVAL_BAR}%`],
                  rows: months.map((m) => [fmtMonth(m.month), m.n - m.bad, m.bad,
                    m.badShare != null ? `${Math.round(m.badShare * 100)}%` : "—", fmtPct(m.approval), m.underBar]),
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
            </Reveal>
          </Section>

          {/* ── 4 ── */}
          <Section id="spread">
            <Reveal className={P}>
              <SectionHeader n={4} id="spread-title" title={sec("spread").title} />
              <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
                Most classes land at 4.75 or above — <b className="text-foreground">{ratingBands[4]?.count.toLocaleString()}</b>{" "}
                of them. The {GOOD} line separates the healthy middle from the{" "}
                <b className="text-foreground">{bad.length}</b> that need a look.
              </p>
            </Reveal>
            <Reveal className={P} delay={0.05}>
              <ChartCard
                title="Rating bands, worst → best"
                subtitle={`The ${GOOD} line and the ${PARTICIPATION_BAR}% / ${MIN_VOICES}-voice rule were set from this distribution`}
                table={{ headers: ["Band", "Classes"], rows: ratingBands.map((b) => [b.label.replace("|", " — "), b.count]) }}
              >
                <Histogram bands={ratingBands} height={200} />
              </ChartCard>
            </Reveal>
          </Section>

          {/* ── 5 ── */}
          <Section id="courses">
            <Reveal className={P}>
              <SectionHeader n={5} id="courses-title" title={sec("courses").title} />
              <p className="text-muted-foreground mb-3 text-[13.5px] leading-relaxed">
                The trend in section 3 is not spread evenly. Every course with at least{" "}
                <b className="text-foreground">10 rated classes</b>, worst first — the pill is its share of
                classes below {GOOD}, the line is that share month by month, and the vote sits beside the rating.
              </p>
            </Reveal>
            {courseCards.length === 0 ? (
              <p className="text-muted-foreground text-[13px]">
                No course has reached 10 rated classes yet — this view fills in as the sheet grows.
              </p>
            ) : (
              <Stagger className={cn("grid gap-3 sm:grid-cols-2", P)} step={0.06}>
                {courseCards.map((c) => (
                  <StaggerItem key={c.key} className={P}>
                   <div className="bg-card shadow-soft hover-lift h-full rounded-xl border p-4">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="min-w-0 truncate text-[13px] font-semibold" title={c.name}>
                        {c.courseId ? (
                          <Link href={`/course-analytics?course=${c.courseId}`} className="hover:text-primary transition-colors">
                            {c.name}
                          </Link>
                        ) : (
                          c.name
                        )}
                      </h3>
                      <span
                        className={cn(
                          "inline-flex shrink-0 items-center rounded-full px-2 py-px text-[11px] font-semibold",
                          (c.badShare ?? 0) > (total.badShare ?? 0)
                            ? "bg-destructive/10 text-destructive"
                            : "bg-success/10 text-success",
                        )}
                        data-numeric
                      >
                        {Math.round((c.badShare ?? 0) * 100)}% below {GOOD}
                      </span>
                    </div>
                    <p className="text-muted-foreground mt-1 text-xs">
                      <b className="text-foreground font-semibold" data-numeric>{c.n}</b> classes · avg{" "}
                      <b className="text-foreground font-semibold" data-numeric>{fmtAvg(c.avgRating)}</b>
                      {c.approval != null && (
                        <>
                          {" "}·{" "}
                          <BandDot tone={approvalTone(c.approval)} />
                          <b className={cn("font-semibold", c.approval < APPROVAL_BAR ? "text-destructive" : "text-foreground")} data-numeric>
                            {Math.round(c.approval)}%
                          </b>{" "}
                          would have the instructor back
                          {c.underBar > 0 ? ` · ${c.underBar} under ${APPROVAL_BAR}%` : ""}
                        </>
                      )}
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
                  </StaggerItem>
                ))}
              </Stagger>
            )}
          </Section>

          {/* ── 6 ── */}
          <Section id="content">
            <Reveal className={P}>
              <SectionHeader n={6} id="content-title" title={sec("content").title} />
            </Reveal>
            <div className="grid gap-4 lg:grid-cols-2">
              <Reveal className={cn("bg-card shadow-soft overflow-hidden rounded-xl border", P)}>
                <div className="flex items-start gap-2.5 px-4 pt-4 sm:px-5">
                  <span className="bg-warning/15 text-warning flex size-8 shrink-0 items-center justify-center rounded-lg">
                    <Puzzle className="size-4" aria-hidden />
                  </span>
                  <div>
                    <h3 className="text-[13px] font-semibold">Module watchlist — likely content issues</h3>
                    <p className="text-muted-foreground text-xs">
                      Rated below {GOOD} across <b>two or more different SMEs</b> — pointing at the material, not the person.
                      A healthy approval beside a low rating says the same thing.
                    </p>
                  </div>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Module</TableHead>
                      <TableHead className="text-right">Avg</TableHead>
                      <TableHead className="text-right">Approval</TableHead>
                      <TableHead className="text-right">Classes</TableHead>
                      <TableHead className="text-right">SMEs</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {watchlist.map((t) => (
                      <TableRow key={t.topic}>
                        <TableCell className="max-w-60 truncate font-medium">{t.topic}</TableCell>
                        <TableNum><BandDot tone="bad" />{fmtAvg(t.avgRating)}</TableNum>
                        <TableNum className={t.approval != null && t.approval < APPROVAL_BAR ? "text-destructive font-semibold" : ""}>
                          {t.approval != null ? <><BandDot tone={approvalTone(t.approval)} />{Math.round(t.approval)}%</> : <span className="text-muted-foreground">—</span>}
                        </TableNum>
                        <TableNum className="text-muted-foreground">{t.n}</TableNum>
                        <TableNum className="text-muted-foreground">{t.instructors}</TableNum>
                      </TableRow>
                    ))}
                    {watchlist.length === 0 && (
                      <TableRow><TableCell className="text-muted-foreground">No multi-SME low modules found — a good sign.</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </Reveal>

              <Reveal className={cn("bg-card shadow-soft overflow-hidden rounded-xl border", P)} delay={0.08}>
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
                          <Link href={`/instructor-analytics?sme=${encodeURIComponent(p.instructor)}`} className="hover:text-primary transition-colors">
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
              </Reveal>
            </div>
          </Section>

          {/* ── 7 ── */}
          <Section id="vision">
            <Reveal className={P}>
              <SectionHeader n={7} id="vision-title" title={sec("vision").title} />
            </Reveal>
            <Reveal className={cn("bg-card shadow-soft rounded-xl border p-5 sm:p-6", P)} delay={0.05}>
              <div className="flex items-start gap-3">
                <span className="bg-primary/12 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                  <Lightbulb className="size-4.5" aria-hidden />
                </span>
                <p className="text-muted-foreground text-[13px] leading-relaxed">
                  The long-term goal is to move from tracking ratings to a system that decides better —
                  SME allocation, content improvement, learner intervention, training, and hiring.
                </p>
              </div>
              <ol className="mt-4 grid gap-3 lg:grid-cols-2" data-stagger>
                {VISION.map((v, i) => (
                  <li key={v.title} className="surface-inset hover-lift rounded-lg border p-3.5">
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
            </Reveal>
          </Section>
        </article>
      </div>
    </>
  );
}
