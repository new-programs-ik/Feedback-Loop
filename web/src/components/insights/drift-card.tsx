"use client";

import * as React from "react";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { cn } from "@/lib/utils";

export type DriftData = {
  labels: string[];
  rating: (number | null)[];
  underLine: (number | null)[];
  attended: (number | null)[];
  score: (number | null)[];
  /** The table twin, PRE-COMPUTED by the page (props must be serializable). */
  table: { headers: string[]; rows: (string | number)[][] };
};

type Measure = "under" | "rating" | "attended" | "score";
const SERIES_OF: Record<Measure, keyof Pick<DriftData, "underLine" | "rating" | "attended" | "score">> = { under: "underLine", rating: "rating", attended: "attended", score: "score" };

const MEASURES: { key: Measure; label: string; title: string; subtitle: string }[] = [
  { key: "under", label: "Under 4.55", title: "Share of classes rated under 4.55, by month", subtitle: "The line the score treats as hard · lower is better" },
  { key: "rating", label: "Avg rating", title: "Average rating, by month", subtitle: "Every rated class · the 4.55 line is where a class starts to need a look" },
  { key: "attended", label: "Class size", title: "Learners in the room, by month", subtitle: "Average attendance per class · a smaller room makes every rating count for more" },
  { key: "score", label: "Avg score", title: "Average Class Sentiment Score, by month", subtitle: "Under the active version · 75 and 90 are the Good and Excellent edges" },
];

/** One card, four lines: a segmented toggle swaps the measure without losing the reader's
 *  place. The chart remounts on each switch so it draws in again. */
export function DriftCard({ data, className }: { data: DriftData; className?: string }) {
  const [measure, setMeasure] = React.useState<Measure>("under");
  const m = MEASURES.find((x) => x.key === measure)!;
  const values = data[SERIES_OF[measure]];
  const finite = values.filter((v): v is number => v != null);
  const chart =
    measure === "under" ? (
      <LineChart labels={data.labels} series={[{ name: "Under 4.55", values }]} yDomain={[0, Math.max(10, Math.ceil((Math.max(...finite, 0) * 1.25) / 5) * 5)]} unit="%" decimals={0} area height={220} />
    ) : measure === "rating" ? (
      <LineChart labels={data.labels} series={[{ name: "Average rating", values }]} threshold={4.55} thresholdLabel="4.55 line" decimals={2} area height={220} />
    ) : measure === "attended" ? (
      <LineChart labels={data.labels} series={[{ name: "Learners in the room", values }]} decimals={0} area height={220} />
    ) : (
      <LineChart
        labels={data.labels}
        series={[{ name: "Average score", values }]}
        decimals={0}
        area
        height={220}
        bands={[
          { from: 75, to: 90, color: "var(--band-good)", label: "Good" },
          { from: 90, to: 100, color: "var(--band-excellent)", label: "Excellent" },
        ]}
      />
    );

  return (
    <ChartCard
      title={m.title}
      subtitle={m.subtitle}
      table={data.table}
      className={className}
      actions={
        <div role="group" aria-label="Measure" className="bg-muted/60 inline-flex rounded-md p-0.5" data-print-hide>
          {MEASURES.map((x) => (
            <button
              key={x.key}
              type="button"
              aria-pressed={x.key === measure}
              onClick={() => setMeasure(x.key)}
              className={cn(
                "rounded-[5px] px-2 py-0.5 text-[11px] font-medium whitespace-nowrap transition-colors duration-150",
                "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
                x.key === measure ? "bg-card text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {x.label}
            </button>
          ))}
        </div>
      }
    >
      <div key={measure}>{chart}</div>
    </ChartCard>
  );
}
