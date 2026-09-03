"use client";

import * as React from "react";
import { motion } from "motion/react";
import { useSeriesHidden } from "./chart-legend";
import { DRAW, POP, SNAP, leaveUnlessTouch, useChartPlay, useTapOutside } from "./chart-motion";
import { ChartTooltip, type TooltipRow } from "./chart-tooltip";

const BATCHES = 8;
/** Dots pop in with a scale overshoot — one CSS animation per dot, delayed per batch, instead of
 *  thousands of JS timelines. Hoisted + deduped by React via href/precedence. */
const DOT_CSS = `@keyframes np-dot-pop{0%{transform:scale(0);opacity:0}55%{transform:scale(1.4);opacity:1}100%{transform:scale(1);opacity:1}}
[data-play] .np-dot{transform-box:fill-box;transform-origin:center;animation:np-dot-pop .5s cubic-bezier(.22,1,.36,1) both;animation-delay:var(--d,0ms)}
@media (prefers-reduced-motion:reduce){[data-play] .np-dot{animation:none}}`;

/** The study's signature figure: every class as a dot, rating (y) against a percentage (x) —
 *  participation by default, or the approval vote — with the 4.55 decision line, the vertical
 *  bar, and a shaded corner. Built for a few thousand points: no per-dot handlers or titles —
 *  ONE pointer listener finds the nearest dot, which gets a halo and the tooltip. Dots pop in
 *  left→right in 8 batches on first view. */
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
  labels,
  xValueLabel,
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
  /** Tooltip title per point, aligned with `points` (e.g. "Course · topic · date"). */
  labels?: string[];
  /** Short name for the x value in the tooltip ("participation"); defaults to `xLabel`. */
  xValueLabel?: string;
}) {
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<number | null>(null);
  const { play, enter } = useChartPlay(wrapRef, { amount: 0.2 });
  const isHidden = useSeriesHidden();
  const clear = React.useCallback(() => setHover(null), []);
  useTapOutside(wrapRef, hover != null, clear);

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
  // Legend position 0 is the fine class, 1 the flagged class (both call sites list them so).
  const hiddenCls = [isHidden("", 0), isHidden("", 1)];

  // Projected once; the nearest-dot scan and the dot layer both read these.
  const { px, py } = React.useMemo(() => {
    const px = new Float64Array(points.length);
    const py = new Float64Array(points.length);
    points.forEach(([p, r], i) => {
      px[i] = ml + (Math.min(p, 100) / 100) * pw;
      py[i] = mt + ((5 - Math.max(Math.min(r, 5), 3)) / 2) * ph;
    });
    return { px, py };
  }, [points, ml, mt, pw, ph]);

  // The dot layer is memoised so hovering re-renders only the halo and tooltip, not 2,000 dots.
  const dotLayers = React.useMemo(() => {
    const groups: number[][][] = [0, 1].map(() => Array.from({ length: BATCHES }, () => []));
    points.forEach(([p, , bad], i) => {
      groups[bad ? 1 : 0][Math.min(BATCHES - 1, Math.floor((Math.min(p, 100) / 100) * BATCHES))].push(i);
    });
    return groups.map((batches, cls) => (
      <g key={cls}>
        {batches.map((idxs, b) => (
          <g key={b} style={{ "--d": `${b * 55}ms` } as React.CSSProperties}>
            {idxs.map((i) => (
              <circle
                key={i}
                className="np-dot"
                cx={px[i]}
                cy={py[i]}
                r={2.4}
                fill={cls ? "var(--viz-bad)" : "var(--chart-1)"}
                fillOpacity={cls ? 0.55 : 0.28}
              />
            ))}
          </g>
        ))}
      </g>
    ));
  }, [points, px, py]);

  const nearestAt = (clientX: number, clientY: number) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const k = rect.width / W;
    const vx = (clientX - rect.left) / k;
    const vy = (clientY - rect.top) / k;
    let best = -1;
    let bestD = (14 / k) ** 2; // 14 CSS px reach
    for (let i = 0; i < points.length; i++) {
      if (hiddenCls[points[i][2] ? 1 : 0]) continue;
      const dx = px[i] - vx;
      const dy = py[i] - vy;
      const d = dx * dx + dy * dy;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    return best < 0 ? null : best;
  };

  const hp = hover == null ? null : points[hover];
  const hoverColor = hp?.[2] ? "var(--viz-bad)" : "var(--chart-1)";
  const tipRows: TooltipRow[] = hp
    ? [
        { value: hp[1].toFixed(2), label: "rating", color: hoverColor, swatch: "dot" },
        { value: `${Math.round(hp[0])}%`, label: xValueLabel ?? xLabel },
      ]
    : [];

  return (
    <div
      ref={wrapRef}
      className="relative"
      onPointerMove={(e) => setHover(nearestAt(e.clientX, e.clientY))}
      onPointerDown={(e) => {
        if (e.pointerType === "touch") setHover(nearestAt(e.clientX, e.clientY));
      }}
      onPointerLeave={leaveUnlessTouch(clear)}
    >
      <style href="np-chart-scatter" precedence="default">{DOT_CSS}</style>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="block w-full"
        role="img"
        aria-label={ariaLabel}
        data-play={play ? "" : undefined}
      >
        {/* grid */}
        {[3, 3.5, 4, 4.5, 5].map((r) => (
          <g key={r}>
            <line x1={ml} x2={W - mr} y1={y(r)} y2={y(r)} stroke="var(--chart-grid)" strokeWidth={1} strokeDasharray="1 3" />
            <text x={ml - 7} y={y(r) + 3} textAnchor="end" className="fill-muted-foreground/80 font-mono text-[9.5px]">{r.toFixed(1)}</text>
          </g>
        ))}
        {[0, 20, 40, 60, 80, 100].map((p) => (
          <text key={p} x={x(p)} y={height - 22} textAnchor="middle" className="fill-muted-foreground/80 font-mono text-[9.5px]">{p}%</text>
        ))}
        {/* the shaded corner: bad rating AND the bar's bad side */}
        <motion.rect
          x={cornerX0}
          y={y(threshold)}
          width={cornerX1 - cornerX0}
          height={mt + ph - y(threshold)}
          fill="var(--viz-bad)"
          fillOpacity={0.06}
          initial={false}
          animate={{ opacity: enter ? [0, 1] : 1 }}
          transition={{ duration: 0.6, delay: enter ? 0.3 : 0 }}
        />
        {/* decision line + bar draw in; their labels follow */}
        <motion.line
          x1={ml}
          y1={y(threshold)}
          y2={y(threshold)}
          initial={false}
          animate={{ x2: enter ? [ml, W - mr] : W - mr }}
          transition={{ ...DRAW, delay: enter ? 0.2 : 0 }}
          stroke="var(--muted-foreground)"
          strokeWidth={1.5}
          strokeDasharray="5 4"
        />
        <motion.line
          x1={x(bar)}
          x2={x(bar)}
          y2={mt + ph}
          initial={false}
          animate={{ y1: enter ? [mt + ph, mt] : mt }}
          transition={{ ...DRAW, delay: enter ? 0.35 : 0 }}
          stroke="var(--chart-1)"
          strokeWidth={1.5}
        />
        <motion.g
          initial={false}
          animate={{ opacity: enter ? [0, 1] : 1 }}
          transition={{ duration: 0.4, delay: enter ? 0.9 : 0 }}
        >
          <text x={ml + 6} y={y(threshold) + 13} className="fill-muted-foreground text-[10px]">
            {lineLabel ?? `rating ${threshold} — below this we look`}
          </text>
          <text x={x(bar)} y={mt - 8} textAnchor="middle" className="fill-[var(--chart-1)] text-[10px] font-semibold">
            {barLabel ?? `${bar}% bar`}
          </text>
          <text x={cornerMid} y={y(3.15)} textAnchor="middle" className="fill-[var(--viz-bad)] text-[10px] font-medium">
            {cornerLabel ?? `below ${threshold} + representative sample → video`}
          </text>
        </motion.g>
        {/* dots, by class so a legend chip can fade a whole class */}
        {dotLayers.map((layer, cls) => (
          <g key={cls} className="transition-opacity duration-200" style={{ opacity: hiddenCls[cls] ? 0 : 1 }}>
            {layer}
          </g>
        ))}
        {hover != null && hp && (
          <g>
            <motion.circle
              r={9}
              fill={hoverColor}
              fillOpacity={0.18}
              initial={{ cx: px[hover], cy: py[hover], scale: 0 }}
              animate={{ cx: px[hover], cy: py[hover], scale: 1 }}
              transition={{ cx: SNAP, cy: SNAP, scale: POP }}
            />
            <motion.circle
              r={3.4}
              fill={hoverColor}
              stroke="var(--card)"
              strokeWidth={1.5}
              initial={{ cx: px[hover], cy: py[hover] }}
              animate={{ cx: px[hover], cy: py[hover] }}
              transition={{ cx: SNAP, cy: SNAP }}
            />
          </g>
        )}
        <text x={ml + pw / 2} y={height - 6} textAnchor="middle" className="fill-muted-foreground text-[10.5px]">
          {xLabel}
        </text>
      </svg>
      <ChartTooltip
        open={hover != null}
        x={hover == null ? 0 : px[hover]}
        y={hover == null ? 0 : py[hover]}
        viewBox={[W, height]}
        boundsRef={wrapRef}
        title={hover == null ? undefined : labels?.[hover]}
        rows={tipRows}
      />
    </div>
  );
}
