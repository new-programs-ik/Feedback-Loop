"use client";

import * as React from "react";

/** The study's signature figure: every class as a dot, rating (y) against a percentage (x) —
 *  participation by default, or the approval vote — with the 4.55 decision line, the vertical
 *  bar, and a shaded corner. Built for a few thousand points (no per-dot handlers or titles —
 *  the shape IS the message). */
export function ScatterChart({
  points, // [xPct, rating, isBad(0|1)][]
  threshold = 4.55,
  bar = 40,
  height = 380,
  xLabel = "share of attendees who rated the class",
  barLabel,
  lineLabel,
  cornerLabel,
  cornerSide = "right",
  ariaLabel = "Every class plotted by rating against participation. The cloud is flat — participation does not predict the rating.",
}: {
  points: [number, number, number][];
  threshold?: number;
  bar?: number;
  height?: number;
  xLabel?: string;
  barLabel?: string;
  lineLabel?: string;
  cornerLabel?: string;
  /** Which side of the bar the shaded corner sits on: right (≥ bar) or left (< bar). */
  cornerSide?: "right" | "left";
  ariaLabel?: string;
}) {
  const W = 720;
  const ml = 40;
  const mr = 14;
  const mt = 30;
  const mb = 40;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const x = (p: number) => ml + (Math.min(p, 100) / 100) * pw;
  const y = (r: number) => mt + ((5 - Math.max(Math.min(r, 5), 3)) / 2) * ph;
  const cornerX0 = cornerSide === "right" ? x(bar) : x(0);
  const cornerX1 = cornerSide === "right" ? x(100) : x(bar);
  const cornerMid = cornerSide === "right" ? x(bar + (100 - bar) / 2) : x(bar / 2);

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" role="img" aria-label={ariaLabel}>
      {/* grid */}
      {[3, 3.5, 4, 4.5, 5].map((r) => (
        <g key={r}>
          <line x1={ml} x2={W - mr} y1={y(r)} y2={y(r)} stroke="var(--chart-grid)" strokeWidth={1} strokeDasharray="1 3" />
          <text x={ml - 7} y={y(r) + 3} textAnchor="end" className="fill-muted-foreground/80 text-[9.5px]">{r.toFixed(1)}</text>
        </g>
      ))}
      {[0, 20, 40, 60, 80, 100].map((p) => (
        <text key={p} x={x(p)} y={height - 22} textAnchor="middle" className="fill-muted-foreground/80 text-[9.5px]">{p}%</text>
      ))}
      {/* the shaded corner: bad rating AND the bar's bad side */}
      <rect x={cornerX0} y={y(threshold)} width={cornerX1 - cornerX0} height={mt + ph - y(threshold)}
            fill="var(--viz-bad)" fillOpacity={0.06} />
      {/* decision line + bar */}
      <line x1={ml} x2={W - mr} y1={y(threshold)} y2={y(threshold)} stroke="var(--muted-foreground)" strokeWidth={1.5} strokeDasharray="5 4" />
      <text x={ml + 6} y={y(threshold) + 13} className="fill-muted-foreground text-[10px]">
        {lineLabel ?? `rating ${threshold} — below this we look`}
      </text>
      <line x1={x(bar)} x2={x(bar)} y1={mt} y2={mt + ph} stroke="var(--chart-1)" strokeWidth={1.5} />
      <text x={x(bar)} y={mt - 8} textAnchor="middle" className="fill-[var(--chart-1)] text-[10px] font-semibold">
        {barLabel ?? `${bar}% bar`}
      </text>
      <text x={cornerMid} y={y(3.15)} textAnchor="middle" className="fill-[var(--viz-bad)] text-[10px] font-medium">
        {cornerLabel ?? `below ${threshold} + representative sample → video`}
      </text>
      {/* dots */}
      {points.map(([p, r, bad], i) => (
        <circle key={i} cx={x(p)} cy={y(r)} r={2.4}
                fill={bad ? "var(--viz-bad)" : "var(--chart-1)"} fillOpacity={bad ? 0.55 : 0.28} />
      ))}
      <text x={ml + pw / 2} y={height - 6} textAnchor="middle" className="fill-muted-foreground text-[10.5px]">
        {xLabel}
      </text>
    </svg>
  );
}
