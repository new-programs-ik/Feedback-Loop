"use client";

import * as React from "react";
import Link from "next/link";
import { TableBody, TableCell, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { AvgScorePill } from "@/components/analytics/score";
import { DataTable, Delta } from "@/components/analytics/ui";
import { BAND_META } from "@/lib/sentiment";
import { RATING_LINE, type Verdict } from "@/lib/curriculum";
import { cn } from "@/lib/utils";

/** Who taught one module and how it went for each of them — the "who should teach this next
 *  time" table. Sortable; the verdict chip says who lifts the module and who struggles. */

export type ModuleInstructorRow = {
  key: string;
  name: string;
  href: string;
  n: number;
  avgScore: number | null;
  rating: number | null;
  attended: number | null;
  reach: number | null;
  /** Their rating minus the module's average. */
  delta: number | null;
  verdict: Verdict;
  approval: number | null;
};

type Key = "name" | "n" | "score" | "rating" | "attended" | "reach" | "delta" | "approval";

const SPEC: SortSpec<ModuleInstructorRow, Key> = {
  name: { value: (r) => r.name, first: "asc" },
  n: { value: (r) => r.n, first: "desc" },
  score: { value: (r) => r.avgScore, first: "desc" },
  rating: { value: (r) => r.rating, first: "desc" },
  attended: { value: (r) => r.attended, first: "desc" },
  reach: { value: (r) => r.reach, first: "desc" },
  delta: { value: (r) => r.delta, first: "desc" },
  approval: { value: (r) => r.approval, first: "desc" },
};

export function VerdictChip({ verdict, n }: { verdict: Verdict; n?: number }) {
  if (!verdict) return n != null && n < 2 ? <span className="text-muted-foreground text-[10.5px]">one class</span> : null;
  const band = verdict === "lifts" ? "excellent" : "bad";
  return (
    <span className="inline-flex items-center rounded px-1.5 py-px text-[10.5px] font-semibold" style={{ background: BAND_META[band].soft, color: BAND_META[band].text }} title={verdict === "lifts" ? "At least 0.15 above the module's average, two or more classes" : "At least 0.15 under the module's average, two or more classes"}>
      {verdict}
    </span>
  );
}

export function ModuleInstructorTable({ rows, moduleAvg }: { rows: ModuleInstructorRow[]; moduleAvg: number | null }) {
  const { sorted, state, toggle } = useSortable(rows, SPEC, { key: "rating", dir: "desc" });
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" state={state} onToggle={toggle}>Instructor</SortButton>
          <SortButton sortKey="n" state={state} onToggle={toggle} align="right">Classes</SortButton>
          <SortButton sortKey="score" state={state} onToggle={toggle}>Avg score</SortButton>
          <SortButton sortKey="rating" state={state} onToggle={toggle} align="right" title="Average rating (1–5)">Rating</SortButton>
          <SortButton sortKey="attended" state={state} onToggle={toggle} align="right" title="Learners in the room per class">Attended</SortButton>
          <SortButton sortKey="reach" state={state} onToggle={toggle} align="right" title="Share of the room that rated">Reach</SortButton>
          <SortButton sortKey="delta" state={state} onToggle={toggle} align="right" title={moduleAvg != null ? `Against the module's ${moduleAvg.toFixed(2)} average` : "Against the module's average"}>vs module avg</SortButton>
          <SortButton sortKey="approval" state={state} onToggle={toggle} align="right">Approval</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((i) => (
          <TableRow key={i.key} className="relative">
            <TableCell className="max-w-48">
              <Link href={i.href} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={i.name}>
                {i.name}
              </Link>
            </TableCell>
            <TableNum className="text-muted-foreground">{i.n}</TableNum>
            <TableCell>
              <AvgScorePill score={i.avgScore} />
            </TableCell>
            <TableNum className={cn("font-num font-semibold", i.rating != null && i.rating < RATING_LINE ? "text-destructive" : "")}>{i.rating == null ? "—" : i.rating.toFixed(2)}</TableNum>
            <TableNum className="text-muted-foreground">{i.attended == null ? "—" : Math.round(i.attended)}</TableNum>
            <TableNum className="text-muted-foreground">{i.reach == null ? "—" : `${Math.round(i.reach)}%`}</TableNum>
            <TableNum>
              <span className="inline-flex items-center justify-end gap-1.5">
                {i.delta == null ? <span className="text-muted-foreground">—</span> : <Delta value={i.delta} decimals={2} />}
                <VerdictChip verdict={i.verdict} n={i.n} />
              </span>
            </TableNum>
            <TableNum className={cn(i.approval != null && i.approval < 80 ? "text-destructive font-semibold" : "text-muted-foreground")}>{i.approval == null ? "—" : `${Math.round(i.approval)}%`}</TableNum>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
