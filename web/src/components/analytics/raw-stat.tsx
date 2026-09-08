import * as React from "react";
import { cn } from "@/lib/utils";

/** The raw numbers behind a score, in one compact cell: the star rating, then rated / attended.
 *  The score says how a class went against the rule; these say what the room actually did —
 *  a 4.31 with 6 of 30 rating reads very differently from a 4.31 with 24 of 30. The rating turns
 *  red under the 4.55 line; the counts stay quiet. Tabular figures, so columns of them line up. */
export function RawStat({
  rating,
  rated,
  attended,
  line = 4.55,
  decimals = 2,
  className,
}: {
  rating: number | null | undefined;
  rated: number | null | undefined;
  attended: number | null | undefined;
  /** The rating line the team agreed; below it the rating is tinted. */
  line?: number | null;
  decimals?: number;
  className?: string;
}) {
  const low = rating != null && line != null && rating < line;
  return (
    <span className={cn("font-num inline-flex items-baseline gap-1.5 whitespace-nowrap", className)} data-numeric>
      <span className={cn("font-semibold", low ? "text-destructive" : "text-foreground")} title={`Average rating (1–5)${low ? ` · under the ${line} line` : ""}`}>
        {rating == null ? "—" : rating.toFixed(decimals)}
      </span>
      <span className="text-muted-foreground text-[11px]" title="learners who rated / learners who attended">
        {rated ?? "—"}
        <span className="opacity-60">/</span>
        {attended ?? "—"}
      </span>
    </span>
  );
}

/** The aggregate version: average rating · average attended · reach, for a cohort, module,
 *  instructor or course. `attended` is the average room size, `reach` the share that rated. */
export function RawAvg({
  rating,
  attended,
  reach,
  line = 4.55,
  className,
}: {
  rating: number | null | undefined;
  attended: number | null | undefined;
  reach?: number | null | undefined;
  line?: number | null;
  className?: string;
}) {
  const low = rating != null && line != null && rating < line;
  return (
    <span className={cn("font-num inline-flex items-baseline gap-1.5 whitespace-nowrap", className)} data-numeric>
      <span className={cn("font-semibold", low ? "text-destructive" : "text-foreground")} title="Average rating (1–5)">
        {rating == null ? "—" : rating.toFixed(2)}
      </span>
      <span className="text-muted-foreground text-[11px]" title="average learners attended per class">
        {attended == null ? "—" : Math.round(attended)} <span className="opacity-70">in the room</span>
      </span>
      {reach !== undefined && (
        <span className="text-muted-foreground text-[11px]" title="share of the room that rated">
          {reach == null ? "—" : `${Math.round(reach)}%`}
        </span>
      )}
    </span>
  );
}
