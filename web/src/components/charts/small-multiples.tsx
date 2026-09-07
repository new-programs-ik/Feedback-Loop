"use client";

import * as React from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { curveMonotoneX, line as d3Line } from "d3-shape";
import { cn } from "@/lib/utils";
import { clamp, scaleLinear } from "./chart-kit";
import { DRAW, leaveUnlessTouch, useChartPlay } from "./chart-motion";

export type SmallMultipleItem = {
  key: string;
  title: string;
  subtitle?: string;
  href?: string;
  /** Right-hand value shown in the panel header (pre-formatted). */
  headline?: string;
  values: (number | null)[];
  /** A grey dashed comparison line (previous cohorts, the course average…). */
  reference?: (number | null)[];
  accent?: string;
};

export type SmallMultipleBand = { from: number; to: number; color: string };

/** A grid of mini line charts on ONE shared axis — the honest way to compare 6–8 cohorts or
 *  courses. Each panel: title (a link when given), the headline value, the line, an optional
 *  reference, the shared band zones. Lines draw in once; hover shows the value at the nearest
 *  x in the panel's header, so the comparison stays readable at 375px. */
export function SmallMultiples({
  items,
  labels,
  yDomain,
  bands,
  height = 72,
  minWidth = 180,
  decimals = 0,
  unit = "",
  accent = "var(--chart-1)",
  className,
}: {
  items: SmallMultipleItem[];
  labels: string[];
  yDomain?: [number, number];
  bands?: SmallMultipleBand[];
  height?: number;
  minWidth?: number;
  decimals?: number;
  unit?: string;
  accent?: string;
  className?: string;
}) {
  const gridRef = React.useRef<HTMLDivElement>(null);
  const { enter } = useChartPlay(gridRef, { amount: 0.15 });
  const all = items.flatMap((i) => [...i.values, ...(i.reference ?? [])]).filter((v): v is number => v != null);
  if (items.length === 0 || all.length === 0) return null;
  const lo = yDomain?.[0] ?? Math.min(...all);
  const hi = yDomain?.[1] ?? Math.max(...all);
  return (
    <div
      ref={gridRef}
      className={cn("grid gap-3", className)}
      style={{ gridTemplateColumns: `repeat(auto-fill, minmax(min(${minWidth}px, 100%), 1fr))` }}
    >
      {items.map((item, i) => (
        <Panel
          key={item.key}
          item={item}
          labels={labels}
          lo={lo}
          hi={hi}
          bands={bands}
          height={height}
          enter={enter}
          delay={i * 0.05}
          decimals={decimals}
          unit={unit}
          accent={item.accent ?? accent}
        />
      ))}
    </div>
  );
}

function Panel({
  item,
  labels,
  lo,
  hi,
  bands,
  height,
  enter,
  delay,
  decimals,
  unit,
  accent,
}: {
  item: SmallMultipleItem;
  labels: string[];
  lo: number;
  hi: number;
  bands?: SmallMultipleBand[];
  height: number;
  enter: boolean;
  delay: number;
  decimals: number;
  unit: string;
  accent: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<number | null>(null);
  const W = 240;
  const ml = 4;
  const mr = 4;
  const mt = 6;
  const mb = 6;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const n = labels.length;
  const xs = Array.from({ length: n }, (_, i) => (n === 1 ? ml + pw / 2 : ml + (i / (n - 1)) * pw));
  const y = scaleLinear([lo, hi], [mt + ph, mt]);
  const idx = xs.map((_, i) => i);
  const path = (vals: (number | null)[]) =>
    d3Line<number>()
      .defined((i) => vals[i] != null)
      .x((i) => xs[i])
      .y((i) => y(clamp(vals[i] as number, lo, hi)))
      .curve(curveMonotoneX)(idx) ?? "";
  let lastIdx = -1;
  item.values.forEach((v, i) => {
    if (v != null) lastIdx = i;
  });
  const indexAt = (clientX: number) => {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect || n < 2) return null;
    return clamp(Math.round(((clientX - rect.left) / rect.width) * (n - 1)), 0, n - 1);
  };
  const hv = hover == null ? null : item.values[hover];
  const hr = hover == null ? null : (item.reference?.[hover] ?? null);
  const fmt = (v: number) => v.toFixed(decimals) + unit;
  const summary = item.values.filter((v): v is number => v != null).map((v) => fmt(v)).join(", ");

  return (
    <div className="surface-inset rounded-lg border px-2.5 pt-2 pb-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          {item.href ? (
            <Link href={item.href} className="hover:text-primary block truncate text-[12px] font-semibold">
              {item.title}
            </Link>
          ) : (
            <span className="block truncate text-[12px] font-semibold">{item.title}</span>
          )}
          {item.subtitle && <span className="text-muted-foreground block truncate text-[10.5px]">{item.subtitle}</span>}
        </div>
        <span className="shrink-0 font-mono text-[11px] font-semibold" data-numeric>
          {hover != null ? (
            <span className="text-muted-foreground font-medium">
              {labels[hover]} · {hv == null ? "—" : fmt(hv)}
              {hr != null && <span className="opacity-70"> vs {fmt(hr)}</span>}
            </span>
          ) : (
            item.headline
          )}
        </span>
      </div>
      <div
        ref={ref}
        className="relative mt-1"
        onPointerMove={(e) => setHover(indexAt(e.clientX))}
        onPointerLeave={leaveUnlessTouch(() => setHover(null))}
      >
        <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" role="img" aria-label={`${item.title}: ${summary}`}>
          {bands?.map((b, i) => {
            const top = y(clamp(b.to, lo, hi));
            const bottom = y(clamp(b.from, lo, hi));
            return bottom - top < 1 ? null : <rect key={i} x={ml} y={top} width={pw} height={bottom - top} fill={b.color} fillOpacity={0.08} />;
          })}
          <line x1={ml} x2={ml + pw} y1={mt + ph} y2={mt + ph} stroke="var(--chart-grid)" strokeWidth={1} />
          {item.reference && (
            <motion.path
              d={path(item.reference)}
              fill="none"
              stroke="var(--muted-foreground)"
              strokeOpacity={0.55}
              strokeWidth={1.25}
              strokeDasharray="3 3"
              initial={false}
              animate={{ pathLength: enter ? [0, 1] : 1 }}
              transition={{ pathLength: { ...DRAW, delay } }}
            />
          )}
          <motion.path
            d={path(item.values)}
            fill="none"
            stroke={accent}
            strokeWidth={1.75}
            strokeLinejoin="round"
            strokeLinecap="round"
            initial={false}
            animate={{ pathLength: enter ? [0, 1] : 1 }}
            transition={{ pathLength: { ...DRAW, delay } }}
          />
          {lastIdx >= 0 && hover == null && (
            <circle cx={xs[lastIdx]} cy={y(clamp(item.values[lastIdx] as number, lo, hi))} r={3} fill={accent} stroke="var(--card)" strokeWidth={1.5} />
          )}
          {hover != null && (
            <>
              <line x1={xs[hover]} x2={xs[hover]} y1={mt} y2={mt + ph} stroke="var(--muted-foreground)" strokeOpacity={0.5} strokeWidth={1} />
              {hv != null && <circle cx={xs[hover]} cy={y(clamp(hv, lo, hi))} r={3.5} fill={accent} stroke="var(--card)" strokeWidth={1.5} />}
            </>
          )}
        </svg>
      </div>
    </div>
  );
}
