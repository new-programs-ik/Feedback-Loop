"use client";

import * as React from "react";
import Link from "next/link";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { Sparkline } from "@/components/charts/sparkline";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { DataTable } from "@/components/analytics/ui";
import { BAND_META } from "@/lib/sentiment";
import { RATING_LINE, ratioBand, type BandCounts } from "@/lib/curriculum";
import { cn } from "@/lib/utils";

/** Every cohort of the course, sortable by any number: the score stays the headline, the raw
 *  numbers (rating, room, reach, retention) sit beside it. The page hands slim rows over. */

export type CohortRow = {
  key: string;
  name: string;
  href: string;
  trackLabel: string;
  region: string | null;
  startLabel: string;
  /** ISO date of the first class — what "Start" sorts by. */
  start: string;
  weekNow: number;
  weeksTotal: number;
  active: boolean;
  n: number;
  avgScore: number | null;
  counts: BandCounts;
  avgRating: number | null;
  avgAttended: number | null;
  avgReach: number | null;
  retention: number | null;
  size: number | null;
  /** Room size module by module — the row's sparkline. */
  spark: number[];
};

type Key = "name" | "track" | "start" | "week" | "n" | "score" | "rating" | "attended" | "reach" | "retention";

const SPEC: SortSpec<CohortRow, Key> = {
  name: { value: (r) => r.name, first: "asc" },
  track: { value: (r) => r.trackLabel, first: "asc" },
  start: { value: (r) => r.start, first: "desc" },
  week: { value: (r) => r.weekNow, first: "desc" },
  n: { value: (r) => r.n, first: "desc" },
  score: { value: (r) => r.avgScore, first: "desc" },
  rating: { value: (r) => r.avgRating, first: "desc" },
  attended: { value: (r) => r.avgAttended, first: "desc" },
  reach: { value: (r) => r.avgReach, first: "desc" },
  retention: { value: (r) => r.retention, first: "desc" },
};

export function RetentionCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-muted-foreground">—</span>;
  const band = ratioBand(value);
  return (
    <span className="inline-flex items-center rounded px-1.5 py-px text-[11px] font-semibold" style={band ? { background: BAND_META[band].soft, color: BAND_META[band].text } : undefined} data-numeric>
      {Math.round(value * 100)}%
    </span>
  );
}

export function CohortTable({ rows, showTrack = false }: { rows: CohortRow[]; showTrack?: boolean }) {
  const { sorted, state, toggle } = useSortable(rows, SPEC, { key: "start", dir: "desc" });
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" state={state} onToggle={toggle}>Cohort</SortButton>
          {showTrack && <SortButton sortKey="track" state={state} onToggle={toggle}>Track</SortButton>}
          <SortButton sortKey="start" state={state} onToggle={toggle}>Start</SortButton>
          <SortButton sortKey="week" state={state} onToggle={toggle} align="right">Week</SortButton>
          <SortButton sortKey="n" state={state} onToggle={toggle} align="right">Classes</SortButton>
          <SortButton sortKey="score" state={state} onToggle={toggle}>Avg score</SortButton>
          <TableHead>Band mix</TableHead>
          <SortButton sortKey="rating" state={state} onToggle={toggle} align="right" title="Average rating (1–5)">Avg rating</SortButton>
          <SortButton sortKey="attended" state={state} onToggle={toggle} align="right" title="Learners in the room per class">Avg attended</SortButton>
          <SortButton sortKey="reach" state={state} onToggle={toggle} align="right" title="Share of the room that rated">Rated / attended</SortButton>
          <SortButton sortKey="retention" state={state} onToggle={toggle} align="right" title="Last module's room over the first module's room">Retention</SortButton>
          <TableHead title="Room size module by module">Attendance</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((c) => (
          <TableRow key={c.key} className="relative">
            <TableCell className="max-w-72">
              <Link href={c.href} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={c.name}>
                {c.name}
              </Link>
              <span className="text-muted-foreground block text-[10.5px]">
                {c.region ?? ""}
                {c.region && c.size != null ? " · " : ""}
                {c.size != null ? `${c.size} learners` : ""}
                {c.active ? " · running" : ""}
              </span>
            </TableCell>
            {showTrack && <TableCell className="text-muted-foreground">{c.trackLabel}</TableCell>}
            <TableCell className="text-muted-foreground whitespace-nowrap">{c.startLabel}</TableCell>
            <TableNum>
              {Math.min(c.weekNow, 99)} <span className="text-muted-foreground">of {c.weeksTotal}</span>
            </TableNum>
            <TableNum className="text-muted-foreground">{c.n}</TableNum>
            <TableCell>
              <AvgScorePill score={c.avgScore} />
            </TableCell>
            <TableCell>
              <BandStripOf counts={c.counts} className="w-20" />
            </TableCell>
            <TableNum className={cn("font-num font-semibold", c.avgRating != null && c.avgRating < RATING_LINE ? "text-destructive" : "")}>{c.avgRating == null ? "—" : c.avgRating.toFixed(2)}</TableNum>
            <TableNum className="text-muted-foreground">{c.avgAttended == null ? "—" : Math.round(c.avgAttended)}</TableNum>
            <TableNum className="text-muted-foreground">{c.avgReach == null ? "—" : `${Math.round(c.avgReach)}%`}</TableNum>
            <TableNum>
              <RetentionCell value={c.retention} />
            </TableNum>
            <TableCell>{c.spark.length >= 2 ? <Sparkline values={c.spark} width={84} /> : <span className="text-muted-foreground">—</span>}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
