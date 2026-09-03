"use client";

import * as React from "react";
import { motion } from "motion/react";
import { SEQ, scaleLinear } from "./chart-kit";
import { CountText, DRAW, GROW, leaveUnlessTouch, useChartPlay, useTapOutside } from "./chart-motion";
import { ChartTooltip } from "./chart-tooltip";

export type HistogramMarker = {
  /** Position in band units: 2 is the centre of the third band, 2.5 the edge between the third
   *  and fourth — a threshold sits on an edge, a mean is interpolated inside its band. */
  at: number;
  label: string;
  color?: string;
};

/** Distribution over ORDERED bands (e.g. rating bands worst→best) — wears the ordinal blue
 *  ramp, count on each cap, band labels beneath. Bars grow from the baseline in sequence on
 *  first view, the counts count up, and any threshold/mean markers draw in after the bars. */
export function Histogram({
  bands,
  height = 200,
  markers,
}: {
  bands: { label: string; count: number }[];
  height?: number;
  markers?: HistogramMarker[];
}) {
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [hover, setHover] = React.useState<number | null>(null);
  const { enter } = useChartPlay(wrapRef);
  const clear = React.useCallback(() => setHover(null), []);
  useTapOutside(wrapRef, hover != null, clear);

  const W = 720;
  const ml = 12;
  const mr = 12;
  const mt = markers?.length ? 34 : 20;
  const mb = 40;
  const pw = W - ml - mr;
  const ph = height - mt - mb;
  const max = Math.max(...bands.map((b) => b.count), 1);
  const y = scaleLinear([0, max], [mt + ph, mt]);
  const slot = pw / bands.length;
  const bw = Math.min(52, slot * 0.62);
  // Ramp maps band ORDER (not value): spread the 5 steps across however many bands exist.
  const color = (i: number) => SEQ[Math.round((i / Math.max(bands.length - 1, 1)) * (SEQ.length - 1))];
  const summary = bands.map((b) => `${b.label.split("|")[0]}: ${b.count}`).join(", ");

  return (
    <div ref={wrapRef} className="relative">
      <svg
        viewBox={`0 0 ${W} ${height}`}
        className="block w-full"
        role="img"
        aria-label={`Distribution — ${summary}`}
        onPointerLeave={leaveUnlessTouch(clear)}
      >
        <line x1={ml} x2={W - mr} y1={mt + ph} y2={mt + ph} stroke="var(--chart-grid)" strokeWidth={1} />
        {bands.map((b, i) => {
          const cx = ml + slot * i + slot / 2;
          const x0 = cx - bw / 2;
          const y1 = y(b.count);
          const dim = hover != null && hover !== i;
          return (
            <g
              key={b.label}
              className="transition-opacity duration-150"
              style={{ opacity: dim ? 0.45 : 1 }}
              onPointerEnter={() => setHover(i)}
            >
              {/* full-column hit target so empty bands are hoverable too */}
              <rect x={ml + slot * i} y={mt} width={slot} height={ph} fill="transparent" />
              {b.count > 0 && (
                <motion.path
                  d={`M${x0},${mt + ph}V${y1 + 4}Q${x0},${y1} ${x0 + 4},${y1}H${x0 + bw - 4}Q${x0 + bw},${y1} ${x0 + bw},${y1 + 4}V${mt + ph}Z`}
                  fill={color(i)}
                  style={{ originY: 1 }}
                  initial={false}
                  animate={{ scaleY: enter ? [0.001, 1] : 1 }}
                  transition={{ ...GROW, delay: i * 0.05 }}
                />
              )}
              <CountText
                value={b.count}
                play={enter}
                delay={i * 0.05}
                x={cx}
                y={(b.count > 0 ? y1 : mt + ph) - 6}
                textAnchor="middle"
                className="fill-muted-foreground font-mono text-[10.5px] font-semibold"
              />
              <text x={cx} y={height - 22} textAnchor="middle" className="fill-foreground text-[10.5px]">
                {b.label.split("|")[0]}
              </text>
              {b.label.includes("|") && (
                <text x={cx} y={height - 9} textAnchor="middle" className="fill-muted-foreground text-[9.5px]">
                  {b.label.split("|")[1]}
                </text>
              )}
            </g>
          );
        })}
        {markers?.map((m) => {
          const mx = ml + slot * (m.at + 0.5);
          const c = m.color ?? "var(--muted-foreground)";
          return (
            <g key={m.label}>
              <motion.line
                x1={mx}
                x2={mx}
                y2={mt + ph}
                initial={false}
                animate={{ y1: enter ? [mt + ph, mt - 6] : mt - 6 }}
                transition={{ ...DRAW, delay: enter ? 0.45 : 0 }}
                stroke={c}
                strokeWidth={1.5}
                strokeDasharray="5 4"
              />
              <motion.text
                x={mx}
                y={12}
                textAnchor="middle"
                fill={c}
                className="text-[10px] font-semibold"
                initial={false}
                animate={{ opacity: enter ? [0, 1] : 1 }}
                transition={{ duration: 0.4, delay: enter ? 1 : 0 }}
              >
                {m.label}
              </motion.text>
            </g>
          );
        })}
      </svg>
      <ChartTooltip
        open={hover != null}
        x={hover == null ? 0 : ml + slot * hover + slot / 2}
        y={hover == null ? mt : y(bands[hover].count)}
        viewBox={[W, height]}
        boundsRef={wrapRef}
        title={hover == null ? undefined : bands[hover].label.replace("|", " — ")}
        rows={
          hover == null
            ? []
            : [
                {
                  value: bands[hover].count.toLocaleString("en-US"),
                  label: bands[hover].count === 1 ? "class" : "classes",
                  color: color(hover),
                  swatch: "square",
                },
              ]
        }
      />
    </div>
  );
}
