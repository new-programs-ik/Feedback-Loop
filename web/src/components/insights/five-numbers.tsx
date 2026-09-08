import * as React from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

/** One cell of the five-number table: the number, a quiet line under it, an optional tone. */
export type StudyCell = { value: string; note?: string; tone?: "good" | "bad" | "muted" };

export type StudyMeasureRow = {
  key: string;
  label: string;
  /** What the measure means, in one line. */
  hint: string;
  v1: StudyCell;
  active: StudyCell;
  study: StudyCell;
};

const TONE: Record<NonNullable<StudyCell["tone"]>, string> = {
  good: "text-success",
  bad: "text-destructive",
  muted: "text-muted-foreground",
};

function Cell({ cell, emphasis = false }: { cell: StudyCell; emphasis?: boolean }) {
  return (
    <TableCell className="text-right align-top whitespace-nowrap" data-numeric>
      <span className={cn("block text-[15px] leading-tight font-semibold tracking-[-0.01em]", cell.tone && TONE[cell.tone], emphasis && !cell.tone && "text-foreground")}>
        {cell.value}
      </span>
      {cell.note && <span className="text-muted-foreground mt-0.5 block text-[11px] leading-snug">{cell.note}</span>}
    </TableCell>
  );
}

/** The study's five numbers, live: one row per measure, one column per version, and the
 *  offline study beside them so a reader can see the live database say the same thing the PDF
 *  said. Server-safe. */
export function FiveNumbers({
  rows,
  columns,
  className,
}: {
  rows: StudyMeasureRow[];
  columns: { v1: string; v1Note?: string; active: string; activeNote?: string; study: string; studyNote?: string };
  className?: string;
}) {
  return (
    <div className={cn("bg-card shadow-soft overflow-hidden rounded-xl border", className)}>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="min-w-52">Measure</TableHead>
            <TableHead className="text-right">
              <span className="block">{columns.v1}</span>
              {columns.v1Note && <span className="text-muted-foreground/80 block text-[10px] font-normal">{columns.v1Note}</span>}
            </TableHead>
            <TableHead className="text-foreground text-right">
              <span className="block">{columns.active}</span>
              {columns.activeNote && <span className="text-muted-foreground/80 block text-[10px] font-normal">{columns.activeNote}</span>}
            </TableHead>
            <TableHead className="text-right">
              <span className="block">{columns.study}</span>
              {columns.studyNote && <span className="text-muted-foreground/80 block text-[10px] font-normal">{columns.studyNote}</span>}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.key} className="align-top">
              <TableCell className="min-w-52 py-2.5 align-top">
                <span className="block text-[13px] font-medium">{r.label}</span>
                <span className="text-muted-foreground mt-0.5 block max-w-64 text-[11px] leading-snug">{r.hint}</span>
              </TableCell>
              <Cell cell={r.v1} />
              <Cell cell={r.active} emphasis />
              <Cell cell={r.study} />
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
