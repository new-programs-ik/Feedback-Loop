/** Shared math + conventions for the hand-rolled SVG chart kit.
 *
 *  Design contract (dataviz rules, applied everywhere):
 *  - thin marks: 2px lines, columns <= 24px wide, 4px rounded caps at the DATA end only;
 *  - one axis per chart, hairline solid grid in --chart-grid, labels in text tokens;
 *  - categorical series use --chart-1..8 in FIXED order (never cycled, never re-sorted);
 *  - ordinal/heat data uses --chart-seq-1..5; status colors are never series colors;
 *  - every multi-series chart shows a legend; every chart ships a table twin (chart-card).
 */

export const SERIES = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
] as const;

export const SEQ = [
  "var(--chart-seq-1)",
  "var(--chart-seq-2)",
  "var(--chart-seq-3)",
  "var(--chart-seq-4)",
  "var(--chart-seq-5)",
] as const;

/** "Nice" ascending tick values covering [min, max] (3-5 ticks). */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!isFinite(min) || !isFinite(max)) return [];
  if (min === max) {
    max = min + 1;
  }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 5 : norm >= 2.5 ? 2.5 : norm >= 2 ? 2 : 1) * mag;
  const start = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

export function scaleLinear(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const m = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v: number) => r0 + (v - d0) * m;
}

export function fmtRating(v: number): string {
  return v.toFixed(2).replace(/\.?0+$/, (m) => (m === ".00" ? "" : m.replace(/0+$/, "")));
}

export function fmtMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, 1).toLocaleString("en-US", { month: "short" });
}

export function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Rough advance width of `text` at `px` (Geist ≈ 0.56em per character) — enough to reserve
 *  room for direct labels without measuring the DOM. */
export function estimateTextWidth(text: string, px = 10.5): number {
  return text.length * px * 0.56;
}

/** Split a formatted value ("$1,240", "78%", "4.55") into what CountUp needs, or null when the
 *  string is not a single number. A 4+ digit integer written WITHOUT separators is rejected: the
 *  counter would add commas and change the label's shape mid-count. */
export function parseNumeric(
  s: string,
): { prefix: string; value: number; decimals: number; suffix: string } | null {
  const m = /^([^\d-]*)(-?\d[\d,]*)(?:\.(\d+))?([^\d]*)$/.exec(s.trim());
  if (!m) return null;
  const [, prefix, int, frac = "", suffix] = m;
  if (int.replace("-", "").length > 3 && !int.includes(",")) return null;
  const value = Number(int.replace(/,/g, "") + (frac ? `.${frac}` : ""));
  if (!Number.isFinite(value)) return null;
  return { prefix, value, decimals: frac.length, suffix };
}
