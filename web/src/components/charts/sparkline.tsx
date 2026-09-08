"use client";

import * as React from "react";
import { motion } from "motion/react";
import { EASE_OUT } from "@/components/motion/reveal";
import { POP, useChartPlay } from "./chart-motion";

/** 12-point-ish inline trend, per the stat-tile contract: quiet gray line, accent dot on the
 *  current period, no axes, no tooltip. Draws in once on first view — one path, one dot, so it
 *  stays cheap inside tiles and table rows. */
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
  const ref = React.useRef<SVGSVGElement>(null);
  const { enter } = useChartPlay(ref, { amount: 0.5, settle: 1.2 });
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
      ref={ref}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
      className="overflow-visible"
    >
      <motion.path
        d={d}
        fill="none"
        stroke="var(--muted-foreground)"
        strokeOpacity={0.45}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        initial={false}
        animate={{ pathLength: enter ? [0, 1] : 1 }}
        transition={{ duration: 0.7, ease: EASE_OUT }}
      />
      <motion.circle
        cx={x(pts.length - 1)}
        cy={y(last)}
        r={2.5}
        fill={accent}
        stroke="var(--card)"
        strokeWidth={1.5}
        initial={false}
        animate={{ scale: enter ? [0, 1] : 1 }}
        transition={{ ...POP, delay: enter ? 0.5 : 0 }}
      />
    </svg>
  );
}
