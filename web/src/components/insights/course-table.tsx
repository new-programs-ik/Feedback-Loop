"use client";

import * as React from "react";
import Link from "next/link";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { cn } from "@/lib/utils";

/** A slim view-model row: the page computes it on the server, this table only sorts it. */
export type CourseRow = {
  key: string;
  name: string;
  href: string | null;
  n: number;
  avgScore: number | null;
  counts: { excellent: number; good: number; average: number; bad: number };
  avgRating: number | null;
  avgAttended: number | null;
  /** Pooled share who would have the instructor back (0–100). */
  approval: number | null;
  /** Average share of the room that rated (0–100). */
  reach: number | null;
  /** Share of banded classes shown Bad (0–100). */
  badPct: number | null;
};

type Key = "name" | "n" | "score" | "rating" | "attended" | "approval" | "reach" | "bad";

const SPEC: SortSpec<CourseRow, Key> = {
  name: { value: (r) => r.name, first: "asc" },
  n: { value: (r) => r.n, first: "desc" },
  score: { value: (r) => r.avgScore, first: "desc" },
  rating: { value: (r) => r.avgRating, first: "desc" },
  attended: { value: (r) => r.avgAttended, first: "desc" },
  approval: { value: (r) => r.approval, first: "desc" },
  reach: { value: (r) => r.reach, first: "desc" },
  bad: { value: (r) => r.badPct, first: "desc" },
};

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));
const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);
const fmtInt = (v: number | null) => (v == null ? "—" : String(Math.round(v)));

/** Every course with enough rated classes, sortable by any column; the row's name links to the
 *  course workspace. Worst Bad share first by default. */
export function CourseTable({ rows, teamBadPct, className }: { rows: CourseRow[]; teamBadPct: number | null; className?: string }) {
  // The explicit type arguments keep `K` at the full key union — a literal `initial` would narrow it.
  const { sorted, state, toggle } = useSortable<CourseRow, Key>(rows, SPEC, { key: "bad", dir: "desc" });
  const head = (key: Key, label: string, align: "left" | "right" = "right", title?: string) => (
    <SortButton sortKey={key} state={state} onToggle={toggle} align={align} title={title}>
      {label}
    </SortButton>
  );
  return (
    <div className={cn("bg-card shadow-soft overflow-hidden rounded-xl border", className)}>
      <Table density="compact">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {head("name", "Course", "left")}
            {head("n", "Classes")}
            {head("score", "Avg score")}
            <TableHead className="min-w-28">Band mix</TableHead>
            {head("rating", "Avg rating")}
            {head("attended", "In the room", "right", "Sort by average learners attended")}
            {head("approval", "Approval", "right", "Sort by the share who would have the instructor back")}
            {head("reach", "Reach", "right", "Sort by the share of the room that rated")}
            {head("bad", "Bad share")}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((c) => {
            const worse = c.badPct != null && teamBadPct != null && c.badPct > teamBadPct;
            return (
              <TableRow key={c.key}>
                <TableCell className="max-w-56 truncate font-medium" title={c.name}>
                  {c.href ? (
                    <Link href={c.href} className="hover:text-primary transition-colors">
                      {c.name}
                    </Link>
                  ) : (
                    c.name
                  )}
                </TableCell>
                <TableNum className="text-muted-foreground">{c.n.toLocaleString()}</TableNum>
                <TableCell className="text-right">
                  <AvgScorePill score={c.avgScore} />
                </TableCell>
                <TableCell>
                  <BandStripOf counts={c.counts} height="h-1.5" className="min-w-24" />
                </TableCell>
                <TableNum className={cn(c.avgRating != null && c.avgRating < 4.55 && "text-destructive font-semibold")}>{fmtAvg(c.avgRating)}</TableNum>
                <TableNum className="text-muted-foreground">{fmtInt(c.avgAttended)}</TableNum>
                <TableNum className={cn(c.approval != null && c.approval < 80 && "text-destructive font-semibold")}>{fmtPct(c.approval)}</TableNum>
                <TableNum className="text-muted-foreground">{fmtPct(c.reach)}</TableNum>
                <TableNum>
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-px text-[11px] font-semibold",
                      c.badPct == null ? "text-muted-foreground" : worse ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success",
                    )}
                  >
                    {fmtPct(c.badPct)}
                  </span>
                </TableNum>
              </TableRow>
            );
          })}
          {sorted.length === 0 && (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={9} className="text-muted-foreground py-6 text-center">
                No course has reached 10 rated classes in this window yet.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
