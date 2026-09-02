"use client";

import * as React from "react";
import { SERIES, niceTicks, scaleLinear } from "./chart-kit";

export type LineSeries = { name: string; values: (number | null)[] };

/** Trend lines (1-4 series) over shared categorical x labels.
 *  Dataviz spec: 2px round-join lines, ring-stroked end markers, crosshair snapped to the
 *  nearest x with ONE tooltip listing every series, hairline solid grid, one axis, optional
 *  threshold line (e.g. the 4.55 rating line). */
export function LineChart({
  labels,
  series,
  height = 240,
  yDomain,
  threshold,
  thresholdLabel,
  unit = "",
  area = false,
}: {
  labels: string[];
  series: LineSeries[];
  height?: number;
  yDomain?: [number, number];
  threshold?: number;
  thresholdLabel?: string;
  unit?: string;
  area?: boolean;
}) {
  const W = 720;
  const ml = 40;
  const mr = 16;
  const mt = 12;
  const mb = 28;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const [hover, setHover] = React.useState<number | null>(null);
  const wrapRef = React.useRef<HTMLDivElement>(null);

  const all = series.flatMap((s) => s.values).filter((v): v is number => v != null);
  if (all.length === 0 || labels.length === 0) return null;
  let lo = yDomain?.[0] ?? Math.min(...all, threshold ?? Infinity);
  let hi = yDomain?.[1] ?? Math.max(...all, threshold ?? -Infinity);
  const padY = (hi - lo || 1) * 0.12;
  lo = yDomain ? lo : lo - padY;
  hi = yDomain ? hi : hi + padY;
  const ticks = niceTicks(lo, hi, 4).filter((t) => t >= lo && t <= hi);
  const y = scaleLinear([lo, hi], [mt + ph, mt]);
  const x = (i: number) =>
    labels.length === 1 ? ml + pw / 2 : ml + (i / (labels.length - 1)) * pw;

  const path = (vals: (number | null)[]) => {
    let d = "";
    vals.forEach((v, i) => {
      if (v == null) return;
      d += `${d === "" ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    });
    return d;
  };

  const onMove = (e: React.MouseEvent) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((px - ml) / pw) * (labels.length - 1));
    setHover(Math.max(0, Math.min(labels.length - 1, i)));
  };

  // Every ~nth x label so ticks never crowd (dataviz axis-readability).
  const stepX = Math.max(1, Math.ceil(labels.length / 8));

  return (
    <div ref={wrapRef} className="relative" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" role="img">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ml} x2={W - mr} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={ml - 8} y={y(t) + 3.5} textAnchor="end" className="fill-muted-foreground text-[10px]">
              {t}{unit}
            </text>
          </g>
        ))}
        {labels.map((l, i) =>
          i % stepX === 0 ? (
            <text key={i} x={x(i)} y={height - 8} textAnchor="middle" className="fill-muted-foreground text-[10px]">
              {l}
            </text>
          ) : null,
        )}
        {threshold != null && (
          <g>
            <line x1={ml} x2={W - mr} y1={y(threshold)} y2={y(threshold)} stroke="var(--muted-foreground)" strokeWidth={1.5} strokeDasharray="5 4" />
            {thresholdLabel && (
              <text x={W - mr} y={y(threshold) - 5} textAnchor="end" className="fill-muted-foreground text-[10px]">
                {thresholdLabel}
              </text>
            )}
          </g>
        )}
        {area && series.length === 1 && (
          <path
            d={`${path(series[0].values)}L${x(labels.length - 1)},${y(lo)}L${x(0)},${y(lo)}Z`}
            fill={SERIES[0]}
            fillOpacity={0.08}
          />
        )}
        {hover != null && (
          <line x1={x(hover)} x2={x(hover)} y1={mt} y2={mt + ph} stroke="var(--muted-foreground)" strokeOpacity={0.4} strokeWidth={1} />
        )}
        {series.map((s, si) => (
          <path key={s.name} d={path(s.values)} fill="none" stroke={SERIES[si]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {series.map((s, si) => {
          let lastIdx = -1;
          s.values.forEach((v, i) => {
            if (v != null) lastIdx = i;
          });
          const lastVal = lastIdx >= 0 ? s.values[lastIdx] : null;
          if (lastVal == null) return null;
          return (
            <circle
              key={s.name}
              cx={x(lastIdx)}
              cy={y(lastVal)}
              r={4}
              fill={SERIES[si]}
              stroke="var(--card)"
              strokeWidth={2}
            />
          );
        })}
        {hover != null &&
          series.map((s, si) =>
            s.values[hover] != null ? (
              <circle key={s.name} cx={x(hover)} cy={y(s.values[hover]!)} r={4} fill={SERIES[si]} stroke="var(--card)" strokeWidth={2} />
            ) : null,
          )}
      </svg>
      {hover != null && (
        <div
          className="bg-popover text-popover-foreground shadow-soft pointer-events-none absolute z-10 rounded-lg border px-3 py-2 text-xs"
          style={{
            left: `${(x(hover) / W) * 100}%`,
            top: 0,
            transform: x(hover) > W * 0.7 ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
          }}
        >
          <div className="text-muted-foreground mb-1 font-medium">{labels[hover]}</div>
          {series.map(
            (s, si) =>
              s.values[hover] != null && (
                <div key={s.name} className="flex items-center gap-2">
                  <span className="h-0.5 w-3 rounded-full" style={{ background: SERIES[si] }} />
                  <span className="font-semibold" data-numeric>
                    {Number(s.values[hover]).toFixed(2)}
                  </span>
                  {series.length > 1 && <span className="text-muted-foreground">{s.name}</span>}
                </div>
              ),
          )}
        </div>
      )}
    </div>
  );
}
