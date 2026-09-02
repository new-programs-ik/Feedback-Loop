"use client";

import * as React from "react";
import { SEQ, scaleLinear } from "./chart-kit";

/** Distribution over ORDERED bands (e.g. rating bands worst→best) — wears the ordinal blue
 *  ramp, count on each cap, band labels beneath. */
export function Histogram({
  bands,
  height = 200,
}: {
  bands: { label: string; count: number }[];
  height?: number;
}) {
  const W = 720;
  const ml = 12;
  const mr = 12;
  const mt = 20;
  const mb = 40;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const max = Math.max(...bands.map((b) => b.count), 1);
  const y = scaleLinear([0, max], [mt + ph, mt]);
  const slot = pw / bands.length;
  const bw = Math.min(52, slot * 0.62);
  // Ramp maps band ORDER (not value): spread the 5 steps across however many bands exist.
  const color = (i: number) => SEQ[Math.round((i / Math.max(bands.length - 1, 1)) * (SEQ.length - 1))];

  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="block w-full" role="img">
      <line x1={ml} x2={W - mr} y1={mt + ph} y2={mt + ph} stroke="var(--chart-grid)" strokeWidth={1} />
      {bands.map((b, i) => {
        const cx = ml + slot * i + slot / 2;
        const x0 = cx - bw / 2;
        const y1 = y(b.count);
        const h = mt + ph - y1;
        return (
          <g key={b.label}>
            {b.count > 0 && (
              <path
                d={`M${x0},${mt + ph}V${y1 + 4}Q${x0},${y1} ${x0 + 4},${y1}H${x0 + bw - 4}Q${x0 + bw},${y1} ${x0 + bw},${y1 + 4}V${mt + ph}Z`}
                fill={color(i)}
              >
                <title>{`${b.label}: ${b.count} classes`}</title>
              </path>
            )}
            <text x={cx} y={(b.count > 0 ? y1 : mt + ph) - 6} textAnchor="middle" className="fill-muted-foreground text-[10.5px] font-semibold">
              {b.count}
            </text>
            <text x={cx} y={height - 22} textAnchor="middle" className="fill-foreground text-[10.5px]">
              {b.label.split("|")[0]}
            </text>
            {b.label.includes("|") && (
              <text x={cx} y={height - 9} textAnchor="middle" className="fill-muted-foreground text-[9.5px]">
                {b.label.split("|")[1]}
              </text>
            )}
            {h > 0 && <rect x={x0} y={y1} width={bw} height={h} fill="transparent" />}
          </g>
        );
      })}
    </svg>
  );
}
