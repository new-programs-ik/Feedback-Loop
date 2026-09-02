import * as React from "react";
import { cn } from "@/lib/utils";

/** The report-style finding card: a left accent bar and a claim stated in one line, then the
 *  evidence. This is how a finding is TOLD, not just displayed. */
export function Callout({
  tone = "warn",
  title,
  children,
  className,
}: {
  tone?: "warn" | "ok";
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-card shadow-soft rounded-xl border border-l-4 p-4 sm:p-5",
        tone === "warn" ? "border-l-[var(--viz-bad)]" : "border-l-[var(--chart-1)]",
        className,
      )}
    >
      <h3 className="text-[13.5px] font-semibold tracking-[-0.01em]">{title}</h3>
      <div className="text-muted-foreground mt-1.5 text-[13px] leading-relaxed [&_b]:text-foreground [&_b]:font-semibold">
        {children}
      </div>
    </div>
  );
}

/** Editorial section header: numbered, with the report's border-top rhythm. */
export function SectionHeader({
  n,
  title,
  className,
}: {
  n?: number;
  title: string;
  className?: string;
}) {
  return (
    <h2 className={cn("mt-8 mb-3 border-t pt-5 text-[15px] font-semibold tracking-[-0.01em]", className)}>
      {n != null && <span className="text-muted-foreground mr-1.5" data-numeric>{n}.</span>}
      {title}
    </h2>
  );
}
