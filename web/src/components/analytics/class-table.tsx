"use client";

import * as React from "react";
import Link from "next/link";
import { TableBody, TableCell, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec, type SortState } from "@/components/ui/sortable";
import { ScorePill } from "@/components/score/score-pill";
import { ClickRow } from "@/components/score/click-row";
import { RawStat } from "@/components/analytics/raw-stat";
import { DataTable, Empty, KindChip } from "@/components/analytics/ui";
import type { Action, Band, ComponentRow } from "@/lib/sentiment";
import { cn } from "@/lib/utils";

/** One row per class — the cohort's run, or a module's every class — sortable by any column.
 *  A row opens the class drawer in place (`?class=`); the inner links (module, cohort,
 *  instructor) keep working. The page decides which columns apply. */

export type ClassRow = {
  id: string;
  href: string;
  week: number | null;
  module: string;
  moduleHref?: string;
  cohort?: string;
  cohortHref?: string;
  /** ISO date (sorts) and the label shown. */
  date: string;
  dateLabel: string;
  kind: string;
  instructor: string;
  instructorHref?: string;
  rating: number;
  rated: number | null;
  attended: number | null;
  reach: number | null;
  approval: number | null;
  pill: { score: number | null; band: Band | null; provisional: boolean; action: Action; rows: ComponentRow[]; reason: string; version?: string | number | null };
};

export type ClassSortKey = "week" | "module" | "cohort" | "date" | "kind" | "instructor" | "rating" | "attended" | "reach" | "approval" | "score";

const SPEC: SortSpec<ClassRow, ClassSortKey> = {
  week: { value: (r) => r.week, first: "asc" },
  module: { value: (r) => r.module, first: "asc" },
  cohort: { value: (r) => r.cohort, first: "asc" },
  date: { value: (r) => r.date, first: "desc" },
  kind: { value: (r) => r.kind, first: "asc" },
  instructor: { value: (r) => r.instructor, first: "asc" },
  rating: { value: (r) => r.rating, first: "asc" },
  attended: { value: (r) => r.attended, first: "desc" },
  reach: { value: (r) => r.reach, first: "desc" },
  approval: { value: (r) => r.approval, first: "asc" },
  score: { value: (r) => r.pill.score, first: "asc" },
};

export function ClassTable({
  rows,
  show = {},
  initialSort = { key: "date", dir: "desc" },
  activeId,
  emptyText = "No rated classes.",
}: {
  rows: ClassRow[];
  show?: { week?: boolean; module?: boolean; cohort?: boolean; kind?: boolean; approval?: boolean; attended?: boolean };
  initialSort?: SortState<ClassSortKey>;
  activeId?: string;
  emptyText?: string;
}) {
  const { sorted, state, toggle } = useSortable(rows, SPEC, initialSort);
  if (rows.length === 0) return <Empty>{emptyText}</Empty>;
  const kind = show.kind ?? true;
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {show.week && <SortButton sortKey="week" state={state} onToggle={toggle} align="right">Week</SortButton>}
          {show.module !== false && <SortButton sortKey="module" state={state} onToggle={toggle}>Module</SortButton>}
          {show.cohort && <SortButton sortKey="cohort" state={state} onToggle={toggle}>Cohort</SortButton>}
          <SortButton sortKey="date" state={state} onToggle={toggle}>Date</SortButton>
          {kind && <SortButton sortKey="kind" state={state} onToggle={toggle}>Kind</SortButton>}
          <SortButton sortKey="instructor" state={state} onToggle={toggle}>Instructor</SortButton>
          <SortButton sortKey="rating" state={state} onToggle={toggle} align="right" title="Rating · rated / attended">Rating</SortButton>
          {show.attended && <SortButton sortKey="attended" state={state} onToggle={toggle} align="right" title="Learners in the room">Attended</SortButton>}
          <SortButton sortKey="reach" state={state} onToggle={toggle} align="right" title="Share of the room that rated">Rated / attended</SortButton>
          {show.approval && <SortButton sortKey="approval" state={state} onToggle={toggle} align="right" title="Would have the instructor back">Approval</SortButton>}
          <SortButton sortKey="score" state={state} onToggle={toggle}>Score</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((r) => (
          <ClickRow key={r.id} href={r.href} active={activeId === r.id}>
            {show.week && <TableNum className="text-muted-foreground">{r.week ?? "—"}</TableNum>}
            {show.module !== false && (
              <TableCell className="max-w-64">
                {r.moduleHref ? (
                  <Link href={r.moduleHref} className="hover:text-primary block truncate font-medium" title={r.module}>
                    {r.module}
                  </Link>
                ) : (
                  <span className="block truncate font-medium" title={r.module}>
                    {r.module}
                  </span>
                )}
              </TableCell>
            )}
            {show.cohort && (
              <TableCell className="text-muted-foreground max-w-56">
                {r.cohortHref ? (
                  <Link href={r.cohortHref} className="hover:text-primary block truncate" title={r.cohort}>
                    {r.cohort ?? "—"}
                  </Link>
                ) : (
                  <span className="block truncate" title={r.cohort}>
                    {r.cohort ?? "—"}
                  </span>
                )}
              </TableCell>
            )}
            <TableCell className="text-muted-foreground whitespace-nowrap" data-numeric>
              {r.dateLabel}
            </TableCell>
            {kind && (
              <TableCell>
                <KindChip kind={r.kind} />
              </TableCell>
            )}
            <TableCell className="max-w-44">
              {r.instructorHref ? (
                <Link href={r.instructorHref} className="hover:text-primary block truncate" title={r.instructor}>
                  {r.instructor}
                </Link>
              ) : (
                <span className="block truncate" title={r.instructor}>
                  {r.instructor}
                </span>
              )}
            </TableCell>
            <TableNum>
              <RawStat rating={r.rating} rated={r.rated} attended={r.attended} />
            </TableNum>
            {show.attended && <TableNum className="text-muted-foreground">{r.attended ?? "—"}</TableNum>}
            <TableNum className={cn(r.reach != null && r.reach < 40 ? "text-destructive font-medium" : "text-muted-foreground")}>{r.reach == null ? "—" : `${Math.round(r.reach)}%`}</TableNum>
            {show.approval && <TableNum className={cn(r.approval != null && r.approval < 80 ? "text-destructive font-semibold" : "text-muted-foreground")}>{r.approval == null ? "—" : `${Math.round(r.approval)}%`}</TableNum>}
            <TableCell className="py-1.5">
              <ScorePill variant="sm" score={r.pill.score} band={r.pill.band} provisional={r.pill.provisional} action={r.pill.action} breakdown={{ rows: r.pill.rows, reason: r.pill.reason, version: r.pill.version }} />
            </TableCell>
          </ClickRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
