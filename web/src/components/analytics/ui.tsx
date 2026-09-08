import * as React from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

/** The analytics pages' working-screen kit: a quiet card, a dense KPI, a delta, the course
 *  identity square, a sticky-header table shell and a one-sentence empty state. Server-safe. */

export function Section({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  id,
  flush = false,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
  /** No inner padding (tables). */
  flush?: boolean;
}) {
  return (
    <section id={id} className={cn("bg-card shadow-soft report-section overflow-hidden rounded-xl border", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 px-4 pt-3.5 pb-2.5">
          <div className="min-w-0">
            {title && <h3 className="text-[13px] font-semibold tracking-[-0.01em]">{title}</h3>}
            {subtitle && <p className="text-muted-foreground mt-0.5 text-xs">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-1.5">{actions}</div>}
        </div>
      )}
      <div className={cn(!flush && "px-4 pb-4", flush && "border-t", bodyClassName)}>{children}</div>
    </section>
  );
}

/** A delta pill: arrow + magnitude; `goodWhen` decides the tone. Null renders nothing. */
export function Delta({
  value,
  decimals = 0,
  unit = "",
  suffix,
  goodWhen = "up",
  className,
}: {
  value: number | null | undefined;
  decimals?: number;
  unit?: string;
  suffix?: string;
  goodWhen?: "up" | "down";
  className?: string;
}) {
  if (value == null || Number.isNaN(value)) return null;
  const rounded = Number(value.toFixed(decimals));
  const flat = rounded === 0;
  const up = rounded > 0;
  const good = flat ? null : goodWhen === "up" ? up : !up;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap", className)}>
      <span
        className={cn(
          "inline-flex items-center gap-0.5 rounded-full px-1.5 py-px text-[11px] font-semibold",
          good == null ? "bg-muted text-muted-foreground" : good ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
        )}
        data-numeric
      >
        <Icon className="size-3" aria-hidden />
        {flat ? "0" : `${up ? "+" : "−"}${Math.abs(rounded).toFixed(decimals)}`}
        {unit}
      </span>
      {suffix && <span className="text-muted-foreground text-[11px]">{suffix}</span>}
    </span>
  );
}

/** A dense KPI: label · value · one line under it. No count-up, no icon, no tint. */
export function Kpi({
  label,
  value,
  sub,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("bg-card shadow-soft min-w-0 rounded-xl border px-4 py-3", className)}>
      <div className="text-muted-foreground text-[11px] font-medium">{label}</div>
      <div className="mt-1.5 flex min-h-7 items-center text-[22px] leading-none font-semibold tracking-[-0.02em]" data-numeric>
        {value}
      </div>
      <div className="text-muted-foreground mt-1.5 flex min-h-4 items-center gap-1.5 text-[11px]">{sub}</div>
    </div>
  );
}

/** The course identity square — the ONLY place the eight course colours appear. */
export function CourseSquare({ color, initials, size = 28, className }: { color: string; initials: string; size?: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-md font-semibold text-white", className)}
      style={{ background: color, width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.38)) }}
    >
      {initials}
    </span>
  );
}

/** Table shell: scrolls in its own box (never the page), header stays put, hairline rows,
 *  36px rows, numbers right-aligned by the cell classes. */
export function DataTable({ children, className, maxHeight = "70vh" }: { children: React.ReactNode; className?: string; maxHeight?: string }) {
  return (
    <div className={cn("relative w-full overflow-auto", className)} style={{ maxHeight }}>
      <table className="w-full min-w-max text-[13px] [&_tbody_td]:h-9 [&_tbody_td]:py-1 [&_thead_th]:sticky [&_thead_th]:top-0 [&_thead_th]:z-[1]">
        {children}
      </table>
    </div>
  );
}

/** One sentence and the action that fixes it — no illustration. */
export function Empty({ children, action, className }: { children: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-6 text-[13px]", className)}>
      <span>{children}</span>
      {action}
    </div>
  );
}

/** A row label that is also the row's link (the whole row is clickable through the overlay). */
export function RowLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <Link href={href} className={cn("hover:text-primary font-medium after:absolute after:inset-0", className)}>
      {children}
    </Link>
  );
}

/** Small uppercase label used above compact blocks. */
export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("text-muted-foreground text-[10.5px] font-semibold tracking-[0.08em] uppercase", className)}>{children}</div>;
}

/** Inline live/review chip. */
export function KindChip({ kind }: { kind: string }) {
  const short = kind === "Live Class" ? "Live" : kind === "Test Review" ? "Review" : kind || "—";
  return <span className="text-muted-foreground inline-flex items-center rounded border px-1.5 py-px text-[10.5px] font-medium">{short}</span>;
}
