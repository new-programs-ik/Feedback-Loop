import * as React from "react";

/** 12-point-ish inline trend, per the stat-tile contract: quiet gray line, accent dot on the
 *  current period, no axes, no tooltip. Server-safe. */
export function Sparkline({
  values,
  width = 72,
  height = 24,
  accent = "var(--chart-1)",
}: {
  values: number[];
  width?: number;
  height?: number;
  accent?: string;
}) {
  const pts = values.filter((v) => Number.isFinite(v));
  if (pts.length < 2) return null;
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const pad = 3;
  const x = (i: number) => pad + (i / (pts.length - 1)) * (width - pad * 2);
  const y = (v: number) =>
    max === min ? height / 2 : height - pad - ((v - min) / (max - min)) * (height - pad * 2);
  const d = pts.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
      className="overflow-visible"
    >
      <path d={d} fill="none" stroke="var(--muted-foreground)" strokeOpacity={0.45} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(pts.length - 1)} cy={y(last)} r={2.5} fill={accent} stroke="var(--card)" strokeWidth={1.5} />
    </svg>
  );
}
