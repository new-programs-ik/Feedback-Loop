import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight, Lightbulb, Puzzle, Scale, TrendingDown, TrendingUp, Users } from "lucide-react";
import { createClient } from "@/lib/supabase/server";
import { getActiveConfig } from "@/lib/scoring";
import { BAND_META, BAND_ORDER, DEFAULT_CONFIG, type ScoringConfig } from "@/lib/sentiment";
import { hrefIn } from "@/lib/workspace-shared";
import {
  byCourse,
  byTopic,
  fetchScored,
  fmtAvg,
  fmtPct,
  fmtScore,
  mean,
  parseCohortText,
  plural,
  prettyDate,
  QUADRANT_META,
  quadrantOf,
  scoreSummary,
  today,
  type Quadrant,
  type ScoredRating,
} from "@/lib/analytics";
import { driftByMonth, slices, studyMeasures, studyWindow, trustByVotes, type BandRisk, type StudyMeasures } from "@/lib/study";
import { Badge } from "@/components/ui/badge";
import { Callout, SectionHeader } from "@/components/ui/callout";
import { BandDot, Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { StackedBars } from "@/components/charts/stacked-bars";
import { ScatterChart } from "@/components/charts/scatter-chart";
import { HBars } from "@/components/charts/h-bars";
import { Empty, Kpi } from "@/components/analytics/ui";
import { AvgScorePill } from "@/components/analytics/score";
import { SectionNav, type InsightSection } from "@/components/insights/section-nav";
import { AccentReveal } from "@/components/insights/accent-reveal";
import { FiveNumbers, type StudyCell } from "@/components/insights/five-numbers";
import { RiskBars } from "@/components/insights/risk-bars";
import { DriftCard } from "@/components/insights/drift-card";
import { CourseTable, type CourseRow } from "@/components/insights/course-table";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Insights" };

/** The study's running order — the navigator, the headings and the anchors all read from here. */
const SECTIONS: InsightSection[] = [
  { id: "right", n: 1, short: "Is the score right?", title: "Is the score right? The validation study, run live" },
  { id: "predict", n: 2, short: "The next class", title: "Does the band predict the next class?" },
  { id: "voices", n: 3, short: "Voices", title: "How many voices before a band is firm" },
  { id: "vote", n: 4, short: "Instructor approval", title: "Instructor approval is not the rating" },
  { id: "trend", n: 5, short: "The trend", title: "The trend leadership should watch" },
  { id: "courses", n: 6, short: "By course", title: "By course" },
  { id: "content", n: 7, short: "Content vs delivery", title: "Content vs delivery — the data can tell them apart" },
  { id: "fair", n: 8, short: "Fair to everyone?", title: "Fair to everyone?" },
  { id: "vision", n: 9, short: "Where this goes", title: "Where this goes" },
];
const sec = (id: string) => SECTIONS.find((s) => s.id === id)!;

/** The offline validation the VP one-pager quotes (analysis/out/scoring_results.json). */
const STUDY_LABEL = "Study · Jan–Aug 2026 · 2,784 classes";
const STUDY: Record<"flips" | "badAbove" | "comfort" | "load" | "risk", StudyCell> = {
  flips: { value: "39% → 37%", note: "original → recommended", tone: "muted" },
  badAbove: { value: "38 of 199 → 0 of 179", note: "original → recommended", tone: "muted" },
  comfort: { value: "249 → 0", note: "firm bands · the recommended left 11 provisional", tone: "muted" },
  load: { value: "7.1 → 11.8", note: "4.6 video · 7.2 transcript a week", tone: "muted" },
  risk: { value: "41% / 14% → 45% / 11%", note: "Bad / Excellent", tone: "muted" },
};

const VISION: { title: string; body: string; status: "live" | "waiting" | "planned" }[] = [
  { title: "Course workspaces", body: "One workspace per course — overview, classes, queue, cohorts, modules, instructors, reports — and the team level above them.", status: "live" },
  { title: "The score everywhere", body: "Every class, instructor, module, cohort and course carries the same 0–100 Class Sentiment Score and its band, with the four inputs one hover away.", status: "live" },
  { title: "Instructor identity", body: "Spelling variants and aliases merged, so an instructor's record is one record and a track record means something.", status: "live" },
  { title: "Ownership", body: "Course members and roles: each course's PM owns its queue; leadership sees every course at once.", status: "live" },
  { title: "Scoring versions", body: "The score's settings are versioned rows: preview a change on real classes, publish with a note, roll back in one click — and this page re-validates whatever is live.", status: "live" },
  { title: "Cohort journeys", body: "Week by week, each cohort's score against the median journey — where the drop begins, and whether it is difficulty, fatigue or design.", status: "live" },
  { title: "Module hot-spots", body: "Modules that rate low under every instructor (content) told apart from modules that rate low under one (delivery), with the best-known instructor per module.", status: "live" },
  { title: "Learner layer", body: "Learner-level ratings through the Metabase feed: who is consistently dissatisfied, what drives it, who needs a word — the schema is ready, the feed is not.", status: "waiting" },
  { title: "Weekly digest and PDF", body: "A Monday digest per course and a printable PDF of this study and each course report, so the numbers travel without a login.", status: "planned" },
  { title: "Instructor patterns for hiring and training", body: "What the best instructors do — clarity, examples, pacing — measured from the analyses, then used to score demos and coach the rest.", status: "planned" },
];
const STATUS_LABEL = { live: "Live", waiting: "Waiting on data", planned: "Planned" } as const;

// ── data ──────────────────────────────────────────────────────────────────────
type WhatIf = {
  n: number;
  weeks: number;
  analyses_per_week: number;
  videos_per_week: number;
  transcripts_per_week: number;
  flip_share: number;
  flip_count: number;
  banded: number;
};

/** The database's own answer for a configuration over the window (scoring_whatif_summary). */
async function whatIf(cfg: ScoringConfig, from: string, to: string): Promise<WhatIf | null> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.rpc("scoring_whatif_summary", { p_config: cfg, p_from: from, p_to: to });
    if (error || !data || typeof data !== "object") return null;
    const d = data as Record<string, unknown>;
    const n = (k: string) => Number(d[k] ?? 0) || 0;
    return {
      n: n("n"),
      weeks: n("weeks"),
      analyses_per_week: n("analyses_per_week"),
      videos_per_week: n("videos_per_week"),
      transcripts_per_week: n("transcripts_per_week"),
      flip_share: n("flip_share"),
      flip_count: n("flip_count"),
      banded: n("banded"),
    };
  } catch {
    return null;
  }
}

type Version = { version: number; name: string; config: ScoringConfig };

/** Version 1 as stored — the manager's original; the built-in copy when the row is missing. */
async function loadVersionOne(): Promise<Version> {
  const fallback: Version = { version: 1, name: DEFAULT_CONFIG.name ?? "Manager's original", config: DEFAULT_CONFIG };
  try {
    const supabase = await createClient();
    const { data } = await supabase.from("scoring_configs").select("version, name, config").eq("version", 1).maybeSingle();
    const row = data as { name?: string; config?: unknown } | null;
    const cfg = row?.config;
    if (cfg && typeof cfg === "object" && "rating" in cfg && "weights" in cfg && "bands" in cfg && "actions" in cfg) {
      return { version: 1, name: String(row?.name ?? fallback.name), config: cfg as ScoringConfig };
    }
  } catch {
    /* the table is not there yet — the built-in copy is the same rule */
  }
  return fallback;
}

// ── small helpers ─────────────────────────────────────────────────────────────
const fmt1 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));
const pctText = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
const riskText = (b: BandRisk) => (b.lowPct == null ? "too few" : `${Math.round(b.lowPct)}%`);
const bandOf = (m: StudyMeasures, band: BandRisk["band"]) => m.risk.bands.find((b) => b.band === band)!;

function Section({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-28 print:break-inside-avoid">
      {children}
    </section>
  );
}

function Lede({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-muted-foreground mb-3 text-[13.5px] leading-relaxed [&_b]:text-foreground [&_b]:font-semibold", className)}>{children}</p>;
}

const CARD = "bg-card shadow-soft overflow-hidden rounded-xl border";
const QUADRANT_TONE: Record<Quadrant, "good" | "warn" | "bad"> = { fine: "good", polite: "warn", hard: "warn", fails: "bad" };

export default async function InsightsPage() {
  const win = studyWindow(today());
  const [active, v1] = await Promise.all([getActiveConfig(), loadVersionOne()]);
  const [scored, whatV1, whatActive] = await Promise.all([
    fetchScored({ from: win.from, to: win.to }),
    whatIf(v1.config, win.from, win.to),
    whatIf(active.config, win.from, win.to),
  ]);
  // The cohort text says which region a class ran for — the one slice the row itself lacks.
  const rows: (ScoredRating & { region: string | null })[] = scored.map((r) => ({ ...r, region: parseCohortText(r.cohort_text)[0]?.region ?? null }));

  const total = scoreSummary(rows);
  const attended = rows.reduce((a, r) => a + (r.attended ?? 0), 0);
  const rated = rows.reduce((a, r) => a + (r.num_ratings ?? 0), 0);
  const activeVersion = active.version ?? 1;
  const activeIsV1 = activeVersion === 1;
  const mv = active.config.min_votes ?? { band: 0, action: 0 };
  const minBand = Number(mv.band ?? 0) || 0;
  const minAction = Number(mv.action ?? 0) || 0;
  const caps = active.config.caps ?? { rating_line: null, approval_bar: null };
  const hasCaps = caps.rating_line != null || caps.approval_bar != null;

  // ── 1. the five numbers ──
  const mV1 = studyMeasures(rows, v1.config);
  const mAct = activeIsV1 ? mV1 : studyMeasures(rows, active.config);
  const flipCell = (w: WhatIf | null): StudyCell =>
    w ? { value: pctText(w.flip_share * 100), note: `${w.flip_count.toLocaleString()} of ${w.n.toLocaleString()} classes` } : { value: "—", note: "database function unavailable", tone: "muted" };
  const loadCell = (w: WhatIf | null): StudyCell =>
    w ? { value: fmt1(w.analyses_per_week), note: `${fmt1(w.videos_per_week)} video · ${fmt1(w.transcripts_per_week)} transcript` } : { value: "—", note: "database function unavailable", tone: "muted" };
  const badCell = (m: StudyMeasures): StudyCell => ({
    value: `${m.badAbove.count.toLocaleString()} of ${m.badAbove.bad.toLocaleString()}`,
    note: m.badAbove.bad ? `${pctText(m.badAbove.sharePct)} of the Bad band` : "no Bad classes",
    tone: m.badAbove.count === 0 ? "good" : "bad",
  });
  const comfortCell = (m: StudyMeasures): StudyCell => ({
    value: m.comfort.firm.toLocaleString(),
    note: `of ${m.comfort.voiced.toLocaleString()} with 5+ votes${m.comfort.provisional ? ` · +${m.comfort.provisional} provisional, watched` : ""}`,
    tone: m.comfort.firm === 0 ? "good" : "bad",
  });
  const riskCell = (m: StudyMeasures): StudyCell => {
    const bad = bandOf(m, "bad");
    const exc = bandOf(m, "excellent");
    return { value: `${riskText(bad)} / ${riskText(exc)}`, note: `${bad.n.toLocaleString()} · ${exc.n.toLocaleString()} pairs` };
  };
  const fiveRows = [
    { key: "flips", label: "Band flips if one learner answers differently", hint: "Share of classes whose band changes if one yes becomes a no, or one rater gives a point less.", v1: flipCell(whatV1), active: flipCell(whatActive), study: STUDY.flips },
    { key: "badAbove", label: "Bad classes actually rated 4.55+", hint: "Classes the band calls Bad although the room rated them on or above the line.", v1: badCell(mV1), active: badCell(mAct), study: STUDY.badAbove },
    { key: "comfort", label: "Low classes shown Good or Excellent", hint: "Rated under 4.55, or under 80% approval, with 5+ votes — yet a firm Good or Excellent band.", v1: comfortCell(mV1), active: comfortCell(mAct), study: STUDY.comfort },
    { key: "load", label: "Analyses a week", hint: "Videos plus transcript reads the band rule sends to the queue, averaged over the window.", v1: loadCell(whatV1), active: loadCell(whatActive), study: STUDY.load },
    { key: "risk", label: "Next-class risk, Bad / Excellent", hint: "How often the same instructor's next class is low, after a Bad class and after an Excellent one.", v1: riskCell(mV1), active: riskCell(mAct), study: STUDY.risk },
  ];
  const badV1 = bandOf(mV1, "bad");
  const excV1 = bandOf(mV1, "excellent");
  const badAct = bandOf(mAct, "bad");
  const excAct = bandOf(mAct, "excellent");
  const ratio = badAct.lowPct != null && excAct.lowPct ? badAct.lowPct / excAct.lowPct : null;

  // ── 3. voices ──
  const trust = trustByVotes(rows);
  const declined = trust.noBand + trust.provisional;

  // ── 4. the vote ──
  const voted = rows.filter((r) => r.approval_pct != null);
  const quadrants = (["fine", "fails", "hard", "polite"] as Quadrant[]).map((q) => ({ q, n: voted.filter((r) => quadrantOf(r) === q).length }));
  const nobodySaidNo = voted.filter((r) => r.no_votes === 0).length;
  const approvalPoints = voted.map((r) => [Number(r.approval_pct), r.rating, quadrantOf(r) === "fine" ? 0 : 1] as [number, number, number]);
  const approvalLabels = voted.map((r) => `${r.course_name ?? r.course_label} · ${r.topic.trim() || r.session_kind} · ${prettyDate(r.class_date)}`);

  // ── 5. the trend ──
  const months = driftByMonth(rows);
  const first = months[0];
  const last = months[months.length - 1];
  const peak = [...months].sort((a, b) => (b.underLinePct ?? 0) - (a.underLinePct ?? 0))[0];
  const underShift = first && last ? (last.underLinePct ?? 0) - (first.underLinePct ?? 0) : 0;
  const reachShift = first && last && first.avgReach != null && last.avgReach != null ? last.avgReach - first.avgReach : null;
  const trendTone: "warn" | "ok" = underShift >= 3 ? "warn" : "ok";
  const drift = {
    labels: months.map((m) => m.label),
    rating: months.map((m) => m.avgRating),
    underLine: months.map((m) => m.underLinePct),
    attended: months.map((m) => m.avgAttended),
    score: months.map((m) => m.avgScore),
    table: {
      headers: ["Month", "Classes", "Avg rating", "Under 4.55", "In the room", "Rated", "Avg score", "Bad"],
      rows: months.map((m) => [m.label, m.n, fmtAvg(m.avgRating), pctText(m.underLinePct), m.avgAttended == null ? "—" : Math.round(m.avgAttended), pctText(m.avgReach), fmtScore(m.avgScore), pctText(m.badPct)]),
    },
  };

  // ── 6. by course ──
  const courses = byCourse(rows);
  const courseRows: CourseRow[] = courses
    .filter((c) => c.n >= 10)
    .map((c) => ({
      key: c.key,
      name: c.name,
      href: c.slug ? hrefIn(c.slug, "/overview") : null,
      n: c.n,
      avgScore: c.avgScore,
      counts: { excellent: c.counts.excellent, good: c.counts.good, average: c.counts.average, bad: c.counts.bad },
      avgRating: c.avgRating,
      avgAttended: mean(c.rows.map((r) => r.attended).filter((v): v is number => v != null)),
      approval: c.approval,
      reach: c.reach,
      badPct: c.badShare == null ? null : c.badShare * 100,
    }));
  const topBadCourse = [...courses].filter((c) => c.counts.bad > 0).sort((a, b) => b.counts.bad - a.counts.bad)[0];
  const teamBadPct = total.badShare == null ? null : total.badShare * 100;

  // ── 7. content vs delivery ──
  const topics = byTopic(rows);
  const contentTopics = topics.filter((t) => t.tag === "content").sort((a, b) => (a.avgScore ?? 100) - (b.avgScore ?? 100)).slice(0, 6);
  const deliveryTopics = topics
    .filter((t) => t.tag === "delivery" && t.bestSme && t.worstSme)
    .sort((a, b) => (b.bestSme!.avgScore ?? 0) - (b.worstSme!.avgScore ?? 0) - ((a.bestSme!.avgScore ?? 0) - (a.worstSme!.avgScore ?? 0)))
    .slice(0, 6);
  const contentCount = topics.filter((t) => t.tag === "content").length;
  const deliveryCount = topics.filter((t) => t.tag === "delivery").length;
  const moduleHref = (t: (typeof topics)[number]) => {
    const slug = t.rows[0]?.course_slug;
    return slug ? hrefIn(slug, `/modules/${encodeURIComponent(t.key)}`) : null;
  };

  // ── 8. fair to everyone? ──
  // A slice needs a real sample before it can say anything; the region card needs both regions
  // (the cohort text names India reliably, the US only sometimes).
  const MIN_SLICE = 20;
  const all = slices(rows);
  const fair = {
    kind: all.kind.filter((s) => s.n >= MIN_SLICE),
    region: all.region && all.region.filter((s) => s.n >= MIN_SLICE).length >= 2 ? all.region.filter((s) => s.n >= MIN_SLICE) : null,
    weekday: all.weekday.filter((s) => s.n >= MIN_SLICE),
  };
  const bars = (list: typeof fair.kind) => list.map((s) => ({ label: s.label, value: Math.round(s.avgScore ?? 0), sub: `${s.n.toLocaleString()} ${plural(s.n, "class", "classes")} · rated ${fmtAvg(s.avgRating)}` }));
  const gap = (list: typeof fair.kind | null) => {
    const xs = (list ?? []).map((s) => s.avgScore).filter((v): v is number => v != null);
    return xs.length >= 2 ? Math.max(...xs) - Math.min(...xs) : null;
  };
  const kindGap = gap(fair.kind);
  const regionGap = gap(fair.region);
  const weekdayGap = gap(fair.weekday);
  const live = fair.kind.find((s) => s.key === "Live Class");
  const review = fair.kind.find((s) => s.key === "Test Review");

  return (
    <div className="mx-auto max-w-4xl xl:grid xl:max-w-6xl xl:grid-cols-[168px_minmax(0,56rem)] xl:justify-center xl:gap-x-10">
      {/* ── editorial header, the report's voice ── */}
      <header className="xl:col-start-2">
        <div className="text-muted-foreground mb-2 text-[10.5px] font-semibold tracking-[0.14em] uppercase">Interview Kickstart · New Programs · live study</div>
        <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] sm:text-[30px]">
          What <span data-numeric>{total.n.toLocaleString()}</span> rated classes say about the score
        </h1>
        <p className="text-muted-foreground mt-2 max-w-2xl text-[14.5px] leading-relaxed">
          Every live class and test review from <b className="text-foreground">{win.label}</b>, straight from the ratings sheet and scored by{" "}
          <b className="text-foreground">version {activeVersion}</b> — recomputed on every sync. <b className="text-foreground">{attended.toLocaleString()}</b> learners sat in a
          class, <b className="text-foreground">{rated.toLocaleString()}</b> rated one
          {total.votes > 0 && (
            <>
              , <b className="text-foreground">{total.votes.toLocaleString()}</b> said whether they would have the instructor back
            </>
          )}
          . The offline study that chose this version is re-run below on the live database, so nobody has to take the PDF on trust.
        </p>
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          <Kpi label={`Classes · ${win.label}`} value={total.n.toLocaleString()} sub={`${fmt1(total.n / win.weeks)} a week`} />
          <Kpi label="Average score" value={<AvgScorePill score={total.avgScore} label="avg" />} sub={`${total.scored.toLocaleString()} with a band`} />
          <Kpi label="Shown Bad" value={<span className={cn(teamBadPct != null && teamBadPct >= 10 && "text-destructive")}>{pctText(teamBadPct)}</span>} sub={`${total.counts.bad.toLocaleString()} classes → video`} />
          <Kpi label="Would have the instructor back" value={<span className={cn(total.approval != null && total.approval < 80 && "text-destructive")}>{fmtPct(total.approval)}</span>} sub="pooled over every approval answer" />
          <Kpi label={`Analyses a week · v${activeVersion}`} value={whatActive ? fmt1(whatActive.analyses_per_week) : "—"} sub={whatActive ? `${fmt1(whatActive.videos_per_week)} video · ${fmt1(whatActive.transcripts_per_week)} transcript` : "database function unavailable"} />
        </div>
      </header>

      {/* the navigator: left rail on xl, pill row under the topbar below that */}
      <SectionNav sections={SECTIONS} className="xl:col-start-1 xl:row-span-2 xl:row-start-1" />

      <article className="min-w-0 xl:col-start-2">
        {rows.length === 0 && (
          <Empty className="mt-6 rounded-xl border">No rated classes in {win.label} yet — this study fills in as the sheet syncs.</Empty>
        )}

        {/* ── 1 ── */}
        <Section id="right">
          <SectionHeader n={1} id="right-title" title={sec("right").title} />
          <Lede>
            Five numbers decided the score. The study measured them offline on the eight months to August; the two live columns measure the same five on{" "}
            <b>{total.n.toLocaleString()} classes</b>, {win.label}, under the manager&apos;s original settings and under the version that is live today.
            {activeIsV1 && <> Version 1 is the live version, so its two columns agree by construction.</>}
          </Lede>
          <FiveNumbers
            rows={fiveRows}
            columns={{
              v1: "Manager's original",
              v1Note: `v1 · ${v1.name}`,
              active: activeIsV1 ? "Live today" : `Live today · v${activeVersion}`,
              activeNote: active.name,
              study: "The study said",
              studyNote: STUDY_LABEL,
            }}
          />
          <AccentReveal className="mt-3">
            <Callout tone="ok" icon={Scale} title="What the change does">
              {activeIsV1 ? (
                <>
                  Version 1 has no hard lines: a strong vote can buy back a low rating, which is how it showed <b>{mV1.comfort.firm.toLocaleString()}</b> low classes as Good or
                  Excellent and called <b>{mV1.badAbove.count.toLocaleString()}</b> classes Bad that the room rated 4.55 or better. The recommended version fixes both by keeping the
                  two lines hard.
                </>
              ) : (
                <>
                  In this window the original showed <b>{mV1.comfort.firm.toLocaleString()}</b> low {plural(mV1.comfort.firm, "class", "classes")} as Good or Excellent and called{" "}
                  <b>{mV1.badAbove.count.toLocaleString()}</b> Bad that the room rated 4.55 or better; version {activeVersion} shows <b>{mAct.comfort.firm.toLocaleString()}</b> and{" "}
                  <b>{mAct.badAbove.count.toLocaleString()}</b>.
                  {whatV1 && whatActive && (
                    <>
                      {" "}
                      The price is more reading — <b>{fmt1(whatV1.transcripts_per_week)}</b> → <b>{fmt1(whatActive.transcripts_per_week)}</b> transcript reads a week — while videos go{" "}
                      {fmt1(whatV1.videos_per_week)} → {fmt1(whatActive.videos_per_week)}.
                    </>
                  )}
                </>
              )}{" "}
              Flips and analyses a week come from the database&apos;s own what-if function; the other three are computed on this page from the same rows, so a corrected sheet moves
              every column at once.{" "}
              <Link href="/admin/scoring" className="text-primary inline-flex items-center gap-0.5 font-medium hover:underline">
                Change or roll back on Admin › Scoring
                <ArrowUpRight className="size-3.5" aria-hidden />
              </Link>
            </Callout>
          </AccentReveal>
        </Section>

        {/* ── 2 ── */}
        <Section id="predict">
          <SectionHeader n={2} id="predict-title" title={sec("predict").title} />
          <Lede>
            {badAct.lowPct != null && excAct.lowPct != null ? (
              <>
                After a class shown <b>Bad</b>, the same instructor&apos;s next class is low <b>{Math.round(badAct.lowPct)}%</b> of the time; after an <b>Excellent</b> one,{" "}
                <b>{Math.round(excAct.lowPct)}%</b> — against <b>{pctText(mAct.risk.baseline.lowPct)}</b> for any class.
                {ratio != null && ratio >= 1.5 && (
                  <>
                    {" "}
                    That is <b>{ratio.toFixed(1)}×</b> the risk: the band forecasts the next class, it does not just describe the last one.
                  </>
                )}
              </>
            ) : (
              <>
                A band needs <b>{mAct.risk.minPairs}</b> pairs before its share is shown; this window has {mAct.risk.pairs.toLocaleString()} pairs in all, and{" "}
                {mAct.risk.bands.filter((b) => b.tooFew).map((b) => BAND_META[b.band].label).join(", ")} {mAct.risk.bands.filter((b) => b.tooFew).length === 1 ? "has" : "have"} too few — the
                share is hidden rather than guessed.
              </>
            )}{" "}
            A next class is &ldquo;low&rdquo; when it is rated under 4.55 or fewer than 80% would have the instructor back; a pair needs 5+ votes on both sides.
          </Lede>
          <ChartCard
            title={`Next-class risk by band · v${activeVersion}`}
            subtitle="Share of the same instructor's next classes that were low · the dashed line is the base rate every band has to beat"
            table={{
              headers: ["Band", "Pairs", "Next class low", "Share"],
              rows: [
                ...mAct.risk.bands.map((b) => [BAND_META[b.band].label, b.n, b.low, b.lowPct == null ? `too few (under ${mAct.risk.minPairs})` : pctText(b.lowPct)]),
                ["All classes", mAct.risk.baseline.n, mAct.risk.baseline.low, pctText(mAct.risk.baseline.lowPct)],
              ],
            }}
          >
            <RiskBars
              items={mAct.risk.bands.map((b) => ({ label: BAND_META[b.band].label, pct: b.lowPct, n: b.n, color: BAND_META[b.band].color }))}
              baseline={{ pct: mAct.risk.baseline.lowPct, n: mAct.risk.baseline.n }}
            />
          </ChartCard>
          {!activeIsV1 && (
            <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
              Under the manager&apos;s original the same pairs read {riskText(badV1)} after Bad and {riskText(excV1)} after Excellent ({badV1.n.toLocaleString()} and{" "}
              {excV1.n.toLocaleString()} pairs).
            </p>
          )}
        </Section>

        {/* ── 3 ── */}
        <Section id="voices">
          <SectionHeader n={3} id="voices-title" title={sec("voices").title} />
          <Lede>
            {minBand > 0 || minAction > 0 ? (
              <>
                Version {activeVersion} shows <b>no band under {minBand} {plural(minBand, "vote")}</b>, a <b>provisional</b> band — watched, never sent for analysis — from{" "}
                {minBand} to {Math.max(minBand, minAction - 1)}, and a firm band from <b>{minAction}</b>.
              </>
            ) : (
              <>
                Version {activeVersion} shows a band however few voices spoke — a single rating is enough.
              </>
            )}{" "}
            In this window <b>{trust.noBand.toLocaleString()}</b> {plural(trust.noBand, "class", "classes")} ({pctText(trust.noBandPct)}) got no band and{" "}
            <b>{trust.provisional.toLocaleString()}</b> ({pctText(trust.provisionalPct)}) a provisional one: {declined.toLocaleString()} classes the score declined to judge on too few
            voices.
          </Lede>
          <ChartCard
            title="Bands by how many learners answered"
            subtitle="Every class in the window, grouped by how many voted · the label above each column is the class count"
            legend={[...BAND_ORDER.map((b) => ({ label: BAND_META[b].label, color: BAND_META[b].color })), { label: "No band", color: "var(--band-none)" }]}
            table={{
              headers: ["Votes", "Classes", ...BAND_ORDER.map((b) => BAND_META[b].label), "No band", "Provisional"],
              rows: trust.buckets.map((b) => [b.label, b.n, ...BAND_ORDER.map((band) => b.counts[band]), b.counts.none, `${b.provisional} (${pctText(b.provisionalPct)})`]),
            }}
          >
            <StackedBars
              labels={trust.buckets.map((b) => b.label)}
              height={220}
              normalize
              segments={[...BAND_ORDER.map((b) => ({ name: BAND_META[b].label, color: BAND_META[b].color })), { name: "No band", color: "var(--band-none)" }]}
              values={trust.buckets.map((b) => [...BAND_ORDER.map((band) => b.counts[band]), b.counts.none])}
              topLabels={trust.buckets.map((b) => (b.n ? `${b.n.toLocaleString()}${b.provisional ? ` · ${pctText(b.provisionalPct)} prov.` : ""}` : null))}
            />
          </ChartCard>
          <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
            With ten or more votes a band is settled; below that the score says so out loud rather than pretending three opinions are a verdict.
          </p>
        </Section>

        {/* ── 4 ── */}
        <Section id="vote">
          <SectionHeader n={4} id="vote-title" title={sec("vote").title} />
          {voted.length === 0 ? (
            <Lede>
              The ratings form also asks whether the room would have the instructor back. No votes have synced yet — this section fills in once the sheet&apos;s Yes / No columns
              arrive.
            </Lede>
          ) : (
            <>
              <Lede>
                Every rating form asks a second question: <i>would you want this instructor to take the class again?</i> Across <b>{voted.length.toLocaleString()}</b> classes with a
                vote, <b>{fmtPct(total.approval)}</b> of {total.votes.toLocaleString()} answers say yes, and in <b>{Math.round((nobodySaidNo / voted.length) * 100)}%</b> of classes
                nobody said no. The two signals move together but do not agree — the rating flags the class, the vote flags the instructor — which is why the score keeps both as
                hard lines instead of averaging them away.
              </Lede>
              <ChartCard
                title="Every class with an approval answer"
                subtitle="Rating against the share who would have the instructor back · the 4.55 line and the 80% bar are the score's two hard lines · the shaded corner misses both"
                legend={[
                  { label: "Clears both lines", color: "var(--chart-1)" },
                  { label: "Misses a line", color: "var(--viz-bad)" },
                ]}
              >
                <ScatterChart
                  points={approvalPoints}
                  labels={approvalLabels}
                  threshold={4.55}
                  bar={80}
                  cornerSide="left"
                  xLabel="share of voters who would have the instructor back"
                  xValueLabel="would have the instructor back"
                  barLabel="80% bar"
                  lineLabel="rating 4.55 — below this we look"
                  cornerLabel="misses both → Bad"
                  ariaLabel="Every class plotted by rating against the share who would have the instructor back. Most sit top-right; the shaded corner misses both lines; the strips beside it are where the two signals disagree."
                />
              </ChartCard>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {quadrants.map(({ q, n }) => (
                  <div key={q} className="bg-card shadow-soft h-full rounded-xl border p-4">
                    <div className="text-[12.5px] font-semibold">
                      <BandDot tone={QUADRANT_TONE[q]} />
                      {QUADRANT_META[q].label}
                    </div>
                    <div className="mt-1.5 flex items-baseline gap-1.5">
                      <span className={cn("text-[24px] leading-none font-semibold tracking-[-0.02em]", q === "fails" && "text-destructive")} data-numeric>
                        {n.toLocaleString()}
                      </span>
                      <span className="text-muted-foreground text-xs" data-numeric>
                        {Math.round((n / voted.length) * 100)}% of classes
                      </span>
                    </div>
                    <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
                      {QUADRANT_META[q].note}{" "}
                      {q === "fine" ? "Good or Excellent." : q === "fails" ? "Bad — a video." : "Capped at Average — a transcript read."}
                    </p>
                  </div>
                ))}
              </div>
              <Callout tone="ok" icon={Scale} title={hasCaps ? "Two lines, four boxes — and the score keeps both lines hard" : "Two lines, four boxes — but version 1 keeps neither line hard"} className="mt-3">
                {hasCaps ? (
                  <>
                    Rated under <b>4.55</b>, or fewer than <b>80%</b> would have the instructor back (with at least {minAction} votes): miss one line and the band is capped at{" "}
                    <b>Average</b> — a transcript read; miss both and it is <b>Bad</b> — a video. The weighted number (rating {active.config.weights.rating}, approval{" "}
                    {active.config.weights.approval}, track record {active.config.weights.track}) only orders classes inside a band and separates Good from Excellent; it can never lift a
                    class over a line it missed.
                  </>
                ) : (
                  <>
                    Under the live version a strong vote can buy back a low rating and a weak vote can sink a well-rated class, which is where the{" "}
                    <b>{mAct.comfort.firm.toLocaleString()}</b> hidden low classes and the <b>{mAct.badAbove.count.toLocaleString()}</b> Bad-but-liked classes in section 1 come from.
                    The recommended version keeps both lines hard.
                  </>
                )}
              </Callout>
            </>
          )}
        </Section>

        {/* ── 5 ── */}
        <Section id="trend">
          <SectionHeader n={5} id="trend-title" title={sec("trend").title} />
          {first && last && months.length >= 2 && (
            <AccentReveal className="mb-3">
              <Callout tone={trendTone} icon={trendTone === "warn" ? TrendingDown : TrendingUp} title={underShift >= 3 ? "Low-rated classes are climbing" : underShift <= -3 ? "Low-rated classes are easing" : "Low-rated classes are holding"}>
                The share of classes rated under 4.55 went from{" "}
                <b>
                  {pctText(first.underLinePct)} in {first.label}
                </b>{" "}
                to{" "}
                <b>
                  {pctText(last.underLinePct)} in {last.label}
                </b>
                {peak && peak.month !== last.month && peak.month !== first.month ? ` (peak ${pctText(peak.underLinePct)} in ${peak.label})` : ""}. The average rating moved{" "}
                <b>{fmtAvg(first.avgRating)}</b> → <b>{fmtAvg(last.avgRating)}</b>, the room {first.avgAttended == null ? "—" : Math.round(first.avgAttended)} →{" "}
                {last.avgAttended == null ? "—" : Math.round(last.avgAttended)} learners, and {pctText(first.avgReach)} → {pctText(last.avgReach)} of them rated —{" "}
                {reachShift != null && Math.abs(reachShift) < 5
                  ? "participation held, so this is a real quality trend, not a change in who fills in ratings."
                  : "participation moved too, so read the rating trend with that in mind."}
                {topBadCourse && total.counts.bad > 0 && (
                  <>
                    {" "}
                    The Bad band is concentrated: <b>{topBadCourse.name}</b> carries{" "}
                    <b>
                      {topBadCourse.counts.bad} of the {total.counts.bad}
                    </b>{" "}
                    Bad classes ({Math.round((topBadCourse.counts.bad / total.counts.bad) * 100)}%).
                  </>
                )}
              </Callout>
            </AccentReveal>
          )}
          {months.length > 0 ? (
            <DriftCard data={drift} />
          ) : (
            <Empty className="rounded-xl border">Nothing to chart yet.</Empty>
          )}
          <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
            Four lines, one card: the share under the line is the one to watch; the average rating says how far under; class size says how much each rating weighs; the score says
            what the rule made of it all.
          </p>
        </Section>

        {/* ── 6 ── */}
        <Section id="courses">
          <SectionHeader n={6} id="courses-title" title={sec("courses").title} />
          <Lede>
            The trend is not spread evenly. Every course with at least <b>10 rated classes</b> in the window — click a heading to sort; the Bad share is tinted against the team&apos;s{" "}
            <b>{pctText(teamBadPct)}</b>.
          </Lede>
          <CourseTable rows={courseRows} teamBadPct={teamBadPct} />
          <p className="text-muted-foreground mt-2 text-xs leading-relaxed">
            The score is an average of class scores; the band mix shows what that average hides. A course name opens its workspace.
          </p>
        </Section>

        {/* ── 7 ── */}
        <Section id="content">
          <SectionHeader n={7} id="content-title" title={sec("content").title} />
          <Lede>
            A module that scores under Good for <b>two or more</b> instructors who have each taught it twice is a <b>content</b> problem; one that scores under Good for exactly one of
            several is a <b>delivery</b> problem. Over {topics.length.toLocaleString()} named modules this window: <b>{contentCount}</b> content, <b>{deliveryCount}</b> delivery.
          </Lede>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className={CARD}>
              <div className="flex items-start gap-2.5 px-4 pt-4 sm:px-5">
                <span className="bg-warning/15 text-warning flex size-8 shrink-0 items-center justify-center rounded-lg">
                  <Puzzle className="size-4" aria-hidden />
                </span>
                <div>
                  <h3 className="text-[13px] font-semibold">Likely content issues</h3>
                  <p className="text-muted-foreground text-xs">Low under every instructor who has taught it — the material, not the person. Lowest average first.</p>
                </div>
              </div>
              <Table density="compact">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Module</TableHead>
                    <TableHead className="text-right">Avg score</TableHead>
                    <TableHead className="text-right">Instructors</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {contentTopics.map((t) => {
                    const href = moduleHref(t);
                    return (
                      <TableRow key={t.key}>
                        <TableCell className="max-w-60 truncate font-medium" title={t.name}>
                          {href ? (
                            <Link href={href} className="hover:text-primary transition-colors">
                              {t.name}
                            </Link>
                          ) : (
                            t.name
                          )}
                          <span className="text-muted-foreground block truncate text-[10.5px] font-normal">{t.rows[0]?.course_name ?? t.rows[0]?.course_label}</span>
                        </TableCell>
                        <TableCell className="text-right">
                          <AvgScorePill score={t.avgScore} />
                        </TableCell>
                        <TableNum className="text-muted-foreground">{t.instructors.filter((i) => i.n >= 2).length}</TableNum>
                        <TableNum className="text-muted-foreground">{t.n}</TableNum>
                      </TableRow>
                    );
                  })}
                  {contentTopics.length === 0 && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={4} className="text-muted-foreground">
                        No module is low across two or more instructors — a good sign.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            <div className={CARD}>
              <div className="flex items-start gap-2.5 px-4 pt-4 sm:px-5">
                <span className="bg-primary/12 text-primary flex size-8 shrink-0 items-center justify-center rounded-lg">
                  <Users className="size-4" aria-hidden />
                </span>
                <div>
                  <h3 className="text-[13px] font-semibold">Likely delivery issues</h3>
                  <p className="text-muted-foreground text-xs">Fine under some instructors, low under one — the widest gap first. The module page names them.</p>
                </div>
              </div>
              <Table density="compact">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Module</TableHead>
                    <TableHead className="text-right">Best · lowest</TableHead>
                    <TableHead className="text-right">Gap</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {deliveryTopics.map((t) => {
                    const href = moduleHref(t);
                    const best = t.bestSme!.avgScore;
                    const worst = t.worstSme!.avgScore;
                    return (
                      <TableRow key={t.key}>
                        <TableCell className="max-w-60 truncate font-medium" title={t.name}>
                          {href ? (
                            <Link href={href} className="hover:text-primary transition-colors">
                              {t.name}
                            </Link>
                          ) : (
                            t.name
                          )}
                          <span className="text-muted-foreground block truncate text-[10.5px] font-normal">{t.rows[0]?.course_name ?? t.rows[0]?.course_label}</span>
                        </TableCell>
                        <TableNum>
                          <BandDot tone="good" />
                          {fmtScore(best)} <span className="text-muted-foreground">·</span> <BandDot tone="bad" />
                          {fmtScore(worst)}
                        </TableNum>
                        <TableNum className="font-semibold">{best != null && worst != null ? Math.round(best - worst) : "—"}</TableNum>
                        <TableNum className="text-muted-foreground">{t.n}</TableNum>
                      </TableRow>
                    );
                  })}
                  {deliveryTopics.length === 0 && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={4} className="text-muted-foreground">
                        No module splits its instructors yet — needs repeat instructor–module pairs.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </Section>

        {/* ── 8 ── */}
        <Section id="fair">
          <SectionHeader n={8} id="fair-title" title={sec("fair").title} />
          <Lede>
            The same rule for every kind of class. A live class averages <b>{fmtScore(live?.avgScore)}</b> and a test review <b>{fmtScore(review?.avgScore)}</b>
            {kindGap != null && (
              <>
                {" "}
                — <b>{Math.round(kindGap)}</b> {plural(Math.round(kindGap), "point")} apart
              </>
            )}
            {regionGap != null && (
              <>
                ; India and the US sit <b>{Math.round(regionGap)}</b> {plural(Math.round(regionGap), "point")} apart
              </>
            )}
            {weekdayGap != null && (
              <>
                ; the spread across weekdays is <b>{Math.round(weekdayGap)}</b> {plural(Math.round(weekdayGap), "point")}
              </>
            )}
            . A gap under ten points is the same score wearing a different timetable; a wider one is a question for the course, not for the rule. Slices with fewer than{" "}
            {MIN_SLICE} classes are left out{!all.region || fair.region ? "" : "; the cohort text does not name the US region often enough to compare India and the US"}.
          </Lede>
          <div className={cn("grid gap-4", fair.region ? "lg:grid-cols-3" : "lg:grid-cols-2")}>
            <ChartCard title="Live vs review" subtitle="Average score · classes and average rating under each bar">
              <HBars items={bars(fair.kind)} maxValue={100} format={(v) => String(Math.round(v))} />
            </ChartCard>
            {fair.region && (
              <ChartCard title="India vs US" subtitle="From the cohort each class ran for">
                <HBars items={bars(fair.region)} maxValue={100} format={(v) => String(Math.round(v))} />
              </ChartCard>
            )}
            <ChartCard title="By weekday" subtitle={`Monday first · weekdays with ${MIN_SLICE}+ classes`}>
              <HBars items={bars(fair.weekday)} maxValue={100} format={(v) => String(Math.round(v))} />
            </ChartCard>
          </div>
        </Section>

        {/* ── 9 ── */}
        <Section id="vision">
          <SectionHeader n={9} id="vision-title" title={sec("vision").title} />
          <div className="bg-card shadow-soft rounded-xl border p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <span className="bg-primary/12 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                <Lightbulb className="size-4.5" aria-hidden />
              </span>
              <p className="text-muted-foreground text-[13px] leading-relaxed">
                From tracking ratings to a system that decides better — instructor allocation, content work, learner intervention, training and hiring. What v3 shipped, what is
                waiting on data, and what comes next.
              </p>
            </div>
            <ol className="mt-4 grid gap-3 lg:grid-cols-2">
              {VISION.map((v, i) => (
                <li key={v.title} className="surface-inset rounded-lg border p-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[13px] font-semibold">
                      <span className="text-muted-foreground mr-1.5" data-numeric>
                        {i + 1}.
                      </span>
                      {v.title}
                    </p>
                    <Badge variant={v.status === "live" ? "success" : v.status === "waiting" ? "warning" : "secondary"} className="shrink-0">
                      {STATUS_LABEL[v.status]}
                    </Badge>
                  </div>
                  <p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">{v.body}</p>
                </li>
              ))}
            </ol>
            <p className="text-muted-foreground mt-4 text-xs leading-relaxed">
              The questions this system answers: who is the best instructor for each module · where does each instructor need help · which modules need content work · where in the
              journey do ratings and attendance start declining · which learners are consistently dissatisfied and why · what makes the best instructors different — and how to use
              that for hiring, evaluation, training and allocation.
            </p>
          </div>
        </Section>
      </article>
    </div>
  );
}
