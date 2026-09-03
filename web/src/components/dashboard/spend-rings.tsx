"use client";

import { motion, useReducedMotion } from "motion/react";
import { CountUp } from "@/components/motion/count-up";
import { EASE_OUT } from "@/components/motion/reveal";
import { cn } from "@/lib/utils";

export type SpendMonth = {
  key: string;
  label: string;
  cost: number;
  count: number;
  current: boolean;
};

const R = 18;
const SIZE = 48;

/** One ring per month, filled as a share of the busiest month in view — the old flat meters,
 *  now drawn in place. Rings sweep in (motion `pathLength`) with a short cascade, and the amount
 *  under each counts up. One hue: the current month is full-strength, earlier months recede. */
export function SpendRings({ months }: { months: SpendMonth[] }) {
  const reduce = useReducedMotion();
  const max = Math.max(...months.map((m) => m.cost), 0.01);
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      {months.map((m, i) => {
        const share = m.cost > 0 ? Math.max(0.04, m.cost / max) : 0;
        const stroke = m.current ? "var(--primary)" : "color-mix(in oklch, var(--primary) 45%, transparent)";
        return (
          <div key={m.key} className="flex flex-col items-center gap-1">
            <svg
              width={SIZE}
              height={SIZE}
              viewBox={`0 0 ${SIZE} ${SIZE}`}
              role="img"
              aria-label={`${m.label}: $${m.cost.toFixed(2)} across ${m.count} ${m.count === 1 ? "analysis" : "analyses"}`}
            >
              <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="var(--muted)" strokeWidth={4} />
              {share > 0 && (
                <motion.circle
                  cx={SIZE / 2}
                  cy={SIZE / 2}
                  r={R}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={4}
                  strokeLinecap="round"
                  transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
                  initial={reduce ? { pathLength: share } : { pathLength: 0 }}
                  whileInView={{ pathLength: share }}
                  viewport={{ once: true, amount: 0.6 }}
                  transition={{ duration: 0.9, ease: EASE_OUT, delay: 0.1 + i * 0.08 }}
                />
              )}
              <text
                x={SIZE / 2}
                y={SIZE / 2 + 3.5}
                textAnchor="middle"
                className={cn("text-[10px] font-semibold", m.current ? "fill-foreground" : "fill-muted-foreground")}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {m.count}
              </text>
            </svg>
            <div className={cn("text-[12px] font-semibold", !m.current && "text-foreground/80")}>
              <CountUp value={m.cost} decimals={2} prefix="$" />
            </div>
            <div className={cn("text-[11px]", m.current ? "text-foreground font-medium" : "text-muted-foreground")}>
              {m.label}
            </div>
          </div>
        );
      })}
    </div>
  );
}
