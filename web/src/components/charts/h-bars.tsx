import * as React from "react";

/** Horizontal bars for one measure across nominal categories (instructor breakdowns etc.).
 *  One series → ONE color (never a ramp on nominal categories); value labelled at the bar tip;
 *  4px rounded cap at the data end, square at the baseline. Server-safe. */
export function HBars({
  items,
  color = "var(--chart-1)",
  format = (v: number) => String(v),
  maxValue,
}: {
  items: { label: string; value: number; href?: string }[];
  color?: string;
  format?: (v: number) => string;
  maxValue?: number;
}) {
  if (items.length === 0) return null;
  const max = maxValue ?? Math.max(...items.map((i) => i.value), 0.0001);
  return (
    <div className="space-y-2.5">
      {items.map((item) => {
        const pct = Math.max((item.value / max) * 100, 0.5);
        const row = (
          <div className="grid grid-cols-[minmax(90px,160px)_1fr_auto] items-center gap-3">
            <span className="truncate text-[13px]" title={item.label}>
              {item.label}
            </span>
            <span className="bg-muted relative h-3.5 overflow-hidden rounded-[4px]">
              <span
                className="absolute inset-y-0 left-0 rounded-r-[4px]"
                style={{ width: `${pct}%`, background: color }}
              />
            </span>
            <span className="text-[13px] font-semibold" data-numeric>
              {format(item.value)}
            </span>
          </div>
        );
        return item.href ? (
          <a key={item.label} href={item.href} className="hover:bg-muted/40 -mx-1 block rounded px-1 py-0.5">
            {row}
          </a>
        ) : (
          <div key={item.label}>{row}</div>
        );
      })}
    </div>
  );
}
