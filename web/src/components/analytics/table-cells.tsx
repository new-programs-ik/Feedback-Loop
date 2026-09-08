import * as React from "react";
import Link from "next/link";
import { TableCell, TableNum } from "@/components/ui/table";
import { APPROVAL_BAR, GOOD } from "@/lib/decision";
import { cn } from "@/lib/utils";

/** Cells the sortable tables share, and the formatters they need — `@/lib/analytics` is
 *  server-only, so the client tables keep their own three one-liners. The rules are the team's:
 *  a rating under the 4.55 line and an approval under the 80% bar read red; the rest stays quiet. */

export const fmtPct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
export const fmtRating = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
export const prettyDate = (isoDate: string) => new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

/** Average rating (1–5), tabular; red under the line, like `RawStat`. */
export function RatingNum({ value, className }: { value: number | null | undefined; className?: string }) {
  const low = value != null && value < GOOD;
  return (
    <TableNum
      className={cn("font-num", low ? "text-destructive font-semibold" : value == null ? "text-muted-foreground" : "font-medium", className)}
      title={low ? `Average rating · under the ${GOOD} line` : "Average rating (1–5)"}
    >
      {fmtRating(value)}
    </TableNum>
  );
}

/** Average learners in the room, rounded. */
export function AttendedNum({ value, className }: { value: number | null | undefined; className?: string }) {
  return (
    <TableNum className={cn("text-muted-foreground", className)} title="Average learners attended per class">
      {value == null ? "—" : Math.round(value)}
    </TableNum>
  );
}

/** The share that would have the instructor back; red under the 80% bar. */
export function ApprovalNum({ value, className }: { value: number | null | undefined; className?: string }) {
  return <TableNum className={cn(value != null && value < APPROVAL_BAR && "text-destructive font-semibold", className)}>{fmtPct(value)}</TableNum>;
}

/** The share of the room that rated. */
export function ReachNum({ value, className }: { value: number | null | undefined; className?: string }) {
  return <TableNum className={cn("text-muted-foreground", className)}>{fmtPct(value)}</TableNum>;
}

/** The row's name: a link that covers the whole row (the row is `relative`), else plain text.
 *  Anything passed as children sits under the name in small type. */
export function NameCell({ href, name, className, children }: { href: string | null; name: string; className?: string; children?: React.ReactNode }) {
  return (
    <TableCell className={cn("max-w-56", className)}>
      {href ? (
        <Link href={href} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={name}>
          {name}
        </Link>
      ) : (
        <span className="block truncate font-medium" title={name}>
          {name}
        </span>
      )}
      {children}
    </TableCell>
  );
}
