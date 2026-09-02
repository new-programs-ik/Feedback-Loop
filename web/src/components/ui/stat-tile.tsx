import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** KPI stat tile: label · big value · optional delta vs a named period · optional sparkline.
 *  The big number stays proportional (not tabular) — it's display type, not a table column. */
function StatTile({
  label,
  value,
  note,
  delta,
  icon: Icon,
  tone = "default",
  sparkline,
  className,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
  /** e.g. { text: "+0.12 vs July", good: true } — direction × goodness decided by the caller. */
  delta?: { text: string; good?: boolean };
  icon?: LucideIcon;
  tone?: "default" | "primary" | "success" | "warning" | "destructive";
  sparkline?: React.ReactNode;
  className?: string;
}) {
  const toneClass = {
    default: "text-foreground",
    primary: "text-primary",
    success: "text-success",
    warning: "text-warning",
    destructive: "text-destructive",
  }[tone];
  return (
    <div
      data-slot="stat-tile"
      className={cn("bg-card shadow-soft rounded-xl border p-4", className)}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-muted-foreground text-[13px] font-medium">{label}</p>
        {Icon && (
          <span className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
            <Icon className="size-4" aria-hidden />
          </span>
        )}
      </div>
      <div className="mt-1.5 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className={cn("text-[26px] leading-8 font-semibold tracking-tight", toneClass)}>{value}</p>
          {delta ? (
            <p
              className={cn(
                "mt-0.5 text-xs font-medium",
                delta.good == null
                  ? "text-muted-foreground"
                  : delta.good
                    ? "text-success"
                    : "text-destructive",
              )}
            >
              {delta.text}
            </p>
          ) : note ? (
            <p className="text-muted-foreground mt-0.5 text-xs">{note}</p>
          ) : null}
        </div>
        {sparkline && <div className="mb-1 shrink-0">{sparkline}</div>}
      </div>
    </div>
  );
}

export { StatTile };
