"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { EASE_OUT } from "@/components/motion/reveal";
import { ChartLegendContext, type LegendState } from "./chart-legend";

/** Card wrapper every chart lives in: title, optional subtitle, legend chips that toggle series
 *  (a hidden series' chip goes hollow), an optional actions slot, the chart, and a collapsible
 *  "View as table" twin (the accessibility + print channel — charts alone are not screen-reader
 *  friendly). */
export function ChartCard({
  title,
  subtitle,
  legend,
  children,
  table,
  actions,
  className,
}: {
  title: string;
  subtitle?: string;
  legend?: { label: string; color: string }[];
  children: React.ReactNode;
  /** The table twin: header row + body rows, rendered inside the expandable panel. */
  table?: { headers: string[]; rows: (string | number)[][] };
  /** Header-right slot for a filter, a download button, a link. */
  actions?: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const tableId = React.useId();
  const [open, setOpen] = React.useState(false);
  const [hidden, setHidden] = React.useState<ReadonlySet<string>>(() => new Set());
  const labels = React.useMemo(() => legend?.map((l) => l.label) ?? [], [legend]);
  const count = labels.length;
  // At least one series always stays visible — an empty chart tells nobody anything.
  const toggle = React.useCallback(
    (label: string) =>
      setHidden((prev) => {
        const next = new Set(prev);
        if (next.has(label)) next.delete(label);
        else {
          next.add(label);
          if (next.size >= count) return prev;
        }
        return next;
      }),
    [count],
  );
  const legendState = React.useMemo<LegendState>(() => ({ labels, hidden, toggle }), [labels, hidden, toggle]);

  return (
    <div className={cn("bg-card shadow-soft hover-lift rounded-xl border p-4 sm:p-5", className)}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">{title}</h3>
          {subtitle && <p className="text-muted-foreground mt-0.5 text-xs">{subtitle}</p>}
        </div>
        {((legend && legend.length > 1) || actions) && (
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            {legend && legend.length > 1 && (
              <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1" role="group" aria-label="Series">
                {legend.map((l) => {
                  const off = hidden.has(l.label);
                  return (
                    <button
                      key={l.label}
                      type="button"
                      aria-pressed={!off}
                      onClick={() => toggle(l.label)}
                      className={cn(
                        "text-muted-foreground hover:bg-muted/60 hover:text-foreground flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium transition-colors",
                        off && "text-muted-foreground/60",
                      )}
                    >
                      <span
                        aria-hidden
                        className="size-2 rounded-[2px] transition-[background-color,box-shadow] duration-200"
                        style={
                          off
                            ? { background: "transparent", boxShadow: `inset 0 0 0 1.5px ${l.color}` }
                            : { background: l.color }
                        }
                      />
                      {l.label}
                    </button>
                  );
                })}
              </div>
            )}
            {actions && <div className="flex items-center gap-1.5">{actions}</div>}
          </div>
        )}
      </div>
      {/* The chart sits in an INSET well — one surface step down — which is where the sense of
          depth comes from, not from shadows. */}
      <div className="print-exact surface-inset rounded-lg border px-2 pt-2 pb-1">
        <ChartLegendContext.Provider value={legendState}>{children}</ChartLegendContext.Provider>
      </div>
      {table && (
        <div className="mt-3" data-print-hide>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={tableId}
            onClick={() => setOpen((o) => !o)}
            className="text-muted-foreground hover:text-foreground -ml-1 flex items-center gap-1 rounded px-1 text-xs font-medium select-none"
          >
            <ChevronDown aria-hidden className={cn("size-3.5 transition-transform duration-200", open && "rotate-180")} />
            {open ? "Hide table" : "View as table"}
          </button>
          <AnimatePresence initial={false}>
            {open && (
              <motion.div
                key="table"
                id={tableId}
                initial={reduce ? false : { height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={reduce ? undefined : { height: 0, opacity: 0 }}
                transition={{ duration: 0.3, ease: EASE_OUT }}
                className="overflow-hidden"
              >
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b">
                        {table.headers.map((h, i) => (
                          <th
                            key={h}
                            className={cn(
                              "text-muted-foreground py-1.5 pr-3 text-left font-semibold",
                              i > 0 && "text-right",
                            )}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {table.rows.map((row, ri) => (
                        <tr key={ri} className="border-b last:border-0">
                          {row.map((cell, ci) => (
                            <td key={ci} className={cn("py-1.5 pr-3", ci > 0 && "text-right")} data-numeric>
                              {cell}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
