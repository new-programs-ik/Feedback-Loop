"use client";

import * as React from "react";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DATE_WORDS, NAME_WORDS, SortControl, type SortOption } from "@/components/ui/sort-control";
import { sortRows, type SortSpec, type SortState } from "@/components/ui/sortable";

/** A queue row's sort values; the row itself (`row`) is rendered on the server and comes along. */
export type QueueSortRow = {
  id: string;
  score: number | null;
  date: string;
  rating: number;
  /** Share of the room that rated, 0–100. */
  reach: number | null;
  instructor: string;
  row: React.ReactNode;
};

type Key = "score" | "date" | "rating" | "reach" | "instructor";

const SPEC: SortSpec<QueueSortRow, Key> = {
  score: { value: (r) => r.score, first: "asc" },
  date: { value: (r) => r.date, first: "desc" },
  rating: { value: (r) => r.rating, first: "asc" },
  reach: { value: (r) => r.reach, first: "asc" },
  instructor: { value: (r) => r.instructor, first: "asc" },
};

/** Worst first is the queue's whole point, so every number opens low → high. */
const OPTIONS: SortOption<Key>[] = [
  { key: "score", label: "Score", first: "asc" },
  { key: "date", label: "Date", first: "desc", words: DATE_WORDS },
  { key: "rating", label: "Rating", first: "asc" },
  { key: "reach", label: "Reach", first: "asc" },
  { key: "instructor", label: "Instructor", first: "asc", words: NAME_WORDS },
];

const DEFAULT: SortState<Key> = { key: "score", dir: "asc" };

type Ctx = { state: SortState<Key>; setState: (next: SortState<Key>) => void };
const QueueSortContext = React.createContext<Ctx | null>(null);

/** One queue section's sort order. Wrap the section in it, put `QueueSortControl` in the
 *  section's header and `QueueRows` in its body — the section itself stays server-rendered. */
export function QueueSort({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<SortState<Key>>(DEFAULT);
  const value = React.useMemo(() => ({ state, setState }), [state]);
  return <QueueSortContext.Provider value={value}>{children}</QueueSortContext.Provider>;
}

function useQueueSort(): Ctx {
  const ctx = React.useContext(QueueSortContext);
  if (!ctx) throw new Error("QueueSortControl and QueueRows must sit inside a QueueSort.");
  return ctx;
}

/** Score · Date · Rating · Reach · Instructor, plus the direction. */
export function QueueSortControl({ className }: { className?: string }) {
  const { state, setState } = useQueueSort();
  return <SortControl options={OPTIONS} state={state} onChange={setState} className={className} />;
}

/** The section's rows in its current order. `header` draws the column headings (the Watch list
 *  has none). Only the order is decided here — each row is a server-rendered `QueueRow`. */
export function QueueRows({ rows, header = true }: { rows: QueueSortRow[]; header?: boolean }) {
  const { state } = useQueueSort();
  const sorted = React.useMemo(() => sortRows(rows, SPEC, state), [rows, state]);
  return (
    <Table>
      {header && (
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-24">Score</TableHead>
            <TableHead>Class</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
      )}
      <TableBody>
        {sorted.map((r) => (
          <React.Fragment key={r.id}>{r.row}</React.Fragment>
        ))}
      </TableBody>
    </Table>
  );
}
