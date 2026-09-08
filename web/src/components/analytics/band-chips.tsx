import * as React from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import { BAND_META, BAND_ORDER, type Band } from "@/lib/sentiment";
import { cn } from "@/lib/utils";

export type BandChoice = Band | "none";
const CHOICES: BandChoice[] = [...BAND_ORDER, "none"];

const LABEL: Record<BandChoice, string> = {
  ...Object.fromEntries(BAND_ORDER.map((b) => [b, BAND_META[b].label])),
  none: "Too few to say",
} as Record<BandChoice, string>;

const WHAT: Record<BandChoice, string> = {
  ...Object.fromEntries(BAND_ORDER.map((b) => [b, BAND_META[b].description])),
  none: "not enough learners answered to give this class a band",
} as Record<BandChoice, string>;

/** The bands in a URL parameter, as a list. One value or several, comma separated. */
export function readBands(value?: string | null): BandChoice[] {
  if (!value) return [];
  const wanted = new Set(value.split(",").map((v) => v.trim()).filter(Boolean));
  return CHOICES.filter((c) => wanted.has(c));
}

export function bandsToParam(bands: BandChoice[]): string | undefined {
  const keep = CHOICES.filter((c) => bands.includes(c));
  return keep.length ? keep.join(",") : undefined;
}

/**
 * The colour key for the table, which is also how you filter it.
 *
 * The colours were on the rows with nothing saying what they meant, and the band filter was a
 * single-choice dropdown — so "show me the bad ones and the average ones" was not a thing you could
 * ask for. Each chip carries its own colour, says what that band means, and ticks on and off.
 */
export function BandChips({
  selected,
  counts,
  hrefFor,
  className,
}: {
  selected: BandChoice[];
  /** How many classes are in each band, before the band filter is applied. */
  counts?: Partial<Record<BandChoice, number>>;
  /** The URL for the list of bands that results from clicking a chip. */
  hrefFor: (bands: BandChoice[]) => string;
  className?: string;
}) {
  const on = new Set(selected);
  return (
    <div className={cn("mb-3 flex flex-wrap items-center gap-1.5", className)} data-print-hide>
      <span className="text-muted-foreground mr-0.5 text-[11px]">What the colours mean · click to filter</span>
      {CHOICES.map((b) => {
        const active = on.has(b);
        const next = active ? selected.filter((x) => x !== b) : [...selected, b];
        const meta = b === "none" ? null : BAND_META[b];
        const n = counts?.[b];
        return (
          <Link
            key={b}
            href={hrefFor(next)}
            scroll={false}
            aria-pressed={active}
            title={`${LABEL[b]} — ${WHAT[b]}`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
              active ? "border-transparent font-medium" : "hover:bg-muted/60 text-muted-foreground",
            )}
            style={
              active
                ? { background: meta ? meta.soft : "var(--muted)", color: meta ? meta.text : "inherit" }
                : undefined
            }
          >
            {active ? (
              <Check className="size-3" aria-hidden />
            ) : (
              <span
                className="size-2.5 rounded-full border"
                style={{ background: meta ? meta.color : "transparent" }}
                aria-hidden
              />
            )}
            {LABEL[b]}
            {n != null && (
              <span className="text-[11px] opacity-70" data-numeric>
                {n}
              </span>
            )}
          </Link>
        );
      })}
      {selected.length > 0 && (
        <Link href={hrefFor([])} scroll={false} className="text-muted-foreground ml-1 text-[11px] underline underline-offset-2">
          show all
        </Link>
      )}
    </div>
  );
}
