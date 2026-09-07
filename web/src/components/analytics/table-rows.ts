import type { CohortAgg, CourseAgg, InstructorAgg, ScoredRating, TopicAgg } from "@/lib/analytics";
import type { Action, Band, ComponentRow } from "@/lib/sentiment";

/** Slim view-model rows for the client-sortable tables.
 *
 *  A page aggregates on the server (`byInstructor`, `byCohort`, `byTopic`, `byCourse`) and maps
 *  each aggregate to the handful of plain fields its table shows — never the aggregate itself,
 *  whose `rows` would drag every underlying rating into the RSC payload. Rows carry comparable
 *  values (numbers, ISO dates, names) rather than formatted strings, because they are what the
 *  client sorts on. No runtime imports: this module is safe on both sides of the boundary. */

export type BandCounts = { excellent: number; good: number; average: number; bad: number };

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

/** Average learners in the room, over the classes that recorded attendance. */
export function avgAttended(rows: { attended: number | null }[]): number | null {
  return mean(rows.map((r) => r.attended).filter((v): v is number => v != null));
}

const fourBands = (c: BandCounts): BandCounts => ({ excellent: c.excellent, good: c.good, average: c.average, bad: c.bad });

/** What every aggregate shares: its `ScoreSummary` and the rows behind it. */
type Summary = Pick<InstructorAgg, "n" | "avgScore" | "counts" | "badShare" | "avgRating" | "approval" | "reach" | "rows">;

/** The columns a cohort, module, course or instructor row shows. */
export type GroupRowVM = {
  key: string;
  name: string;
  href: string | null;
  n: number;
  avgScore: number | null;
  counts: BandCounts;
  /** Share of scored classes in the Bad band — what the "Band mix" column sorts on. */
  badShare: number | null;
  avgRating: number | null;
  avgAttended: number | null;
  approval: number | null;
  reach: number | null;
};

function groupRow(key: string, name: string, href: string | null, s: Summary): GroupRowVM {
  return {
    key,
    name,
    href,
    n: s.n,
    avgScore: s.avgScore,
    counts: fourBands(s.counts),
    badShare: s.badShare,
    avgRating: s.avgRating,
    avgAttended: avgAttended(s.rows),
    approval: s.approval,
    reach: s.reach,
  };
}

// ── instructors ───────────────────────────────────────────────────────────────
export type InstructorRowVM = GroupRowVM & {
  href: string;
  aliases: string[];
  courses: { name: string; href: string | null }[];
  /** Avg score minus the previous period's; null without a previous. */
  delta: number | null;
  lastClassDate: string;
};

export function instructorRow(
  i: InstructorAgg,
  opts: { href: string; previous?: number | null; courseHref?: (slug: string | null) => string | null },
): InstructorRowVM {
  const prev = opts.previous ?? null;
  return {
    ...groupRow(i.key, i.name, opts.href, i),
    href: opts.href,
    aliases: i.aliases,
    courses: i.courses.map((c) => ({ name: c.name, href: opts.courseHref?.(c.slug) ?? null })),
    delta: prev == null || i.avgScore == null ? null : i.avgScore - prev,
    lastClassDate: i.lastClassDate,
  };
}

// ── cohorts · modules · courses ───────────────────────────────────────────────
export type CohortRowVM = GroupRowVM & { weekNow: number };

export const cohortRow = (c: CohortAgg, href: string | null = null): CohortRowVM => ({ ...groupRow(c.ref.key, c.ref.name, href, c), weekNow: c.weekNow });

export type ModuleRowVM = GroupRowVM & { tag: "content" | "delivery" | null };

export const moduleRow = (t: TopicAgg, href: string | null = null): ModuleRowVM => ({ ...groupRow(t.key, t.name, href, t), tag: t.tag });

export type CourseRowVM = GroupRowVM & {
  color: string | null;
  initials: string | null;
  /** Avg score minus the previous period's; null without a previous. */
  delta: number | null;
  bad: number;
  average: number;
};

export function courseRow(
  c: CourseAgg,
  opts: { href: string | null; previous?: number | null; color?: string | null; initials?: string | null },
): CourseRowVM {
  const prev = opts.previous ?? null;
  return {
    ...groupRow(c.key, c.name, opts.href, c),
    color: opts.color ?? null,
    initials: opts.initials ?? null,
    delta: prev == null || c.avgScore == null ? null : c.avgScore - prev,
    bad: c.counts.bad,
    average: c.counts.average,
  };
}

// ── classes (the worst-classes tables) ────────────────────────────────────────
export type OutcomeStage = "open" | "dismissed" | "confirmed" | "analysed" | "approved" | "sent";

/** Later steps rank higher, so sorting by outcome groups what reached the instructor. */
export const OUTCOME_RANK: Record<OutcomeStage, number> = { open: 0, dismissed: 1, confirmed: 2, analysed: 3, approved: 4, sent: 5 };

export type Outcome = { analysed: boolean; approved: boolean; sent: boolean; classId: string | null };

/** Where a flagged class got to: the loop's record first, the review status otherwise. */
export function outcomeStage(status: ScoredRating["review_status"], o?: Outcome | null): OutcomeStage {
  if (o?.sent) return "sent";
  if (o?.approved) return "approved";
  if (o?.analysed) return "analysed";
  if (status === "dismissed") return "dismissed";
  if (status === "confirmed" || status === "analysis_started") return "confirmed";
  return "open";
}

/** The lowest-scoring classes of a set: banded rows only, by score then rating. */
export function worstOf<T extends { score: number | null; band: Band | null; rating: number }>(rows: T[], limit: number): T[] {
  return rows
    .filter((r) => r.score != null && r.band != null)
    .sort((a, b) => a.score! - b.score! || a.rating - b.rating)
    .slice(0, limit);
}

export type ClassRowVM = {
  id: string;
  href: string;
  topic: string;
  kind: string;
  course: string | null;
  instructor: string;
  date: string;
  score: number | null;
  band: Band | null;
  provisional: boolean;
  action: Action;
  /** Scored by the web mirror rather than the database. */
  preview: boolean;
  breakdown: ComponentRow[];
  reason: string;
  rating: number;
  rated: number | null;
  attended: number | null;
  /** Null when the page does not track outcomes. */
  outcome: OutcomeStage | null;
  feedbackHref: string | null;
};

export function classRow(r: ScoredRating, opts: { href: string; reason: string; instructor: string; outcome?: Outcome | null }): ClassRowVM {
  return {
    id: r.id,
    href: opts.href,
    topic: r.topic || r.session_kind,
    kind: r.session_kind,
    course: r.course_name ?? r.course_label,
    instructor: opts.instructor,
    date: r.class_date,
    score: r.score,
    band: r.band,
    provisional: r.provisional,
    action: r.action,
    preview: r.scored_by !== "db",
    breakdown: r.breakdown,
    reason: opts.reason,
    rating: r.rating,
    rated: r.num_ratings,
    attended: r.attended,
    outcome: opts.outcome === undefined ? null : outcomeStage(r.review_status, opts.outcome),
    feedbackHref: opts.outcome?.classId ? `/feedback/${opts.outcome.classId}` : null,
  };
}

// ── the team overview's queue-capacity table ──────────────────────────────────
export type CapacityRowVM = {
  key: string;
  name: string;
  href: string | null;
  video: number;
  transcript: number;
  minutes: number;
  usd: number;
  /** Days since the oldest open class; null when nothing is open. */
  age: number | null;
};
