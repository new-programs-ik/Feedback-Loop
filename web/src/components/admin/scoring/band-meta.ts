/** Band presentation for the admin surfaces, on top of the shell's `BAND_META` (lib/sentiment):
 *  adds the grey "too few responses" bucket the preview needs, and the per-analysis costs the study
 *  uses. Pure — safe in server and client code. */

import { BAND_META, type Action, type Band } from "@/lib/sentiment";

export type BandKey = Band | "no_data";
export const BAND_KEYS: readonly BandKey[] = ["excellent", "good", "average", "bad", "no_data"] as const;

export function bandMeta(b: BandKey): { label: string; short: string; color: string; soft: string } {
  if (b === "no_data") {
    return {
      label: "Too few responses",
      short: "—",
      color: "var(--band-none, oklch(0.7 0.01 262))",
      soft: "color-mix(in oklch, var(--band-none, oklch(0.7 0.01 262)) 25%, transparent)",
    };
  }
  const m = BAND_META[b];
  return { label: m.label, short: m.short, color: m.color, soft: m.soft };
}

/** Per-analysis cost the study uses: video $0.70, transcript $0.51. */
export const COST_PER_ANALYSIS: Record<Action, number> = { video: 0.7, transcript: 0.51, none: 0, watch: 0 };
