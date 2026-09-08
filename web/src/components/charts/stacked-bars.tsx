"use client";

import * as React from "react";
import { motion } from "motion/react";
import { niceTicks, scaleLinear } from "./chart-kit";
import { useSeriesHidden } from "./chart-legend";
import { GROW, leaveUnlessTouch, useChartPlay, useTapOutside } from "./chart-motion";
import { ChartTooltip, type TooltipRow } from "./chart-tooltip";

export type StackSegment = { name: string; color: string };

/** Stacked columns (e.g. fine vs below-4.55 per month, or the band mix per week).
 *  Dataviz spec: columns <= 24px, 2px surface gaps between segments AND bars, 4px rounded cap
 *  on the top segment only (square at the baseline). Columns grow from the baseline 30ms apart
 *  on first view; hovering one dims the rest and opens the stack breakdown. Colors are passed
 *  in (status tokens for pass/fail stacks; categorical tokens otherwise) — never both.
 *  `normalize` draws every column to 100% (the tooltip keeps the counts beside the shares). */
export function StackedBars({
  labels,
  segments,
  values, // values[barIndex][segmentIndex]
  height = 220,
  topLabels,
  normalize = false,
}: {
  labels: string[];
  segments: StackSegment[];
  values: number[][];
  height?: number;
  /** Optional label above each bar, PRE-COMPUTED by the caller (props must be serializable
   *  across the server->client boundary — never pass functions here). */
  topLabels?: (string | null)[];
  normalize?: boolean;
}) {
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<number | null>(null);
  const { enter } = useChartPlay(wrapRef);
  const isHidden = useSeriesHidden();
  const clear = React.useCallback(() => setHover(null), []);
  useTapOutside(wrapRef, hover != null, clear);

  const W = 720;
  const ml = normalize ? 34 : 30;
  const mr = 8;
  const mt = 22;
  const mb = 24;
  const pw = W - ml - mr;
  const ph = height - mt - mb;

  const totals = values.map((row) => row.reduce((a, b) => a + b, 0));
  const shown = normalize ? values.map((row, bi) => row.map((v) => (totals[bi] ? (v / totals[bi]) * 100 : 0))) : values;
  const shownTotals = normalize ? totals.map((t) => (t ? 100 : 0)) : totals;
  const max = normalize ? 100 : Math.max(...totals, 1);
  const ticks = normalize ? [25, 50, 75, 100] : niceTicks(0, max, 3).filter((t) => t > 0 && t <= max * 1.08);
  const y = scaleLinear([0, normalize ? 100 : Math.max(max, ticks[ticks.length - 1] ?? max)], [mt + ph, mt]);
  const slot = pw / Math.max(labels.length, 1);
  // Few categories get substantial columns; many stay thin (dataviz thin-mark cap).
  const bw = Math.min(labels.length <= 6 ? 44 : 24, slot * 0.6);
  const hiddenSeg = segments.map((s, si) => isHidden(s.name, si));
  // Every ~nth x label so ticks never crowd.
  const stepX = Math.max(1, Math.ceil(labels.length / 12));

  const tipRows: TooltipRow[] =
    hover == null
      ? []
      : [
          ...segments.flatMap((seg, si) =>
            hiddenSeg[si]
              ? []
              : [
                  {
                    value: normalize ? `${values[hover][si]} (${Math.round(shown[hover][si])}%)` : String(values[hover][si]),
                    label: seg.name,
                    color: seg.color,
                    swatch: "square" as const,
                  },
                ],
          ),
          ...(segments.length > 1 ? [{ value: String(totals[hover]), label: "total" }] : []),
        ];

  return (
    <div ref={wrapRef} className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" role="img" onPointerLeave={leaveUnlessTouch(clear)}>
        <line x1={ml} x2={W - mr} y1={mt + ph} y2={mt + ph} stroke="var(--chart-grid)" strokeWidth={1} />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ml} x2={W - mr} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} strokeDasharray="1 3" />
            <text x={ml - 6} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground/80 font-mono text-[9.5px]">
              {t}
              {normalize ? "%" : ""}
            </text>
          </g>
        ))}
        {labels.map((label, bi) => {
          const cx = ml + slot * bi + slot / 2;
          const x0 = cx - bw / 2;
          let acc = 0;
          const rects = shown[bi].map((v, si) => {
            const y1 = y(acc + v);
            const y0 = y(acc);
            acc += v;
            return { si, v, y1, h: Math.max(y0 - y1 - (v > 0 ? 2 : 0), v > 0 ? 1.5 : 0) };
          });
          const topIdx = rects.reduce((best, r) => (r.v > 0 ? r.si : best), -1);
          const dim = hover != null && hover !== bi;
          return (
            <g
              key={bi}
              className="transition-opacity duration-150"
              style={{ opacity: dim ? 0.4 : 1 }}
              onPointerEnter={() => setHover(bi)}
            >
              {/* generous invisible hit target (touch-target rule) */}
              <rect x={ml + slot * bi} y={mt} width={slot} height={ph} fill="transparent" />
              {/* The whole stack scales from its own bottom edge — the baseline. */}
              <motion.g
                style={{ originY: 1 }}
                initial={false}
                animate={{ scaleY: enter ? [0.001, 1] : 1 }}
                transition={{ ...GROW, delay: bi * 0.03 }}
              >
                {rects.map((r) =>
                  r.v > 0 ? (
                    <path
                      key={r.si}
                      d={
                        r.si === topIdx
                          ? `M${x0},${r.y1 + r.h}V${r.y1 + 4}Q${x0},${r.y1} ${x0 + 4},${r.y1}H${x0 + bw - 4}Q${x0 + bw},${r.y1} ${x0 + bw},${r.y1 + 4}V${r.y1 + r.h}Z`
                          : `M${x0},${r.y1}H${x0 + bw}V${r.y1 + r.h}H${x0}Z`
                      }
                      fill={segments[r.si].color}
                      className="transition-opacity duration-200"
                      style={{ opacity: hiddenSeg[r.si] ? 0 : 1 }}
                    />
                  ) : null,
                )}
              </motion.g>
              {topLabels?.[bi] && (
                <motion.text
                  x={cx}
                  y={y(shownTotals[bi]) - 7}
                  textAnchor="middle"
                  className="fill-muted-foreground font-mono text-[9.5px] font-semibold"
                  initial={false}
                  animate={{ opacity: enter ? [0, 1] : 1 }}
                  transition={{ duration: 0.3, delay: enter ? GROW.duration * 0.7 + bi * 0.03 : 0 }}
                >
                  {topLabels[bi]}
                </motion.text>
              )}
              {bi % stepX === 0 && (
                <text x={cx} y={height - 7} textAnchor="middle" className="fill-muted-foreground text-[10px] font-medium">
                  {label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <ChartTooltip
        open={hover != null}
        x={hover == null ? 0 : ml + slot * hover + slot / 2}
        y={hover == null ? mt : y(shownTotals[hover])}
        viewBox={[W, height]}
        boundsRef={wrapRef}
        title={hover == null ? undefined : labels[hover]}
        rows={tipRows}
      />
    </div>
  );
}
