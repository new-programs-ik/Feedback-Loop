"use client";

import Link from "next/link";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { ScorePill } from "@/components/score/score-pill";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { RawStat } from "@/components/analytics/raw-stat";
import { CourseSquare, DataTable, Delta, Empty, KindChip } from "@/components/analytics/ui";
import { ApprovalNum, AttendedNum, NameCell, RatingNum, ReachNum, prettyDate } from "@/components/analytics/table-cells";
import {
  OUTCOME_RANK,
  type CapacityRowVM,
  type ClassRowVM,
  type CohortRowVM,
  type CourseRowVM,
  type GroupRowVM,
  type ModuleRowVM,
  type OutcomeStage,
} from "@/components/analytics/table-rows";

/** The client-sortable tables of the reports and the team overview. Each takes slim rows from
 *  `table-rows`, sorts them locally (a heading click, no URL round-trip) and draws them with the
 *  same columns in the same order everywhere: Classes · Avg score · Band mix · Avg rating ·
 *  Avg attended · Approval · Reach. Print shows whatever order is on screen. */

const MIX_TITLE = "Sort by the share of Bad classes";
const DELTA_TITLE = "Sort by the change since the previous period";

// ── the columns cohorts, modules and courses share ────────────────────────────
type GroupKey = "name" | "n" | "score" | "mix" | "rating" | "attended" | "approval" | "reach";

const GROUP_SPEC: SortSpec<GroupRowVM, GroupKey> = {
  name: { value: (r) => r.name, first: "asc" },
  n: { value: (r) => r.n, first: "desc" },
  score: { value: (r) => r.avgScore, first: "desc" },
  mix: { value: (r) => r.badShare, first: "desc" },
  rating: { value: (r) => r.avgRating, first: "desc" },
  attended: { value: (r) => r.avgAttended, first: "desc" },
  approval: { value: (r) => r.approval, first: "desc" },
  reach: { value: (r) => r.reach, first: "desc" },
};

/** Classes · Avg score · Band mix · Avg rating · Avg attended · Approval · Reach. */
function GroupCells({ r, stripWidth = "w-16" }: { r: GroupRowVM; stripWidth?: string }) {
  return (
    <>
      <TableNum className="text-muted-foreground">{r.n}</TableNum>
      <TableCell>
        <AvgScorePill score={r.avgScore} />
      </TableCell>
      <TableCell>
        <BandStripOf counts={r.counts} className={stripWidth} />
      </TableCell>
      <RatingNum value={r.avgRating} />
      <AttendedNum value={r.avgAttended} />
      <ApprovalNum value={r.approval} />
      <ReachNum value={r.reach} />
    </>
  );
}

// ── cohorts ───────────────────────────────────────────────────────────────────
/** Cohorts of a period, most classes first. */
export function CohortsTable({ rows, maxHeight }: { rows: CohortRowVM[]; maxHeight?: string }) {
  const { sorted, state, toggle } = useSortable(rows, GROUP_SPEC, { key: "n", dir: "desc" });
  const th = { state, onToggle: toggle };
  return (
    <DataTable maxHeight={maxHeight}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" {...th}>Cohort</SortButton>
          <SortButton sortKey="n" {...th} align="right">Classes</SortButton>
          <SortButton sortKey="score" {...th}>Avg score</SortButton>
          <SortButton sortKey="mix" {...th} title={MIX_TITLE}>Band mix</SortButton>
          <SortButton sortKey="rating" {...th} align="right">Avg rating</SortButton>
          <SortButton sortKey="attended" {...th} align="right">Avg attended</SortButton>
          <SortButton sortKey="approval" {...th} align="right">Approval</SortButton>
          <SortButton sortKey="reach" {...th} align="right">Rated / attended</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((c) => (
          <TableRow key={c.key} className="relative">
            <NameCell href={c.href} name={c.name} />
            <GroupCells r={c} />
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}

// ── modules ───────────────────────────────────────────────────────────────────
const MODULE_SPEC: SortSpec<ModuleRowVM, GroupKey | "tag"> = { ...GROUP_SPEC, tag: { value: (r) => r.tag, first: "asc" } };

/** Modules of a period, lowest score first; the tag says whether it is the content or one
 *  instructor's delivery. */
export function ModulesTable({ rows, maxHeight }: { rows: ModuleRowVM[]; maxHeight?: string }) {
  const { sorted, state, toggle } = useSortable(rows, MODULE_SPEC, { key: "score", dir: "asc" });
  const th = { state, onToggle: toggle };
  return (
    <DataTable maxHeight={maxHeight}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" {...th}>Module</SortButton>
          <SortButton sortKey="tag" {...th}>Tag</SortButton>
          <SortButton sortKey="n" {...th} align="right">Classes</SortButton>
          <SortButton sortKey="score" {...th}>Avg score</SortButton>
          <SortButton sortKey="mix" {...th} title={MIX_TITLE}>Band mix</SortButton>
          <SortButton sortKey="rating" {...th} align="right">Avg rating</SortButton>
          <SortButton sortKey="attended" {...th} align="right">Avg attended</SortButton>
          <SortButton sortKey="approval" {...th} align="right">Approval</SortButton>
          <SortButton sortKey="reach" {...th} align="right">Rated / attended</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((t) => (
          <TableRow key={t.key} className="relative">
            <NameCell href={t.href} name={t.name} />
            <TableCell className="text-muted-foreground">{t.tag ?? "—"}</TableCell>
            <GroupCells r={t} />
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}

// ── courses (the team report) ─────────────────────────────────────────────────
const COURSE_SPEC: SortSpec<CourseRowVM, GroupKey | "delta" | "bad" | "average"> = {
  ...GROUP_SPEC,
  delta: { value: (r) => r.delta, first: "desc" },
  bad: { value: (r) => r.bad, first: "desc" },
  average: { value: (r) => r.average, first: "desc" },
};

/** Every course in a period, worst Bad share first; a row opens the course's own report. */
export function CoursesTable({ rows, maxHeight }: { rows: CourseRowVM[]; maxHeight?: string }) {
  const { sorted, state, toggle } = useSortable(rows, COURSE_SPEC, { key: "mix", dir: "desc" });
  const th = { state, onToggle: toggle };
  return (
    <DataTable maxHeight={maxHeight}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" {...th}>Course</SortButton>
          <SortButton sortKey="n" {...th} align="right">Classes</SortButton>
          <SortButton sortKey="score" {...th}>Avg score</SortButton>
          <SortButton sortKey="mix" {...th} title={MIX_TITLE}>Band mix</SortButton>
          <SortButton sortKey="rating" {...th} align="right">Avg rating</SortButton>
          <SortButton sortKey="attended" {...th} align="right">Avg attended</SortButton>
          <SortButton sortKey="approval" {...th} align="right">Approval</SortButton>
          <SortButton sortKey="reach" {...th} align="right">Rated / attended</SortButton>
          <SortButton sortKey="delta" {...th} align="right" title={DELTA_TITLE}>Δ</SortButton>
          <SortButton sortKey="bad" {...th} align="right">Bad</SortButton>
          <SortButton sortKey="average" {...th} align="right">Average</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((c) => (
          <TableRow key={c.key} className="relative">
            <TableCell className="max-w-64">
              <span className="flex items-center gap-2">
                {c.color && c.initials && <CourseSquare color={c.color} initials={c.initials} size={22} />}
                {c.href ? (
                  <Link href={c.href} className="hover:text-primary truncate font-medium after:absolute after:inset-0">
                    {c.name}
                  </Link>
                ) : (
                  <span className="truncate font-medium">{c.name}</span>
                )}
              </span>
            </TableCell>
            <GroupCells r={c} stripWidth="w-20" />
            <TableNum>
              <Delta value={c.delta} />
            </TableNum>
            <TableNum className={c.bad ? "text-destructive font-semibold" : "text-muted-foreground"}>{c.bad}</TableNum>
            <TableNum className="text-muted-foreground">{c.average}</TableNum>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}

// ── the worst classes ─────────────────────────────────────────────────────────
type ClassKey = "score" | "topic" | "course" | "instructor" | "date" | "rating" | "outcome";

const CLASS_SPEC: SortSpec<ClassRowVM, ClassKey> = {
  score: { value: (r) => r.score, first: "asc" },
  topic: { value: (r) => r.topic, first: "asc" },
  course: { value: (r) => r.course, first: "asc" },
  instructor: { value: (r) => r.instructor, first: "asc" },
  date: { value: (r) => r.date, first: "desc" },
  rating: { value: (r) => r.rating, first: "asc" },
  outcome: { value: (r) => (r.outcome ? OUTCOME_RANK[r.outcome] : null), first: "asc" },
};

const OUTCOME_WORD: Record<OutcomeStage, { label: string; className: string }> = {
  sent: { label: "sent", className: "text-success font-medium" },
  approved: { label: "approved", className: "text-success font-medium" },
  analysed: { label: "analysed", className: "font-medium" },
  confirmed: { label: "confirmed", className: "text-muted-foreground" },
  dismissed: { label: "dismissed", className: "text-muted-foreground" },
  open: { label: "open", className: "text-muted-foreground" },
};

/** The worst classes of a period on the reports: score pill, the class (opens the drawer), the
 *  instructor, the date, the raw rating with rated / attended, the reason in plain words and —
 *  when the page tracks the loop — what happened to each. Lowest score first. */
export function WorstClassesTable({
  rows,
  showCourse = false,
  withOutcome = false,
  maxHeight,
  emptyText = "No scored classes in this range.",
}: {
  rows: ClassRowVM[];
  showCourse?: boolean;
  withOutcome?: boolean;
  maxHeight?: string;
  emptyText?: string;
}) {
  const { sorted, state, toggle } = useSortable(rows, CLASS_SPEC, { key: "score", dir: "asc" });
  const th = { state, onToggle: toggle };
  if (rows.length === 0) return <Empty>{emptyText}</Empty>;
  return (
    <DataTable maxHeight={maxHeight}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="score" {...th}>Score</SortButton>
          <SortButton sortKey="topic" {...th}>Class</SortButton>
          {showCourse && <SortButton sortKey="course" {...th}>Course</SortButton>}
          <SortButton sortKey="instructor" {...th}>Instructor</SortButton>
          <SortButton sortKey="date" {...th} align="right">Date</SortButton>
          <SortButton sortKey="rating" {...th} align="right" title="Sort by the rating">Rating · rated/attended</SortButton>
          <TableHead>Why</TableHead>
          {withOutcome && <SortButton sortKey="outcome" {...th} title="Sort by how far the class got through the loop">Outcome</SortButton>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((r) => (
          <TableRow key={r.id} className="relative">
            <TableCell>
              <ScorePill
                score={r.score}
                band={r.band}
                variant={r.band == null ? "empty" : "sm"}
                provisional={r.provisional}
                action={r.action}
                breakdown={{ rows: r.breakdown, reason: r.reason, version: r.preview ? "preview" : undefined }}
              />
            </TableCell>
            <NameCell href={r.href} name={r.topic} className="max-w-64">
              <span className="text-muted-foreground flex items-center gap-1.5 text-[10.5px]">
                <KindChip kind={r.kind} />
              </span>
            </NameCell>
            {showCourse && <TableCell className="text-muted-foreground max-w-40 truncate">{r.course ?? "—"}</TableCell>}
            <TableCell className="max-w-40 truncate">{r.instructor}</TableCell>
            <TableNum className="text-muted-foreground">{prettyDate(r.date)}</TableNum>
            <TableNum>
              <RawStat rating={r.rating} rated={r.rated} attended={r.attended} />
            </TableNum>
            <TableCell className="text-muted-foreground max-w-md min-w-56 text-[12px] leading-snug whitespace-normal">{r.reason}</TableCell>
            {withOutcome && (
              <TableCell className="text-[12px] whitespace-nowrap">
                {r.outcome ? <span className={OUTCOME_WORD[r.outcome].className}>{OUTCOME_WORD[r.outcome].label}</span> : <span className="text-muted-foreground">—</span>}
                {r.feedbackHref && (
                  <>
                    {" "}
                    <Link href={r.feedbackHref} className="text-primary relative z-[1] hover:underline">
                      view
                    </Link>
                  </>
                )}
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}

// ── queue capacity (the team overview) ────────────────────────────────────────
type CapacityKey = "name" | "video" | "transcript" | "minutes" | "usd" | "age";

const CAPACITY_SPEC: SortSpec<CapacityRowVM, CapacityKey> = {
  name: { value: (r) => r.name, first: "asc" },
  video: { value: (r) => r.video, first: "desc" },
  transcript: { value: (r) => r.transcript, first: "desc" },
  minutes: { value: (r) => r.minutes, first: "desc" },
  usd: { value: (r) => r.usd, first: "desc" },
  age: { value: (r) => r.age, first: "desc" },
};

const fmtMinutes = (m: number) => (m < 60 ? `${Math.round(m)} min` : `${(m / 60).toFixed(1)} h`);

/** Open analyses per course and what they cost; most videos first. A row opens the course queue. */
export function CapacityTable({ rows }: { rows: CapacityRowVM[] }) {
  const { sorted, state, toggle } = useSortable(rows, CAPACITY_SPEC, { key: "video", dir: "desc" });
  const th = { state, onToggle: toggle };
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" {...th}>Course</SortButton>
          <SortButton sortKey="video" {...th} align="right">Videos</SortButton>
          <SortButton sortKey="transcript" {...th} align="right">Transcripts</SortButton>
          <SortButton sortKey="minutes" {...th} align="right">Time</SortButton>
          <SortButton sortKey="usd" {...th} align="right">Cost</SortButton>
          <SortButton sortKey="age" {...th} align="right" title="Sort by the age of the oldest open class">Oldest</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((c) => (
          <TableRow key={c.key} className="relative">
            <NameCell href={c.href} name={c.name} className="max-w-48" />
            <TableNum className={c.video ? "font-semibold" : "text-muted-foreground"}>{c.video}</TableNum>
            <TableNum className={c.transcript ? "" : "text-muted-foreground"}>{c.transcript}</TableNum>
            <TableNum className="text-muted-foreground">{fmtMinutes(c.minutes)}</TableNum>
            <TableNum className="text-muted-foreground">${c.usd.toFixed(2)}</TableNum>
            <TableNum className={c.age != null && c.age > 14 ? "text-destructive font-semibold" : "text-muted-foreground"}>{c.age == null ? "—" : `${c.age} d`}</TableNum>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
