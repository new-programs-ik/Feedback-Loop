import * as React from "react";
import { HBarRows, type HBarRow } from "./h-bars-rows";

/** Horizontal bars for one measure across nominal categories (instructor breakdowns etc.).
 *  One series → ONE color (never a ramp on nominal categories) unless each item carries its own
 *  `color` (band-tinted hot-spots); value labelled at the bar tip; 4px rounded cap at the data
 *  end, square at the baseline. `center` turns it into a diverging chart: bars grow left or
 *  right from the centre value (e.g. an instructor's module scores around the course's module
 *  average). Server-safe: `format` runs here and only strings cross into the client rows. */
export function HBars({
  items,
  color = "var(--chart-1)",
  format = (v: number) => String(v),
  maxValue,
  center,
  domain,
}: {
  items: { label: string; value: number; href?: string; color?: string; sub?: string }[];
  color?: string;
  format?: (v: number) => string;
  maxValue?: number;
  /** Diverging mode: bars extend from this value. */
  center?: number;
  /** Diverging mode: the value range drawn (defaults to the data's extent around the centre). */
  domain?: [number, number];
}) {
  if (items.length === 0) return null;
  let rows: HBarRow[];
  let centerPct: number | undefined;
  if (center != null) {
    const vals = items.map((i) => i.value);
    const spread = Math.max(Math.abs(Math.max(...vals) - center), Math.abs(Math.min(...vals) - center), 1);
    const min = domain?.[0] ?? center - spread;
    const max = domain?.[1] ?? center + spread;
    const pos = (v: number) => ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * 100;
    centerPct = pos(center);
    rows = items.map((item) => {
      const p = pos(item.value);
      const negative = item.value < center;
      return {
        label: item.label,
        sub: item.sub,
        href: item.href,
        start: negative ? p : centerPct!,
        width: Math.max(Math.abs(p - centerPct!), 0.5),
        negative,
        color: item.color ?? color,
        text: `${item.value >= center ? "+" : "−"}${format(Math.abs(item.value - center))}`,
      };
    });
  } else {
    const max = maxValue ?? Math.max(...items.map((i) => i.value), 0.0001);
    rows = items.map((item) => ({
      label: item.label,
      sub: item.sub,
      href: item.href,
      start: 0,
      width: Math.max((item.value / max) * 100, 0.5),
      negative: false,
      color: item.color ?? color,
      text: format(item.value),
    }));
  }
  return <HBarRows rows={rows} centerPct={centerPct} />;
}
