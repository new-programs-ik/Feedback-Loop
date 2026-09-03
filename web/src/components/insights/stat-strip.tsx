import * as React from "react";
import { Stagger, StaggerItem } from "@/components/motion/reveal";
import { CountUp } from "@/components/motion/count-up";
import { PRINT_SAFE } from "@/components/insights/print-safe";
import { cn } from "@/lib/utils";

export type StatStripItem = {
  /** Server-computed. `null` renders an em dash (no count). */
  value: number | null;
  decimals?: number;
  suffix?: string;
  label: string;
  /** The metric itself is a problem count — the number wears the destructive tone. */
  bad?: boolean;
};

/** The study's opening numbers: five quiet tiles that stagger in and count up the first time
 *  they scroll into view. Server-safe — the tiles are plain markup, CountUp is the island.
 *  The lift lives on the inner card, not the motion wrapper (motion pins its own transform). */
export function StatStrip({ items, className }: { items: StatStripItem[]; className?: string }) {
  return (
    <Stagger className={cn("grid gap-3 sm:grid-cols-2 xl:grid-cols-5", PRINT_SAFE, className)} step={0.07}>
      {items.map((s) => (
        <StaggerItem key={s.label} className={PRINT_SAFE}>
          <div className="bg-card shadow-soft hover-lift h-full rounded-xl border p-4">
            <div
              className={cn("text-[26px] leading-none font-semibold tracking-[-0.02em]", s.bad && "text-destructive")}
              data-numeric
            >
              {s.value == null ? "—" : <CountUp value={s.value} decimals={s.decimals} suffix={s.suffix} />}
            </div>
            <div className="text-muted-foreground mt-1.5 text-xs">{s.label}</div>
          </div>
        </StaggerItem>
      ))}
    </Stagger>
  );
}
