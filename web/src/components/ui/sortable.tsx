"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

/** Client-side sorting for any data table.
 *
 *  A page computes slim view-model rows on the server and hands them to a small client table;
 *  the table declares how each column reads a comparable value (`SortSpec`) and which direction
 *  a first click uses (numbers usually "desc" — the big ones first; names "asc"). `useSortable`
 *  keeps the state; `SortButton` draws the header the same way the URL-driven `SortHead` does, so
 *  a sortable column looks identical everywhere: darker when active, a chevron that flips for
 *  ascending, a faint chevron always, stronger on hover, so the affordance is visible. Nulls always sort last. */

export type SortDir = "asc" | "desc";
export type SortValue = number | string | boolean | null | undefined;
export type SortState<K extends string = string> = { key: K; dir: SortDir };
export type SortSpec<T, K extends string = string> = Record<K, { value: (row: T) => SortValue; first?: SortDir }>;

export function compareValues(a: SortValue, b: SortValue, dir: SortDir): number {
  const an = a == null || a === "" || (typeof a === "number" && Number.isNaN(a));
  const bn = b == null || b === "" || (typeof b === "number" && Number.isNaN(b));
  if (an && bn) return 0;
  if (an) return 1; // nulls last, whatever the direction
  if (bn) return -1;
  let c: number;
  if (typeof a === "number" && typeof b === "number") c = a - b;
  else if (typeof a === "boolean" && typeof b === "boolean") c = Number(a) - Number(b);
  else c = String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
  return dir === "asc" ? c : -c;
}

export function sortRows<T, K extends string>(rows: T[], spec: SortSpec<T, K>, state: SortState<K> | null): T[] {
  if (!state || !spec[state.key]) return rows;
  const read = spec[state.key].value;
  return rows
    .map((row, i) => ({ row, i, v: read(row) }))
    .sort((x, y) => compareValues(x.v, y.v, state.dir) || x.i - y.i) // stable
    .map((x) => x.row);
}

export function useSortable<T, K extends string>(rows: T[], spec: SortSpec<T, K>, initial: SortState<NoInfer<K>> | null = null) {
  const [state, setState] = React.useState<SortState<K> | null>(initial);
  const toggle = React.useCallback(
    (key: K) =>
      setState((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: spec[key]?.first ?? "asc" })),
    [spec],
  );
  const sorted = React.useMemo(() => sortRows(rows, spec, state), [rows, spec, state]);
  return { sorted, state, toggle };
}

/** A sortable header cell for client tables — a button, not a link. */
export function SortButton<K extends string>({
  sortKey,
  state,
  onToggle,
  align = "left",
  className,
  title,
  children,
}: {
  sortKey: K;
  state: SortState<K> | null;
  onToggle: (key: K) => void;
  align?: "left" | "right";
  className?: string;
  title?: string;
  children: React.ReactNode;
}) {
  const active = state?.key === sortKey;
  const dir = active ? state!.dir : undefined;
  return (
    <TableHead aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"} className={cn(align === "right" && "text-right", className)}>
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        title={title ?? `Sort by ${typeof children === "string" ? children.toLowerCase() : "this column"}`}
        className={cn(
          "group/sort -mx-1 inline-flex items-center gap-1 rounded-sm px-1 transition-colors duration-150",
          "hover:text-foreground focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
          active && "text-foreground font-semibold",
          align === "right" && "flex-row-reverse",
        )}
      >
        <span>{children}</span>
        <ChevronDown
          aria-hidden
          className={cn(
            "size-3 shrink-0 transition-[opacity,transform] duration-200 ease-out",
            active ? cn("text-primary opacity-100", dir === "asc" && "rotate-180") : "opacity-35 group-hover/sort:opacity-80 group-focus-visible/sort:opacity-80",
          )}
        />
      </button>
    </TableHead>
  );
}
