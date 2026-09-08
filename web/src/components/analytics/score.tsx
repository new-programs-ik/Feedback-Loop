import * as React from "react";
import { ScorePill, BandStrip } from "@/components/score/score-pill";
import { BAND_META, DEFAULT_CONFIG, bandOf, type Band } from "@/lib/sentiment";
import type { ScoredRating } from "@/lib/analytics";
import { cn } from "@/lib/utils";

/** Thin adapters so every page draws a score the same way; the score components themselves are
 *  C1's (`@/components/score/score-pill`). Server-safe — the pill is the client island. */

/** A class's own score: number + band; hover shows the four inputs and what each earned. */
export function ClassScorePill({ row, variant = "sm", className }: { row: ScoredRating; variant?: "sm" | "md" | "lg"; className?: string }) {
  if (row.score == null || row.band == null) {
    return <ScorePill score={row.score} band={null} variant="empty" className={className} />;
  }
  return (
    <ScorePill
      score={row.score}
      band={row.band}
      variant={variant}
      provisional={row.provisional}
      action={row.action}
      breakdown={{ rows: row.breakdown, reason: row.reason, version: row.scored_by === "db" ? undefined : "preview" }}
      className={className}
    />
  );
}

/** An average (course · instructor · cohort · module): outlined, says "avg". */
export function AvgScorePill({
  score,
  label = "avg",
  className,
  variant = "aggregate",
}: {
  score: number | null | undefined;
  label?: string;
  className?: string;
  variant?: "aggregate" | "lg";
}) {
  if (score == null) return <ScorePill score={null} band={null} variant="empty" emptyText="no scored classes" className={className} />;
  const rounded = Math.round(score);
  return <ScorePill score={rounded} band={bandOf(rounded)} variant={variant === "lg" ? "lg" : "aggregate"} label={label} className={className} />;
}

export function BandStripOf({
  counts,
  className,
  showCounts = false,
  height = "h-1.5",
}: {
  counts: { excellent: number; good: number; average: number; bad: number };
  className?: string;
  showCounts?: boolean;
  height?: string;
}) {
  return <BandStrip counts={counts} className={cn("min-w-16", className)} showCounts={showCounts} height={height} />;
}

/** A bullet: the value as a thick bar over the four band zones, the reference (course average)
 *  as a tick — "does this instructor carry or drag?". Server-safe SVG. */
export function CompareBullet({
  value,
  reference,
  min = 40,
  max = 100,
  label = "score",
  referenceLabel = "course avg",
  width = 96,
  className,
}: {
  value: number | null;
  reference: number | null;
  min?: number;
  max?: number;
  label?: string;
  referenceLabel?: string;
  width?: number;
  className?: string;
}) {
  const H = 10;
  const edges = DEFAULT_CONFIG.bands;
  const x = (v: number) => ((Math.max(min, Math.min(max, v)) - min) / (max - min)) * width;
  const zones: [number, number, Band][] = [
    [min, edges.average, "bad"],
    [edges.average, edges.good, "average"],
    [edges.good, edges.excellent, "good"],
    [edges.excellent, max, "excellent"],
  ];
  const title = value == null ? "no score" : `${label} ${Math.round(value)}${reference != null ? ` · ${referenceLabel} ${Math.round(reference)}` : ""}`;
  return (
    <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} className={cn("inline-block overflow-visible align-middle", className)} role="img" aria-label={title}>
      <title>{title}</title>
      {zones.map(([a, b, band]) => (
        <rect key={band} x={x(a)} y={0} width={Math.max(0, x(b) - x(a))} height={H} fill={BAND_META[band].color} fillOpacity={0.16} />
      ))}
      {value != null && <rect x={0} y={3} width={x(value)} height={4} rx={1} fill={BAND_META[bandOf(Math.round(value))].color} />}
      {reference != null && <rect x={x(reference) - 1} y={-1} width={2} height={H + 2} fill="var(--foreground)" fillOpacity={0.75} />}
    </svg>
  );
}

/** The band label as coloured text (for a table cell where a full pill is too much). */
export function BandWord({ band, className }: { band: Band | null; className?: string }) {
  if (!band) return <span className={cn("text-muted-foreground", className)}>—</span>;
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-medium", className)} style={{ color: BAND_META[band].text }}>
      <span aria-hidden className="inline-block size-1.5 rounded-full" style={{ background: BAND_META[band].color }} />
      {BAND_META[band].label}
    </span>
  );
}
