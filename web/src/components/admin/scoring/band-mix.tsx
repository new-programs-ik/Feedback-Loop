"use client";

import { BandStrip } from "@/components/score/score-pill";
import { cn } from "@/lib/utils";
import { bandMeta, type BandKey } from "./band-meta";

/** The shell's BandStrip plus the bucket it does not draw: classes with too few voices for a
 *  band. That share is exactly what a vote floor changes, so the preview must show it. */
export function BandMix({ counts, compact = false, className }: { counts: Partial<Record<BandKey, number>>; compact?: boolean; className?: string }) {
  const none = counts.no_data ?? 0;
  const total = (["excellent", "good", "average", "bad"] as const).reduce((a, k) => a + (counts[k] ?? 0), 0) + none;
  return (
    <div className={cn("min-w-0", className)}>
      <BandStrip counts={counts} showCounts={!compact} height={compact ? "h-1.5" : "h-2"} />
      {none > 0 && (
        <p className={cn("text-muted-foreground inline-flex items-center gap-1 text-[11px]", compact ? "mt-0.5" : "mt-1")}>
          <span aria-hidden className="inline-block size-2 rounded-sm" style={{ background: bandMeta("no_data").color }} />
          {bandMeta("no_data").label}
          <span className="text-foreground font-medium" data-numeric>
            {none}
          </span>
          {total > 0 && !compact && <span>· {Math.round((none / total) * 100)}%</span>}
        </p>
      )}
    </div>
  );
}
