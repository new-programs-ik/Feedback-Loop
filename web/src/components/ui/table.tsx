import * as React from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/** Data-table primitives. Server-safe (no client state) — sorting is done with `?sort=` links
 *  in the page, so tables stay fully server-rendered. Digits align via the global tabular-nums.
 *
 *  Row pattern: every TableRow is a `group/row` and carries `data-row-hover`; a TableActions cell
 *  sits at 70% and comes up to full on row hover / focus — actions are always discoverable, never
 *  hidden (touch devices see them at full strength). */

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
      data-row-hover=""
      className={cn(
        "group/row hover:bg-muted/40 data-[state=selected]:bg-muted/60 border-b transition-colors duration-150",
        className,
      )}
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

/** A sortable column header: a link that carries the sort key in the URL. The active column reads
 *  darker with a chevron that rises in (and flips for ascending); inactive columns show a ghost
 *  chevron on hover so the affordance is discoverable. `aria-sort` goes on the <th>. */
function SortHead({
  href,
  active,
  dir = "desc",
  align = "left",
  className,
  children,
}: {
  href: string;
  active: boolean;
  /** Direction the column sorts in when active. */
  dir?: "asc" | "desc";
  align?: "left" | "right";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <TableHead
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(align === "right" && "text-right", className)}
    >
      <Link
        href={href}
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
            active
              ? cn("animate-in-up text-primary opacity-100", dir === "asc" && "rotate-180")
              : "opacity-0 group-hover/sort:opacity-60 group-focus-visible/sort:opacity-60",
          )}
        />
      </Link>
    </TableHead>
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

/** The row's action slot: right-aligned, 70% until the row is hovered or focused within. */
function TableActions({ className, children, ...props }: React.ComponentProps<"td">) {
  return (
    <TableCell data-slot="table-actions" className={cn("text-right whitespace-nowrap", className)} {...props}>
      <div className="inline-flex items-center justify-end gap-1 opacity-70 transition-opacity duration-150 group-hover/row:opacity-100 group-focus-within/row:opacity-100 [@media(hover:none)]:opacity-100">
        {children}
      </div>
    </TableCell>
  );
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

export {
  Table, TableHeader, TableBody, TableRow, TableHead, SortHead, TableCell, TableNum, TableActions, Meter, BandDot,
};
