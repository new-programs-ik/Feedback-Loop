"use client";

import * as React from "react";
import Link from "next/link";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { DataTable, Delta } from "@/components/analytics/ui";
import { BAND_META } from "@/lib/sentiment";
import { RATING_LINE, type BandCounts } from "@/lib/curriculum";
import { cn } from "@/lib/utils";

/** Every module of the course in curriculum order, sortable: the score, then the raw numbers
 *  (rating, room, reach), how attendance and the rating move against the module before, and
 *  who teaches it best / struggles with it. */

export type ModuleRow = {
  key: string;
  name: string;
  href: string;
  order: number | null;
  orderLabel: string;
  tag: "content" | "delivery" | null;
  n: number;
  instructors: number;
  avgScore: number | null;
  counts: BandCounts;
  avgRating: number | null;
  avgAttended: number | null;
  avgReach: number | null;
  approval: number | null;
  /** Mean % change of the room against the cohort's previous module, and the cohorts behind it. */
  dropAttended: number | null;
  dropPairs: number;
  dropRating: number | null;
  best: { name: string; href: string; rating: number; n: number } | null;
  worst: { name: string; href: string; rating: number; n: number } | null;
};

type Key = "order" | "name" | "tag" | "n" | "instructors" | "score" | "rating" | "attended" | "reach" | "dropAttended" | "dropRating" | "approval" | "best" | "worst";

const SPEC: SortSpec<ModuleRow, Key> = {
  order: { value: (r) => r.order ?? 99, first: "asc" },
  name: { value: (r) => r.name, first: "asc" },
  tag: { value: (r) => r.tag, first: "asc" },
  n: { value: (r) => r.n, first: "desc" },
  instructors: { value: (r) => r.instructors, first: "desc" },
  score: { value: (r) => r.avgScore, first: "asc" },
  rating: { value: (r) => r.avgRating, first: "asc" },
  attended: { value: (r) => r.avgAttended, first: "desc" },
  reach: { value: (r) => r.avgReach, first: "desc" },
  dropAttended: { value: (r) => r.dropAttended, first: "asc" },
  dropRating: { value: (r) => r.dropRating, first: "asc" },
  approval: { value: (r) => r.approval, first: "asc" },
  best: { value: (r) => r.best?.rating, first: "desc" },
  worst: { value: (r) => r.worst?.rating, first: "asc" },
};

export function ModuleTag({ tag }: { tag: "content" | "delivery" | null }) {
  if (!tag) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="inline-flex items-center rounded border px-1.5 py-px text-[10.5px] font-medium"
      style={{ color: tag === "content" ? BAND_META.bad.text : BAND_META.average.text, borderColor: tag === "content" ? BAND_META.bad.color : BAND_META.average.color }}
      title={tag === "content" ? "Low across two or more instructors — the material" : "Low for one instructor, fine for the others — the delivery"}
    >
      {tag}
    </span>
  );
}

function Who({ who, avg, tone }: { who: ModuleRow["best"]; avg: number | null; tone: "lifts" | "struggles" }) {
  if (!who) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="flex min-w-0 flex-col leading-tight">
      <Link href={who.href} className="hover:text-primary relative z-[1] truncate font-medium" title={who.name}>
        {who.name}
      </Link>
      <span className="text-muted-foreground text-[10.5px] whitespace-nowrap" data-numeric>
        <span className={cn("font-semibold", tone === "lifts" ? "text-band-excellent-text" : "text-band-bad-text")}>{who.rating.toFixed(2)}</span>
        {avg != null ? ` vs ${avg.toFixed(2)}` : ""} · {who.n} {who.n === 1 ? "class" : "classes"}
      </span>
    </span>
  );
}

export function ModuleTable({ rows }: { rows: ModuleRow[] }) {
  const { sorted, state, toggle } = useSortable(rows, SPEC, { key: "order", dir: "asc" });
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="order" state={state} onToggle={toggle} align="right" title="Median cohort week the module is taught in">#</SortButton>
          <SortButton sortKey="name" state={state} onToggle={toggle}>Module</SortButton>
          <SortButton sortKey="tag" state={state} onToggle={toggle}>Tag</SortButton>
          <SortButton sortKey="n" state={state} onToggle={toggle} align="right">Classes</SortButton>
          <SortButton sortKey="instructors" state={state} onToggle={toggle} align="right" title="Instructors who taught it in the period">Instr.</SortButton>
          <SortButton sortKey="score" state={state} onToggle={toggle}>Avg score</SortButton>
          <TableHead>Band mix</TableHead>
          <SortButton sortKey="rating" state={state} onToggle={toggle} align="right" title="Average rating (1–5)">Avg rating</SortButton>
          <SortButton sortKey="attended" state={state} onToggle={toggle} align="right" title="Learners in the room per class">Avg attended</SortButton>
          <SortButton sortKey="reach" state={state} onToggle={toggle} align="right" title="Share of the room that rated">Reach</SortButton>
          <SortButton sortKey="dropAttended" state={state} onToggle={toggle} align="right" title="Attendance against each cohort's previous module">Δ attendance</SortButton>
          <SortButton sortKey="dropRating" state={state} onToggle={toggle} align="right" title="Rating against each cohort's previous module">Δ rating</SortButton>
          <SortButton sortKey="approval" state={state} onToggle={toggle} align="right">Approval</SortButton>
          <SortButton sortKey="best" state={state} onToggle={toggle} title="Highest rating on this module with two or more classes">Teaches it best</SortButton>
          <SortButton sortKey="worst" state={state} onToggle={toggle} title="At least 0.15 under the module's average with two or more classes">Struggles with it</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((t) => (
          <TableRow key={t.key} className="relative">
            <TableNum className="text-muted-foreground">{t.orderLabel}</TableNum>
            <TableCell className="max-w-72">
              <Link href={t.href} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={t.name}>
                {t.name}
              </Link>
            </TableCell>
            <TableCell>
              <ModuleTag tag={t.tag} />
            </TableCell>
            <TableNum className="text-muted-foreground">{t.n}</TableNum>
            <TableNum className="text-muted-foreground">{t.instructors}</TableNum>
            <TableCell>
              <AvgScorePill score={t.avgScore} />
            </TableCell>
            <TableCell>
              <BandStripOf counts={t.counts} className="w-20" />
            </TableCell>
            <TableNum className={cn("font-num font-semibold", t.avgRating != null && t.avgRating < RATING_LINE ? "text-destructive" : "")}>{t.avgRating == null ? "—" : t.avgRating.toFixed(2)}</TableNum>
            <TableNum className="text-muted-foreground">{t.avgAttended == null ? "—" : Math.round(t.avgAttended)}</TableNum>
            <TableNum className="text-muted-foreground">{t.avgReach == null ? "—" : `${Math.round(t.avgReach)}%`}</TableNum>
            <TableNum title={t.dropPairs >= 2 ? `Over ${t.dropPairs} cohorts` : "Needs two cohorts with the module before it"}>
              {t.dropAttended == null || t.dropPairs < 2 ? <span className="text-muted-foreground">—</span> : <Delta value={t.dropAttended} decimals={0} unit="%" />}
            </TableNum>
            <TableNum>{t.dropRating == null || t.dropPairs < 2 ? <span className="text-muted-foreground">—</span> : <Delta value={t.dropRating} decimals={2} />}</TableNum>
            <TableNum className={cn(t.approval != null && t.approval < 80 ? "text-destructive font-semibold" : "text-muted-foreground")}>{t.approval == null ? "—" : `${Math.round(t.approval)}%`}</TableNum>
            <TableCell className="max-w-48">
              <Who who={t.best} avg={t.avgRating} tone="lifts" />
            </TableCell>
            <TableCell className="max-w-48">
              <Who who={t.worst} avg={t.avgRating} tone="struggles" />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
