"use client";

import Link from "next/link";
import { ChevronRight, TriangleAlert } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { EASE_OUT } from "@/components/motion/reveal";
import { BandDot } from "@/components/ui/table";
import { approvalTone } from "@/components/priority-chip";
import { APPROVAL_BAR, GOOD } from "@/lib/decision";
import { cn } from "@/lib/utils";

export type PulseRow = {
  key: string;
  name: string;
  href: string;
  classes: number;
  /** Classes rated below the line in the window — the bar. */
  below: number;
  avgRating: number | null;
  approval: number | null;
  /** Urgent rows for this course currently in the queue. */
  urgent: number;
};

/** Ratings pulse by course: one bar per course (classes below the line, one hue — it is one
 *  measure across nominal categories), the pooled approval beside it, and an urgent chip when
 *  the queue holds urgent rows for that course. Bars grow from zero the first time they are seen.
 *  Every row links into the queue scoped to that course. */
export function PulseBars({ rows, max }: { rows: PulseRow[]; max: number }) {
  const reduce = useReducedMotion();
  const denom = Math.max(max, 1);
  return (
    <ul className="divide-y">
      {rows.map((r, i) => {
        const pct = Math.min(100, (r.below / denom) * 100);
        const underBar = r.approval != null && r.approval < APPROVAL_BAR;
        return (
          <li key={r.key}>
            <Link
              href={r.href}
              className="group -mx-2 grid grid-cols-[minmax(96px,9rem)_minmax(0,1fr)_3.75rem_4.5rem_auto] items-center gap-x-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-accent/40"
              aria-label={`${r.name}: ${r.below} of ${r.classes} classes below ${GOOD}${r.approval != null ? `, ${Math.round(r.approval)}% would have the instructor back` : ""}${r.urgent ? `, ${r.urgent} urgent` : ""}`}
            >
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-medium" title={r.name}>{r.name}</span>
                <span className="text-muted-foreground block text-[11px]" data-numeric>
                  {r.classes} {r.classes === 1 ? "class" : "classes"}
                  {r.avgRating != null && (
                    <>
                      {" · "}
                      <BandDot tone={r.avgRating < GOOD ? "bad" : r.avgRating < 4.7 ? "warn" : "good"} />
                      {r.avgRating.toFixed(2)}
                    </>
                  )}
                </span>
              </span>

              <span className="flex items-center gap-2">
                <span className="bg-muted relative h-2 flex-1 overflow-hidden rounded-full">
                  <motion.span
                    aria-hidden
                    className="absolute inset-y-0 left-0 rounded-r-full"
                    style={{ width: `${pct}%`, background: "var(--viz-bad)", transformOrigin: "left center" }}
                    initial={reduce ? false : { scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.7, ease: EASE_OUT, delay: 0.1 + i * 0.06 }}
                  />
                </span>
                <span
                  className={cn("w-14 shrink-0 text-[12px] font-semibold", r.below === 0 && "text-muted-foreground font-normal")}
                  data-numeric
                >
                  {r.below} below
                </span>
              </span>

              <span
                className={cn("text-right text-[13px]", underBar ? "text-destructive font-semibold" : "text-muted-foreground")}
                data-numeric
                title="Share of voters who would have the instructor back"
              >
                {r.approval != null ? (
                  <>
                    <BandDot tone={approvalTone(r.approval)} />
                    {Math.round(r.approval)}%
                  </>
                ) : (
                  "—"
                )}
              </span>

              <span className="flex justify-end">
                {r.urgent > 0 ? (
                  <span className="bg-destructive/10 text-destructive inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap">
                    <TriangleAlert className="size-3" aria-hidden />
                    <span data-numeric>{r.urgent}</span> urgent
                  </span>
                ) : (
                  <span className="text-muted-foreground/50 text-[11px]">—</span>
                )}
              </span>

              <ChevronRight
                className="text-muted-foreground/50 group-hover:text-foreground size-4 shrink-0 transition-colors"
                aria-hidden
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
