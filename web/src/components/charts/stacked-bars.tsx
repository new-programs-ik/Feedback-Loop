"use client";

import * as React from "react";
import { niceTicks, scaleLinear } from "./chart-kit";

export type StackSegment = { name: string; color: string };

/** Stacked columns (e.g. fine vs below-4.55 per month).
 *  Dataviz spec: columns <= 24px, 2px surface gaps between segments AND bars, 4px rounded cap
 *  on the top segment only (square at the baseline), per-bar hover tooltip. Colors are passed
 *  in (status tokens for pass/fail stacks; categorical tokens otherwise) — never both. */
export function StackedBars({
  labels,
  segments,
  values, // values[barIndex][segmentIndex]
  height = 220,
  topLabels,
}: {
  labels: string[];
  segments: StackSegment[];
  values: number[][];
  height?: number;
  /** Optional label above each bar, PRE-COMPUTED by the caller (props must be serializable
   *  across the server->client boundary — never pass functions here). */
  topLabels?: (string | null)[];
}) {
  const W = 720;
  const ml = 30;
  const mr = 8;
  const mt = 22;
  const mb = 24;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const [hover, setHover] = React.useState<number | null>(null);

  const totals = values.map((row) => row.reduce((a, b) => a + b, 0));
  const max = Math.max(...totals, 1);
  const ticks = niceTicks(0, max, 3).filter((t) => t > 0 && t <= max * 1.08);
  const y = scaleLinear([0, Math.max(max, ticks[ticks.length - 1] ?? max)], [mt + ph, mt]);
  const slot = pw / labels.length;
  // Few categories get substantial columns; many stay thin (dataviz thin-mark cap).
  const bw = Math.min(labels.length <= 6 ? 44 : 24, slot * 0.6);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" role="img" onMouseLeave={() => setHover(null)}>
        <line x1={ml} x2={W - mr} y1={mt + ph} y2={mt + ph} stroke="var(--chart-grid)" strokeWidth={1} />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ml} x2={W - mr} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} strokeDasharray="1 3" />
            <text x={ml - 6} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground/80 text-[9.5px]">
              {t}
            </text>
          </g>
        ))}
        {labels.map((label, bi) => {
          const cx = ml + slot * bi + slot / 2;
          const x0 = cx - bw / 2;
          let acc = 0;
          const rects = values[bi].map((v, si) => {
            const y1 = y(acc + v);
            const y0 = y(acc);
            acc += v;
            return { si, v, y1, h: Math.max(y0 - y1 - (v > 0 ? 2 : 0), v > 0 ? 1.5 : 0) };
          });
          const topIdx = rects.reduce((best, r) => (r.v > 0 ? r.si : best), -1);
          return (
            <g key={bi} onMouseEnter={() => setHover(bi)}>
              {/* generous invisible hit target (touch-target rule) */}
              <rect x={ml + slot * bi} y={mt} width={slot} height={ph} fill="transparent" />
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
                    opacity={hover == null || hover === bi ? 1 : 0.45}
                  />
                ) : null,
              )}
              {topLabels?.[bi] && (
                <text x={cx} y={y(totals[bi]) - 7} textAnchor="middle" className="fill-muted-foreground text-[9.5px] font-semibold">
                  {topLabels[bi]}
                </text>
              )}
              <text x={cx} y={height - 7} textAnchor="middle" className="fill-muted-foreground text-[10px] font-medium">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      {hover != null && (
        <div
          className="bg-popover text-popover-foreground shadow-soft pointer-events-none absolute top-1 z-10 rounded-lg border px-3 py-2 text-xs"
          style={{
            left: `${((ml + slot * hover + slot / 2) / W) * 100}%`,
            transform: hover > labels.length * 0.7 ? "translateX(calc(-100% - 8px))" : "translateX(8px)",
          }}
        >
          <div className="text-muted-foreground mb-1 font-medium">{labels[hover]}</div>
          {segments.map((seg, si) => (
            <div key={seg.name} className="flex items-center gap-2">
              <span className="size-2.5 rounded-[3px]" style={{ background: seg.color }} />
              <span className="font-semibold" data-numeric>{values[hover][si]}</span>
              <span className="text-muted-foreground">{seg.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
