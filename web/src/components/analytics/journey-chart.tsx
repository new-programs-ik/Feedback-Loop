"use client";

import * as React from "react";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart, type LineSeries } from "@/components/charts/line-chart";
import { SERIES } from "@/components/charts/chart-kit";
import { Segmented } from "@/components/analytics/segmented";
import { Empty } from "@/components/analytics/ui";
import { RATING_LINE } from "@/lib/curriculum";

/** One metric (the room, or the rating) along the course for a handful of cohorts, with the
 *  median of every cohort in bold. The x axis is the curriculum (module by module) or the
 *  cohort week — a toggle in the card's corner swaps them without a round trip. */

export type JourneyAxisProps = {
  labels: string[];
  names: (string | null)[];
  notes: (string | null)[];
  cohorts: { key: string; name: string; values: (number | null)[] }[];
  median: (number | null)[];
};

const COHORT_COLORS = [...SERIES, "var(--chart-seq-2)", "var(--chart-seq-5)"];

export function JourneyChart({
  title,
  subtitle,
  metric,
  byModule,
  byWeek,
  medianOf,
  height = 260,
}: {
  title: string;
  subtitle?: string;
  metric: "attended" | "rating";
  byModule: JourneyAxisProps;
  byWeek: JourneyAxisProps;
  /** How many cohorts the median line summarises. */
  medianOf: number;
  height?: number;
}) {
  const [axis, setAxis] = React.useState<"module" | "week">("module");
  const data = axis === "module" ? byModule : byWeek;
  const medianName = `Median of ${medianOf}`;
  const series: LineSeries[] = [
    ...data.cohorts.map((c, i) => ({ name: c.name, values: c.values, color: COHORT_COLORS[i % COHORT_COLORS.length], width: 1.5, opacity: 0.6 })),
    { name: medianName, values: data.median, color: "var(--foreground)", width: 2.5 },
  ];
  const legend = series.map((s) => ({ label: s.name, color: s.color! }));
  const all = series.flatMap((s) => s.values).filter((v): v is number => v != null);
  const max = all.length ? Math.max(...all) : 0;
  const decimals = metric === "attended" ? 0 : 2;
  const fmt = (v: number | null) => (v == null ? "—" : v.toFixed(decimals));
  return (
    <ChartCard
      title={title}
      subtitle={subtitle}
      legend={legend}
      actions={
        <Segmented
          size="sm"
          ariaLabel="X axis"
          value={axis}
          onChange={setAxis}
          options={[
            { value: "module", label: "By module", title: "Modules in curriculum order" },
            { value: "week", label: "By week", title: "Weeks since each cohort's first class" },
          ]}
        />
      }
      table={{
        headers: [axis === "module" ? "Module" : "Week", ...data.cohorts.map((c) => c.name), medianName],
        rows: data.labels.map((l, i) => [data.names[i] ?? l, ...data.cohorts.map((c) => fmt(c.values[i])), fmt(data.median[i])]),
      }}
    >
      {all.length === 0 || data.labels.length === 0 ? (
        <Empty className="px-2">No {metric === "attended" ? "attendance" : "rating"} recorded along this axis yet.</Empty>
      ) : (
        <LineChart
          labels={data.labels}
          series={series}
          xAnnotations={axis === "module" ? data.notes : undefined}
          tooltipTitles={data.names}
          labelStep={data.labels.length <= 12 ? 1 : undefined}
          yDomain={metric === "attended" ? [0, Math.max(10, Math.ceil((max * 1.1) / 5) * 5)] : undefined}
          threshold={metric === "rating" ? RATING_LINE : undefined}
          thresholdLabel={metric === "rating" ? `${RATING_LINE} line` : undefined}
          decimals={decimals}
          endLabels={data.cohorts.length <= 4}
          height={height}
        />
      )}
    </ChartCard>
  );
}
