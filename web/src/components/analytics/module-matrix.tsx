"use client";

import * as React from "react";
import { MatrixHeatmap, type MatrixCell, type MatrixCol, type MatrixRow } from "@/components/charts/matrix-heatmap";
import { Segmented } from "@/components/analytics/segmented";
import { ratingBand, ratioBand } from "@/lib/curriculum";

/** Module × instructor with a metric toggle: the score band (default), the rating alone, or
 *  the room (tinted against the course's typical room). The count of classes stays put; the
 *  value and the tint change. */

export type MatrixPair = { row: string; col: string; n: number; score: number | null; rating: number | null; attended: number | null; note?: string };
type Metric = "score" | "rating" | "attendance";

export function ModuleMatrix({
  rows,
  cols,
  pairs,
  courseAvgAttended,
  rowHeader = "Module",
  minN = 2,
}: {
  rows: MatrixRow[];
  cols: MatrixCol[];
  pairs: MatrixPair[];
  /** The course's typical room — what an instructor's room is tinted against. */
  courseAvgAttended: number | null;
  rowHeader?: string;
  minN?: number;
}) {
  const [metric, setMetric] = React.useState<Metric>("score");
  const cells: MatrixCell[] = React.useMemo(
    () =>
      pairs.map((p) => {
        if (metric === "rating") return { row: p.row, col: p.col, n: p.n, value: p.rating, band: ratingBand(p.rating), note: p.note };
        if (metric === "attendance") {
          return { row: p.row, col: p.col, n: p.n, value: p.attended, band: ratioBand(p.attended != null && courseAvgAttended ? p.attended / courseAvgAttended : null), note: p.note };
        }
        return { row: p.row, col: p.col, n: p.n, value: p.score, note: p.note };
      }),
    [pairs, metric, courseAvgAttended],
  );
  const hint =
    metric === "score"
      ? "Tint = the score band"
      : metric === "rating"
        ? "Tint = the rating alone: 4.82+ · 4.55+ · 4.35+ · under"
        : courseAvgAttended != null
          ? `Tint = the room against the course's typical ${Math.round(courseAvgAttended)}: 90%+ · 75%+ · 60%+ · under`
          : "No typical room to tint against";
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 py-2" data-print-hide>
        <span className="text-muted-foreground text-[11px]">{hint}</span>
        <Segmented
          size="sm"
          ariaLabel="Value shown"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "rating", label: "Rating" },
            { value: "attendance", label: "Attendance" },
            { value: "score", label: "Score" },
          ]}
        />
      </div>
      <MatrixHeatmap
        rows={rows}
        cols={cols}
        cells={cells}
        rowHeader={rowHeader}
        valueLabel={metric === "score" ? "avg score" : metric === "rating" ? "avg rating" : "avg attended"}
        format={metric === "score" ? "score" : metric === "rating" ? "rating" : "int"}
        minN={minN}
      />
    </div>
  );
}
