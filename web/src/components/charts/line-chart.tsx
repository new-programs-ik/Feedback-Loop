"use client";

import * as React from "react";
import { motion, useMotionValue, useSpring } from "motion/react";
import { area as d3Area, curveMonotoneX, line as d3Line } from "d3-shape";
import { cn } from "@/lib/utils";
import { SERIES, clamp, estimateTextWidth, niceTicks, scaleLinear } from "./chart-kit";
import { useSeriesHidden } from "./chart-legend";
import { DRAW, POP, SNAP, leaveUnlessTouch, useChartPlay, useTapOutside } from "./chart-motion";
import { ChartTooltip, type TooltipRow } from "./chart-tooltip";

export type LineSeries = { name: string; values: (number | null)[] };
/** A shaded horizontal zone (e.g. the Bad band, 0–60). */
export type LineBand = { from: number; to: number; color: string; label?: string };
/** A vertical event marker at an x index (e.g. the day AI feedback was sent). */
export type LineMarker = { index: number; label?: string; color?: string };

/** Trend lines (1-4 series) over shared categorical x labels.
 *  Dataviz spec: 2px monotone-cubic lines that draw in on first view (the area fill follows),
 *  ring-stroked end markers with direct labels, ONE crosshair snapped to the nearest x with ONE
 *  tooltip listing every series (spring-follow; arrow keys step it, Escape clears), hairline
 *  solid grid, one axis, optional threshold line (e.g. the 4.55 rating line).
 *  Extensions: `bands` shade y zones, `markers` drop vertical event lines, `xAnnotations` add a
 *  second row under the x labels (module names), `reference` draws a grey dashed comparison
 *  line that is not a series, `colors` overrides the categorical order, `decimals` sets the
 *  number format (2 for ratings, 0 for scores). */
export function LineChart({
  labels,
  series,
  height = 240,
  yDomain,
  threshold,
  thresholdLabel,
  unit = "",
  area = false,
  endLabels = true,
  bands,
  markers,
  xAnnotations,
  reference,
  colors,
  decimals = 2,
}: {
  labels: string[];
  series: LineSeries[];
  height?: number;
  yDomain?: [number, number];
  threshold?: number;
  thresholdLabel?: string;
  unit?: string;
  area?: boolean;
  /** Direct labels at each line's end: the series name, or the last value for a single series. */
  endLabels?: boolean;
  bands?: LineBand[];
  markers?: LineMarker[];
  xAnnotations?: (string | null)[];
  reference?: LineSeries;
  colors?: string[];
  decimals?: number;
}) {
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<number | null>(null);
  const { enter } = useChartPlay(wrapRef);
  const isHidden = useSeriesHidden();
  const crossX = useMotionValue(0);
  const crossSpring = useSpring(crossX, SNAP);
  const clear = React.useCallback(() => setHover(null), []);
  useTapOutside(wrapRef, hover != null, clear);

  const fmtVal = (v: number) => v.toFixed(decimals);
  const color = (si: number) => colors?.[si] ?? SERIES[si % SERIES.length];

  // Geometry is pure, so it can sit above the hooks that depend on it.
  const W = 720;
  const ml = 40;
  const mt = markers?.some((m) => m.label) ? 20 : 12;
  const mb = xAnnotations ? 40 : 28;
  const n = labels.length;
  const ends = series.map((s) => {
    let idx = -1;
    s.values.forEach((v, i) => {
      if (v != null) idx = i;
    });
    return { idx, val: idx >= 0 ? s.values[idx] : null };
  });
  const endText = (si: number) => {
    const val = ends[si].val;
    return series.length > 1 ? series[si].name : val == null ? "" : fmtVal(val) + unit;
  };
  // Reserve the right margin for the direct labels so they never spill out of the SVG.
  const labelRoom = endLabels
    ? Math.min(120, Math.max(0, ...series.map((_, si) => estimateTextWidth(endText(si)))) + 10)
    : 0;
  const mr = 16 + labelRoom;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const xs = React.useMemo(
    () => Array.from({ length: n }, (_, i) => (n === 1 ? ml + pw / 2 : ml + (i / (n - 1)) * pw)),
    [n, ml, pw],
  );

  // Position the crosshair BEFORE the mark mounts (so its first frame is already right): land
  // in place when it first appears, spring between points after.
  const moveTo = (i: number | null) => {
    if (i != null) {
      if (hover == null) {
        crossX.jump(xs[i]);
        crossSpring.jump(xs[i]);
      } else {
        crossX.set(xs[i]);
      }
    }
    setHover(i);
  };

  const all = [...series.flatMap((s) => s.values), ...(reference?.values ?? [])].filter((v): v is number => v != null);
  if (all.length === 0 || n === 0) return null;
  let lo = yDomain?.[0] ?? Math.min(...all, threshold ?? Infinity);
  let hi = yDomain?.[1] ?? Math.max(...all, threshold ?? -Infinity);
  const padY = (hi - lo || 1) * 0.12;
  lo = yDomain ? lo : lo - padY;
  hi = yDomain ? hi : hi + padY;
  const ticks = niceTicks(lo, hi, 4).filter((t) => t >= lo && t <= hi);
  const y = scaleLinear([lo, hi], [mt + ph, mt]);
  const idx = xs.map((_, i) => i);
  const linePath = (vals: (number | null)[]) =>
    d3Line<number>()
      .defined((i) => vals[i] != null)
      .x((i) => xs[i])
      .y((i) => y(vals[i] as number))
      .curve(curveMonotoneX)(idx) ?? "";
  const areaPath = (vals: (number | null)[]) =>
    d3Area<number>()
      .defined((i) => vals[i] != null)
      .x((i) => xs[i])
      .y0(y(lo))
      .y1((i) => y(vals[i] as number))
      .curve(curveMonotoneX)(idx) ?? "";

  // Direct labels: nudged apart when two lines end within 12px of each other.
  const labelYs: (number | null)[] = ends.map(() => null);
  ends
    .map((e, si) => ({ si, y: e.val == null ? null : y(e.val) }))
    .filter((e): e is { si: number; y: number } => e.y != null)
    .sort((a, b) => a.y - b.y)
    .forEach((e, k, arr) => {
      if (k > 0 && e.y - arr[k - 1].y < 12) e.y = arr[k - 1].y + 12;
      labelYs[e.si] = clamp(e.y, mt + 4, mt + ph - 4);
    });

  const indexAt = (clientX: number) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const px = ((clientX - rect.left) / rect.width) * W;
    return clamp(Math.round(((px - ml) / pw) * (n - 1)), 0, n - 1);
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    let next: number | null | undefined;
    if (e.key === "Escape") next = null;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = n - 1;
    // The first arrow press reveals a point (the last for ←, the first for →); later ones step.
    else if (e.key === "ArrowLeft") next = hover == null ? n - 1 : Math.max(0, hover - 1);
    else if (e.key === "ArrowRight") next = hover == null ? 0 : Math.min(n - 1, hover + 1);
    if (next === undefined) return;
    e.preventDefault();
    moveTo(next);
  };

  const hoverRows =
    hover == null
      ? []
      : series.flatMap((s, si) => {
          const v = s.values[hover];
          return v == null || isHidden(s.name, si) ? [] : [{ si, v }];
        });
  const refAtHover = hover == null ? null : (reference?.values[hover] ?? null);
  const tipY = hoverRows.length ? Math.min(...hoverRows.map((r) => y(r.v))) : refAtHover != null ? y(refAtHover) : mt;
  const tipRows: TooltipRow[] = [
    ...hoverRows.map(({ si, v }) => ({
      value: fmtVal(v) + unit,
      label: series.length > 1 ? series[si].name : undefined,
      color: color(si),
      swatch: "line" as const,
    })),
    ...(reference && refAtHover != null
      ? [{ value: fmtVal(refAtHover) + unit, label: reference.name, color: "var(--muted-foreground)", swatch: "line" as const }]
      : []),
    ...(hover == null ? [] : (markers ?? []).filter((m) => m.index === hover && m.label).map((m) => ({ value: m.label!, color: m.color ?? "var(--muted-foreground)", swatch: "square" as const }))),
    ...(hover != null && xAnnotations?.[hover] ? [{ value: xAnnotations[hover]! }] : []),
  ];

  // Every ~nth x label so ticks never crowd (dataviz axis-readability).
  const stepX = Math.max(1, Math.ceil(n / 8));
  const xLabelY = height - (xAnnotations ? 20 : 8);

  return (
    <div
      ref={wrapRef}
      className="relative rounded-md"
      tabIndex={0}
      role="group"
      aria-roledescription="line chart"
      aria-label={`${series.map((s) => s.name).join(", ")}, ${labels[0]} to ${labels[n - 1]}. Use the arrow keys to step through points.`}
      onPointerMove={(e) => moveTo(indexAt(e.clientX))}
      onPointerDown={(e) => {
        if (e.pointerType === "touch") moveTo(indexAt(e.clientX));
      }}
      onPointerLeave={leaveUnlessTouch(clear)}
      onKeyDown={onKeyDown}
      onBlur={clear}
    >
      <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" aria-hidden>
        {bands?.map((b, i) => {
          const top = y(clamp(b.to, lo, hi));
          const bottom = y(clamp(b.from, lo, hi));
          if (bottom - top < 1) return null;
          return (
            <g key={i}>
              <rect x={ml} y={top} width={pw} height={bottom - top} fill={b.color} fillOpacity={0.07} />
              {b.label && (
                <text x={ml + pw - 4} y={top + 10} textAnchor="end" fill={b.color} fillOpacity={0.85} className="text-[9px] font-medium">
                  {b.label}
                </text>
              )}
            </g>
          );
        })}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ml} x2={W - mr} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={ml - 8} y={y(t) + 3.5} textAnchor="end" className="fill-muted-foreground font-mono text-[10px]">
              {t}{unit}
            </text>
          </g>
        ))}
        {labels.map((l, i) =>
          i % stepX === 0 ? (
            <text key={i} x={xs[i]} y={xLabelY} textAnchor="middle" className="fill-muted-foreground text-[10px]">
              {l}
            </text>
          ) : null,
        )}
        {xAnnotations?.map((a, i) =>
          a && i % stepX === 0 ? (
            <text key={`a${i}`} x={xs[i]} y={height - 7} textAnchor="middle" className="fill-muted-foreground/80 text-[9px]">
              {a.length > 18 ? a.slice(0, 17) + "…" : a}
            </text>
          ) : null,
        )}
        {threshold != null && (
          <g>
            <motion.line
              x1={ml}
              y1={y(threshold)}
              y2={y(threshold)}
              initial={false}
              animate={{ x2: enter ? [ml, W - mr] : W - mr }}
              transition={{ ...DRAW, delay: 0.1 }}
              stroke="var(--muted-foreground)"
              strokeWidth={1.5}
              strokeDasharray="5 4"
            />
            {thresholdLabel && (
              <motion.text
                x={W - mr}
                y={y(threshold) - 5}
                textAnchor="end"
                className="fill-muted-foreground font-mono text-[10px]"
                initial={false}
                animate={{ opacity: enter ? [0, 1] : 1 }}
                transition={{ duration: 0.4, delay: enter ? 0.7 : 0 }}
              >
                {thresholdLabel}
              </motion.text>
            )}
          </g>
        )}
        {markers?.map((m, i) => {
          const x = xs[m.index];
          if (x == null) return null;
          const c = m.color ?? "var(--muted-foreground)";
          return (
            <g key={`m${i}`}>
              <line x1={x} x2={x} y1={mt} y2={mt + ph} stroke={c} strokeWidth={1} strokeDasharray="3 3" strokeOpacity={0.8} />
              <path d={`M${x - 4},${mt}L${x + 4},${mt}L${x},${mt + 6}Z`} fill={c} />
              {m.label && (
                <text x={x} y={mt - 5} textAnchor="middle" fill={c} className="text-[9px] font-medium">
                  {m.label}
                </text>
              )}
            </g>
          );
        })}
        {reference && (
          <motion.path
            d={linePath(reference.values)}
            fill="none"
            stroke="var(--muted-foreground)"
            strokeOpacity={0.55}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            strokeLinejoin="round"
            initial={false}
            animate={{ pathLength: enter ? [0, 1] : 1 }}
            transition={{ pathLength: DRAW }}
          />
        )}
        {area && series.length === 1 && (
          <motion.path
            d={areaPath(series[0].values)}
            fill={color(0)}
            fillOpacity={0.08}
            initial={false}
            animate={{ opacity: isHidden(series[0].name, 0) ? 0 : enter ? [0, 1] : 1 }}
            transition={enter ? { duration: 0.6, delay: 0.6 } : { duration: 0.2 }}
          />
        )}
        {hover != null && (
          <motion.line
            x1={crossSpring}
            x2={crossSpring}
            y1={mt}
            y2={mt + ph}
            stroke="var(--muted-foreground)"
            strokeOpacity={0.45}
            strokeWidth={1}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.12 }}
          />
        )}
        {series.map((s, si) => {
          const d = linePath(s.values);
          if (!d) return null;
          return (
            <motion.path
              key={s.name}
              d={d}
              fill="none"
              stroke={color(si)}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              initial={false}
              animate={{ pathLength: enter ? [0, 1] : 1, opacity: isHidden(s.name, si) ? 0 : 1 }}
              transition={{ pathLength: { ...DRAW, delay: si * 0.12 }, opacity: { duration: 0.2 } }}
            />
          );
        })}
        {ends.map(({ idx: li, val }, si) => {
          if (val == null) return null;
          return (
            <motion.g
              key={series[si].name}
              initial={false}
              animate={{ opacity: isHidden(series[si].name, si) ? 0 : enter ? [0, 1] : 1 }}
              transition={enter ? { duration: 0.35, delay: DRAW.duration - 0.2 + si * 0.12 } : { duration: 0.2 }}
            >
              <circle cx={xs[li]} cy={y(val)} r={4} fill={color(si)} stroke="var(--card)" strokeWidth={2} />
              {endLabels && (
                <text
                  x={xs[li] + 9}
                  y={(labelYs[si] ?? y(val)) + 3.5}
                  fill={color(si)}
                  className={cn("text-[10.5px] font-semibold", series.length === 1 && "font-mono")}
                >
                  {endText(si)}
                </text>
              )}
            </motion.g>
          );
        })}
        {hoverRows.map(({ si, v }) => (
          <g key={series[si].name}>
            <motion.circle
              cx={crossSpring}
              r={9}
              fill={color(si)}
              fillOpacity={0.16}
              initial={{ cy: y(v), scale: 0 }}
              animate={{ cy: y(v), scale: 1 }}
              transition={{ cy: SNAP, scale: POP }}
            />
            <motion.circle
              cx={crossSpring}
              r={4}
              fill={color(si)}
              stroke="var(--card)"
              strokeWidth={2}
              initial={{ cy: y(v) }}
              animate={{ cy: y(v) }}
              transition={{ cy: SNAP }}
            />
          </g>
        ))}
      </svg>
      <ChartTooltip
        open={hover != null && tipRows.length > 0}
        x={hover == null ? 0 : xs[hover]}
        y={tipY}
        viewBox={[W, height]}
        boundsRef={wrapRef}
        title={hover == null ? undefined : labels[hover]}
        rows={tipRows}
        live
      />
    </div>
  );
}
