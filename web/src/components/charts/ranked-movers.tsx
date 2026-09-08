import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export type MoverItem = {
  key: string;
  label: string;
  sub?: string;
  href?: string;
  before: number | null;
  after: number | null;
  delta: number;
  nBefore?: number;
  nAfter?: number;
};

/** Biggest changes, up and down, side by side: a diverging bar per item with the delta at the
 *  tip and "before → after" beneath. Server-safe (plain markup). */
export function RankedMovers({
  items,
  limit = 6,
  decimals = 0,
  unit = "",
  upLabel = "Up",
  downLabel = "Down",
  emptyText = "Nothing with enough classes in both periods.",
  className,
}: {
  items: MoverItem[];
  limit?: number;
  decimals?: number;
  unit?: string;
  upLabel?: string;
  downLabel?: string;
  emptyText?: string;
  className?: string;
}) {
  const up = items.filter((m) => m.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, limit);
  const down = items.filter((m) => m.delta < 0).sort((a, b) => a.delta - b.delta).slice(0, limit);
  const max = Math.max(...items.map((m) => Math.abs(m.delta)), 1);
  if (up.length === 0 && down.length === 0) return <p className="text-muted-foreground text-[13px]">{emptyText}</p>;
  const fmt = (v: number | null) => (v == null ? "—" : v.toFixed(decimals) + unit);
  const Row = ({ m, dir }: { m: MoverItem; dir: "up" | "down" }) => (
    <li className="grid grid-cols-[minmax(0,1fr)_88px_auto] items-center gap-2 py-1">
      <div className="min-w-0">
        {m.href ? (
          <Link href={m.href} className="hover:text-primary block truncate text-[12.5px] font-medium">
            {m.label}
          </Link>
        ) : (
          <span className="block truncate text-[12.5px] font-medium">{m.label}</span>
        )}
        <span className="text-muted-foreground block truncate text-[10.5px]" data-numeric>
          {fmt(m.before)} → {fmt(m.after)}
          {m.nBefore != null && m.nAfter != null ? ` · ${m.nBefore} → ${m.nAfter} classes` : m.sub ? ` · ${m.sub}` : ""}
        </span>
      </div>
      <span className="bg-muted relative h-2.5 overflow-hidden rounded-[3px]">
        <span
          className={cn("absolute inset-y-0", dir === "up" ? "left-0 rounded-r-[3px]" : "right-0 rounded-l-[3px]")}
          style={{ width: `${(Math.abs(m.delta) / max) * 100}%`, background: dir === "up" ? "var(--chart-1)" : "var(--chart-2)" }}
        />
      </span>
      <span className={cn("w-12 text-right font-mono text-[12px] font-semibold", dir === "down" && "text-[var(--chart-2)]")} data-numeric>
        {dir === "up" ? "+" : "−"}
        {Math.abs(m.delta).toFixed(decimals)}
      </span>
    </li>
  );
  return (
    <div className={cn("grid gap-x-6 gap-y-3 md:grid-cols-2", className)}>
      <div>
        <div className="text-muted-foreground mb-1 text-[10.5px] font-semibold tracking-[0.08em] uppercase">{upLabel}</div>
        {up.length ? <ul className="divide-y">{up.map((m) => <Row key={m.key} m={m} dir="up" />)}</ul> : <p className="text-muted-foreground text-xs">None.</p>}
      </div>
      <div>
        <div className="text-muted-foreground mb-1 text-[10.5px] font-semibold tracking-[0.08em] uppercase">{downLabel}</div>
        {down.length ? <ul className="divide-y">{down.map((m) => <Row key={m.key} m={m} dir="down" />)}</ul> : <p className="text-muted-foreground text-xs">None.</p>}
      </div>
    </div>
  );
}
