"use client";

import * as React from "react";
import { motion } from "motion/react";
import { CountUp } from "@/components/motion/count-up";
import { GROW, useChartPlay } from "./chart-motion";

export type HBarRow = {
  label: string;
  href?: string;
  pct: number;
  text: string;
  numeric: { prefix: string; value: number; decimals: number; suffix: string } | null;
};

/** The client half of HBars: bars grow from the left 40ms apart, numeric labels count up, and
 *  hovering a row dims the others. */
export function HBarRows({ rows, color }: { rows: HBarRow[]; color: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const { enter } = useChartPlay(ref, { amount: 0.2 });
  const [hover, setHover] = React.useState<number | null>(null);

  return (
    <div ref={ref} className="space-y-2.5" onPointerLeave={() => setHover(null)}>
      {rows.map((r, i) => {
        const dim = hover != null && hover !== i;
        const row = (
          <div
            className="grid grid-cols-[minmax(90px,160px)_1fr_auto] items-center gap-3 transition-opacity duration-150"
            style={{ opacity: dim ? 0.5 : 1 }}
          >
            <span className="truncate text-[13px]" title={r.label}>
              {r.label}
            </span>
            <span className="bg-muted relative h-3.5 overflow-hidden rounded-[4px]">
              <motion.span
                className="absolute inset-y-0 left-0 rounded-r-[4px]"
                style={{ background: color }}
                initial={false}
                animate={{ width: enter ? ["0%", `${r.pct}%`] : `${r.pct}%` }}
                transition={{ ...GROW, delay: enter ? i * 0.04 : 0 }}
              />
            </span>
            <span className="text-[13px] font-semibold" data-numeric>
              {r.numeric ? (
                <CountUp
                  value={r.numeric.value}
                  decimals={r.numeric.decimals}
                  prefix={r.numeric.prefix}
                  suffix={r.numeric.suffix}
                />
              ) : (
                r.text
              )}
            </span>
          </div>
        );
        return r.href ? (
          <a
            key={r.label}
            href={r.href}
            className="hover:bg-muted/40 -mx-1 block rounded px-1 py-0.5"
            onPointerEnter={() => setHover(i)}
          >
            {row}
          </a>
        ) : (
          <div key={r.label} onPointerEnter={() => setHover(i)}>
            {row}
          </div>
        );
      })}
    </div>
  );
}
