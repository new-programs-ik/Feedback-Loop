import * as React from "react";
import { niceTicks } from "@/components/charts/chart-kit";

export type RiskBarItem = {
  label: string;
  /** Share (0–100) of next classes that were low; null when there are too few pairs. */
  pct: number | null;
  /** Pairs behind the bar. */
  n: number;
  color: string;
};

/** Horizontal bars for the next-class risk per band, with the base rate drawn as a vertical
 *  dashed line every bar has to beat. A band with too few pairs shows the words, not a guess.
 *  A plain server-rendered SVG (the chart kit's HBars has no reference line). */
export function RiskBars({
  items,
  baseline,
  baselineLabel = "all classes",
  unit = "pairs",
}: {
  items: RiskBarItem[];
  baseline: { pct: number | null; n: number } | null;
  baselineLabel?: string;
  unit?: string;
}) {
  const W = 720;
  const labelW = 118;
  const valueW = 118;
  const mt = baseline?.pct != null ? 24 : 10;
  const mb = 22;
  const rowH = 34;
  const barH = 14;
  const x0 = labelW;
  const x1 = W - valueW;
  const H = mt + rowH * items.length + mb;
  const shown = items.map((i) => i.pct).filter((v): v is number => v != null);
  const top = Math.max(...shown, baseline?.pct ?? 0, 10);
  const max = Math.min(100, Math.ceil((top * 1.15) / 10) * 10);
  const x = (p: number) => x0 + (Math.min(Math.max(p, 0), max) / max) * (x1 - x0);
  const ticks = niceTicks(0, max, 4).filter((t) => t >= 0 && t <= max);
  const summary = items
    .map((i) => `${i.label}: ${i.pct == null ? `too few ${unit}` : `${Math.round(i.pct)}% of next classes low`} (${i.n} ${unit})`)
    .join("; ");
  const baseText = baseline?.pct != null ? `${baselineLabel} ${Math.round(baseline.pct)}%` : null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={`${summary}${baseText ? `; ${baseText}` : ""}.`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={mt} y2={H - mb} stroke="var(--chart-grid)" strokeWidth={1} strokeDasharray="1 3" />
          <text x={x(t)} y={H - 7} textAnchor="middle" className="fill-muted-foreground/80 font-mono text-[9.5px]">
            {t}%
          </text>
        </g>
      ))}
      {items.map((it, i) => {
        const y = mt + rowH * i;
        const by = y + (rowH - barH) / 2;
        const tip = it.pct == null ? x0 : x(it.pct);
        const r = 4;
        return (
          <g key={it.label}>
            <text x={x0 - 10} y={y + rowH / 2 + 4} textAnchor="end" className="fill-foreground text-[12.5px] font-medium">
              {it.label}
            </text>
            {it.pct != null ? (
              <>
                <path
                  d={`M${x0},${by}H${Math.max(tip - r, x0)}Q${tip},${by} ${tip},${by + r}V${by + barH - r}Q${tip},${by + barH} ${Math.max(tip - r, x0)},${by + barH}H${x0}Z`}
                  fill={it.color}
                />
                <text x={tip + 8} y={y + rowH / 2 + 4} className="fill-foreground text-[12.5px] font-semibold" data-numeric>
                  {Math.round(it.pct)}%
                  <tspan className="fill-muted-foreground text-[10.5px] font-normal"> · {it.n.toLocaleString()} {unit}</tspan>
                </text>
              </>
            ) : (
              <>
                <rect x={x0} y={by} width={x1 - x0} height={barH} rx={r} fill="none" stroke="var(--chart-grid)" strokeDasharray="3 3" />
                <text x={x0 + 8} y={y + rowH / 2 + 4} className="fill-muted-foreground text-[11px]">
                  too few {unit} to say · {it.n} of 20
                </text>
              </>
            )}
          </g>
        );
      })}
      {baseline?.pct != null && (
        <g>
          <line x1={x(baseline.pct)} x2={x(baseline.pct)} y1={mt - 4} y2={H - mb} stroke="var(--muted-foreground)" strokeWidth={1.5} strokeDasharray="5 4" />
          <text
            x={Math.min(Math.max(x(baseline.pct), x0 + 60), x1 - 60)}
            y={mt - 9}
            textAnchor="middle"
            className="fill-muted-foreground text-[10px] font-medium"
          >
            {baseText} · {baseline.n.toLocaleString()} {unit}
          </text>
        </g>
      )}
    </svg>
  );
}
