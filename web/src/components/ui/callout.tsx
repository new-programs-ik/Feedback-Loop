import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** The report-style finding card: a left accent bar and a claim stated in one line, then the
 *  evidence. This is how a finding is TOLD, not just displayed. An optional icon sits beside the
 *  claim in the accent colour — status is carried by the bar + icon + words, never colour alone. */
export function Callout({
  tone = "warn",
  title,
  icon: Icon,
  children,
  className,
}: {
  tone?: "warn" | "ok";
  title: string;
  icon?: LucideIcon;
  children: React.ReactNode;
  className?: string;
}) {
  const accent = tone === "warn" ? "var(--viz-bad)" : "var(--chart-1)";
  return (
    <div
      data-slot="callout"
      data-tone={tone}
      className={cn("bg-card shadow-soft rounded-xl border border-l-4 p-4 sm:p-5", className)}
      style={{ borderLeftColor: accent }}
    >
      <div className="flex items-start gap-2.5">
        {Icon && (
          <span
            aria-hidden
            className="mt-px flex size-6 shrink-0 items-center justify-center rounded-md"
            style={{ color: accent, background: `color-mix(in oklch, ${accent} 12%, transparent)` }}
          >
            <Icon className="size-3.5" />
          </span>
        )}
        <div className="min-w-0">
          <h3 className="text-[13.5px] leading-snug font-semibold tracking-[-0.01em]">{title}</h3>
          <div className="text-muted-foreground mt-1.5 text-[13px] leading-relaxed [&_b]:text-foreground [&_b]:font-semibold">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Editorial section header: numbered, with the report's border-top rhythm. `id` makes it a
 *  scroll target (with headroom for the sticky chrome); `icon` sits quietly before the title. */
export function SectionHeader({
  n,
  title,
  icon: Icon,
  id,
  className,
}: {
  n?: number;
  title: string;
  icon?: LucideIcon;
  id?: string;
  className?: string;
}) {
  return (
    <h2
      id={id}
      className={cn(
        "mt-9 mb-3 flex items-baseline gap-1.5 border-t pt-5 text-[15px] font-semibold tracking-[-0.01em]",
        id && "scroll-mt-28",
        className,
      )}
    >
      {n != null && (
        <span className="text-muted-foreground shrink-0" data-numeric>
          {n}.
        </span>
      )}
      {Icon && <Icon className="text-muted-foreground size-4 shrink-0 self-center" aria-hidden />}
      <span>{title}</span>
    </h2>
  );
}
