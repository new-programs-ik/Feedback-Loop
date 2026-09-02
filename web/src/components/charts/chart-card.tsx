import * as React from "react";
import { cn } from "@/lib/utils";

/** Card wrapper every chart lives in: title, optional subtitle, legend row, the chart, and a
 *  collapsible "View as table" twin (the accessibility + print channel — charts alone are not
 *  screen-reader friendly). */
export function ChartCard({
  title,
  subtitle,
  legend,
  children,
  table,
  className,
}: {
  title: string;
  subtitle?: string;
  legend?: { label: string; color: string }[];
  children: React.ReactNode;
  /** The table twin: header row + body rows, rendered inside <details>. */
  table?: { headers: string[]; rows: (string | number)[][] };
  className?: string;
}) {
  return (
    <div className={cn("bg-card shadow-soft rounded-xl border p-4 sm:p-5", className)}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">{title}</h3>
          {subtitle && <p className="text-muted-foreground mt-0.5 text-xs">{subtitle}</p>}
        </div>
        {legend && legend.length > 1 && (
          <div className="flex flex-wrap items-center gap-3">
            {legend.map((l) => (
              <span key={l.label} className="text-muted-foreground flex items-center gap-1.5 text-[11px] font-medium">
                <span className="size-2 rounded-[2px]" style={{ background: l.color }} aria-hidden />
                {l.label}
              </span>
            ))}
          </div>
        )}
      </div>
      {/* The chart sits in an INSET well — one surface step down — which is where the sense of
          depth comes from, not from shadows. */}
      <div className="print-exact surface-inset rounded-lg border px-2 pt-2 pb-1">{children}</div>
      {table && (
        <details className="mt-3" data-print-hide>
          <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-xs font-medium select-none">
            View as table
          </summary>
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
        </details>
      )}
    </div>
  );
}
