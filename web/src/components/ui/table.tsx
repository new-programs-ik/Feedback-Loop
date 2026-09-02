import * as React from "react";
import { cn } from "@/lib/utils";

/** Data-table primitives. Server-safe (no client state) — sorting is done with `?sort=` links
 *  in the page, so tables stay fully server-rendered. Digits align via the global tabular-nums. */

function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div data-slot="table-container" className="relative w-full overflow-x-auto">
      <table data-slot="table" className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={cn("[&_tr]:border-b", className)} {...props} />;
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody data-slot="table-body" className={cn("[&_tr:last-child]:border-0", className)} {...props} />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn("hover:bg-muted/40 border-b transition-colors", className)}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "text-muted-foreground/90 surface-inset h-9 border-b px-3 text-left align-middle text-[11px] font-medium whitespace-nowrap first:rounded-tl-none first:pl-4 last:pr-4",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn("h-11 px-3 py-2 align-middle text-[13px] first:pl-4 last:pr-4", className)}
      {...props}
    />
  );
}

/** Right-aligned numeric cell — use for every number column. */
function TableNum({ className, ...props }: React.ComponentProps<"td">) {
  return <TableCell className={cn("text-right whitespace-nowrap", className)} {...props} />;
}

/** Inline micro-meter: value against a max, as a 56px track. The quiet way to show a share
 *  in a table row without a loud percentage. */
function Meter({
  value,
  max = 100,
  color = "var(--chart-1)",
  className,
}: {
  value: number;
  max?: number;
  color?: string;
  className?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="bg-muted relative inline-block h-1.5 w-14 overflow-hidden rounded-full align-middle">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </span>
      <span className="text-[13px]" data-numeric>
        {Math.round(value)}%
      </span>
    </span>
  );
}

/** Small band dot: colors a value by threshold without coloring the text itself. */
function BandDot({ tone }: { tone: "good" | "warn" | "bad" }) {
  const bg = tone === "good" ? "var(--viz-good)" : tone === "warn" ? "var(--warning)" : "var(--viz-bad)";
  return <span aria-hidden className="mr-1.5 inline-block size-1.5 rounded-full align-middle" style={{ background: bg }} />;
}

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableNum, Meter, BandDot };
