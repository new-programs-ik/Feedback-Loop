"use client";

import * as React from "react";
import { motion } from "motion/react";
import { GROW, useChartPlay } from "./chart-motion";

export type HBarRow = {
  label: string;
  sub?: string;
  href?: string;
  /** Left edge and width of the bar, in % of the track. */
  start: number;
  width: number;
  /** Diverging mode: the bar sits left of the centre and grows leftwards. */
  negative: boolean;
  color: string;
  text: string;
};

/** The client half of HBars: bars grow from their baseline 40ms apart (once), and hovering a
 *  row dims the others. Labels are static — a number that moves cannot be read. */
export function HBarRows({ rows, centerPct }: { rows: HBarRow[]; centerPct?: number }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const { enter } = useChartPlay(ref, { amount: 0.2 });
  const [hover, setHover] = React.useState<number | null>(null);

  return (
    <div ref={ref} className="space-y-2" onPointerLeave={() => setHover(null)}>
      {rows.map((r, i) => {
        const dim = hover != null && hover !== i;
        const row = (
          <div
            className="grid grid-cols-[minmax(90px,160px)_1fr_auto] items-center gap-3 transition-opacity duration-150"
            style={{ opacity: dim ? 0.5 : 1 }}
          >
            <span className="min-w-0">
              <span className="block truncate text-[13px]" title={r.label}>
                {r.label}
              </span>
              {r.sub && <span className="text-muted-foreground block truncate text-[10.5px]">{r.sub}</span>}
            </span>
            <span className="bg-muted relative h-3.5 overflow-hidden rounded-[4px]">
              {centerPct != null && (
                <span aria-hidden className="bg-foreground/50 absolute inset-y-0 w-px" style={{ left: `${centerPct}%` }} />
              )}
              <motion.span
                className={r.negative ? "absolute inset-y-0 rounded-l-[4px]" : "absolute inset-y-0 rounded-r-[4px]"}
                style={
                  r.negative
                    ? { background: r.color, right: `${100 - (r.start + r.width)}%` }
                    : { background: r.color, left: `${r.start}%` }
                }
                initial={false}
                animate={{ width: enter ? ["0%", `${r.width}%`] : `${r.width}%` }}
                transition={{ ...GROW, delay: enter ? i * 0.04 : 0 }}
              />
            </span>
            <span className="text-[13px] font-semibold" data-numeric>
              {r.text}
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
