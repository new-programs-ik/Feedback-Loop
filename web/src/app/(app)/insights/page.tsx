import Link from "next/link";
import { Lightbulb, Puzzle, Trophy } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatTile } from "@/components/ui/stat-tile";
import { Badge } from "@/components/ui/badge";
import {
  BandDot, Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow,
} from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { StackedBars } from "@/components/charts/stacked-bars";
import { Histogram } from "@/components/charts/histogram";
import {
  fetchRatings, byMonth, bands, byTopic, bestSmePerTopic, summarize,
} from "@/lib/ratings";
import { GOOD, MIN_VOICES, PARTICIPATION_BAR } from "@/lib/decision";
import { fmtMonth } from "@/components/charts/chart-kit";
import { requireUser } from "@/lib/session";

export const metadata = { title: "Insights" };

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));

const VISION: { title: string; body: string; status: "live" | "building" | "planned" }[] = [
  {
    title: "SME strengths & improvement areas by topic",
    body: "Per-instructor topic records show where each SME shines and where they need targeted coaching — instead of generic feedback.",
    status: "live",
  },
  {
    title: "Modules that rate low across every instructor",
    body: "When a module underperforms no matter who teaches it, the problem is the content, structure or difficulty — not the SME. The module watchlist below detects exactly this.",
    status: "live",
  },
  {
    title: "Rating & engagement patterns across the course journey",
    body: "Do ratings start high and decline in later modules? Where does the drop begin, and is it difficulty, fatigue or design? Needs module-sequence data (cohort schedules) joined to ratings — next data integration.",
    status: "building",
  },
  {
    title: "Best SME–module alignment",
    body: "Historical performance already names the best-known SME per module (table above). Over time this becomes an optimized SME-to-module allocation system.",
    status: "live",
  },
  {
    title: "Learner-level rating analytics",
    body: "With raw learner-level ratings (via the Metabase integration), we can spot consistently dissatisfied learners, what drives it, and who needs intervention — the learner analytics layer.",
    status: "planned",
  },
  {
    title: "SME performance patterns for hiring, demo evaluation & training",
    body: "Train the AI on what our best SMEs do — clarity, examples, pacing, engagement — then score hiring demos against those benchmarks and give existing SMEs the same targeted analysis automatically. The analysis engine that reads classes today is the foundation for this.",
    status: "planned",
  },
];

export default async function InsightsPage() {
  await requireUser();
  // The full recorded history — the study, computed live from the database.
  const rows = await fetchRatings({ from: "2026-01-01", to: new Date().toISOString().slice(0, 10) });
  const total = summarize(rows);
  const months = byMonth(rows);
  const first = months[0];
  const last = months[months.length - 1];

  // Module watchlist: rated low across MULTIPLE instructors -> content-issue candidates.
  const watchlist = byTopic(rows, 4)
    .filter((t) => t.instructors >= 2 && (t.avgRating ?? 5) < GOOD)
    .sort((a, b) => (a.avgRating ?? 5) - (b.avgRating ?? 5))
    .slice(0, 8);
  const bestPairs = bestSmePerTopic(rows, 2).slice(0, 8);

  const above80 = rows.filter((r) => (r.participation_pct ?? 0) >= 80).length;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Insights"
        description={`What ${total.n.toLocaleString()} rated classes since January tell us — computed live, updated with every sync.`}
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-stagger>
        <StatTile label="Classes rated (Jan → today)" value={total.n.toLocaleString()} />
        <StatTile label={`Share below ${GOOD}`} value={`${Math.round((total.badShare ?? 0) * 100)}%`}
                  tone="destructive"
                  note={first?.badShare != null && last?.badShare != null
                    ? `${Math.round(first.badShare * 100)}% in ${fmtMonth(first.month)} → ${Math.round(last.badShare * 100)}% in ${fmtMonth(last.month)}`
                    : undefined} />
        <StatTile label="Typical participation" value={`${Math.round(total.avgParticipation ?? 0)}%`}
                  note="about half the room rates a class — stable all year" />
        <StatTile label="Classes ever reaching 80% participation" value={`${((above80 / Math.max(total.n, 1)) * 100).toFixed(1)}%`}
                  note="why the old 80% rule could never fire" />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title={`Fine vs below ${GOOD}, by month`}
          subtitle="The trend leadership should watch: the share of low-rated classes is climbing"
          legend={[
            { label: `Rated ${GOOD}+`, color: "var(--viz-good)" },
            { label: `Below ${GOOD}`, color: "var(--viz-bad)" },
          ]}
          table={{
            headers: ["Month", `${GOOD}+`, `Below`, "Share"],
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

        <ChartCard
          title="How all ratings spread"
          subtitle={`The ${GOOD} line and the ${PARTICIPATION_BAR}% / ${MIN_VOICES}-voice rule were set from this data — not by guessing`}
          table={{ headers: ["Band", "Classes"], rows: bands(rows).map((b) => [b.label.replace("|", " — "), b.count]) }}
        >
          <Histogram bands={bands(rows)} height={200} />
        </ChartCard>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
          <div className="flex items-start gap-2.5 px-4 pt-4 sm:px-5">
            <span className="bg-warning/15 text-warning flex size-8 shrink-0 items-center justify-center rounded-lg">
              <Puzzle className="size-4" aria-hidden />
            </span>
            <div>
              <h3 className="text-[13px] font-semibold">Module watchlist — likely content issues</h3>
              <p className="text-muted-foreground text-xs">
                Rated below {GOOD} across <b>two or more different SMEs</b> — pointing at the material
                (content, examples, sequencing), not the instructor.
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
                Highest average among SMEs with 3+ classes on the module — the seed of the
                SME-to-module allocation map.
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
            </TableBody>
          </Table>
        </div>
      </div>

      {/* ── the vision ── */}
      <div className="bg-card shadow-soft mt-6 rounded-xl border p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="bg-primary/12 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
            <Lightbulb className="size-4.5" aria-hidden />
          </span>
          <div>
            <h2 className="text-[15px] font-semibold tracking-[-0.01em]">
              Where this goes: the SME &amp; Learner Intelligence System
            </h2>
            <p className="text-muted-foreground mt-0.5 text-[13px]">
              The long-term goal is to move from tracking ratings to a system that decides better —
              SME allocation, content improvement, learner intervention, training, and hiring.
            </p>
          </div>
        </div>
        <ol className="mt-5 grid gap-3 lg:grid-cols-2">
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
        <p className="text-muted-foreground mt-4 text-xs">
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
