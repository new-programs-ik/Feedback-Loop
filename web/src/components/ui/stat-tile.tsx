import * as React from "react";
import { ArrowDownRight, ArrowUpRight, type LucideIcon } from "lucide-react";
import { CountUp } from "@/components/motion/count-up";
import { cn } from "@/lib/utils";

/** KPI tile: quiet label row · a confident number · a tinted delta pill vs a named period ·
 *  an integrated sparkline. Numbers use tabular figures + tight tracking; the tile never shouts —
 *  tone colors the delta, not the whole value, unless the metric itself is a problem count.
 *  Pass `count` instead of `value` and the number counts up the first time it scrolls into view. */
function StatTile({
  label,
  value,
  count,
  note,
  delta,
  icon: Icon,
  tone = "default",
  sparkline,
  className,
}: {
  label: string;
  value?: React.ReactNode;
  count?: { value: number; decimals?: number; prefix?: string; suffix?: string };
  note?: string;
  /** e.g. { text: "0.04", suffix: "vs prior 90d", good: false, direction: "down" } */
  delta?: { text: string; suffix?: string; good?: boolean; direction?: "up" | "down" };
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
  const DeltaArrow = delta?.direction === "down" ? ArrowDownRight : ArrowUpRight;
  return (
    <div data-slot="stat-tile" className={cn("bg-card shadow-soft hover-lift rounded-xl border p-4", className)}>
      <div className="flex items-center gap-1.5">
        {Icon && <Icon className="text-muted-foreground/70 size-3.5" aria-hidden />}
        <p className="text-muted-foreground text-xs font-medium">{label}</p>
      </div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <p
          data-numeric
          className={cn("text-[27px] leading-none font-semibold tracking-[-0.02em]", toneClass)}
        >
          {count ? (
            <CountUp value={count.value} decimals={count.decimals} prefix={count.prefix} suffix={count.suffix} />
          ) : (
            value
          )}
        </p>
        {sparkline && <div className="shrink-0 pb-0.5 opacity-80">{sparkline}</div>}
      </div>
      <div className="mt-2.5 flex min-h-5 items-center gap-1.5">
        {delta && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full px-1.5 py-px text-[11px] font-semibold",
              delta.good == null
                ? "bg-muted text-muted-foreground"
                : delta.good
                  ? "bg-success/10 text-success"
                  : "bg-destructive/10 text-destructive",
            )}
          >
            <DeltaArrow className="size-3" aria-hidden />
            {delta.text}
          </span>
        )}
        {(delta?.suffix || note) && (
          <span className="text-muted-foreground truncate text-[11px]">{delta?.suffix ?? note}</span>
        )}
      </div>
    </div>
  );
}

export { StatTile };
