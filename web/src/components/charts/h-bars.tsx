import * as React from "react";
import { parseNumeric } from "./chart-kit";
import { HBarRows } from "./h-bars-rows";

/** Horizontal bars for one measure across nominal categories (instructor breakdowns etc.).
 *  One series → ONE color (never a ramp on nominal categories); value labelled at the bar tip;
 *  4px rounded cap at the data end, square at the baseline. Server-safe: `format` runs here and
 *  only strings cross into the client rows, where bars grow from the left and numeric labels
 *  count up. */
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
  const rows = items.map((item) => {
    const text = format(item.value);
    return {
      label: item.label,
      href: item.href,
      pct: Math.max((item.value / max) * 100, 0.5),
      text,
      numeric: parseNumeric(text),
    };
  });
  return <HBarRows rows={rows} color={color} />;
}
