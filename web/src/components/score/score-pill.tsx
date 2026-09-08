"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  BAND_META,
  BAND_ORDER,
  ACTION_LABEL,
  type Action,
  type Band,
  type ComponentRow,
} from "@/lib/sentiment";

export { BAND_META, BAND_ORDER };

/** The breakdown a pill can show on hover / focus: the inputs and what each earned. */
export type ScoreBreakdown = {
  rows: ComponentRow[];
  /** "version 2" — the scoring configuration that produced the score. */
  version?: string | number | null;
  /** "Good → no analysis unless a PM asks." */
  rule?: string | null;
  /** The one-sentence reason (shown under the rule). */
  reason?: string | null;
};

export type ScorePillVariant = "sm" | "md" | "lg" | "aggregate" | "empty";

const fmtScore = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(v * 10 === Math.round(v * 10) ? 1 : 2));

function bandLabel(band: Band | null, provisional: boolean) {
  if (!band) return "—";
  return BAND_META[band].label + (provisional ? " · prov." : "");
}

/** One component draws every score: number + band label, ALWAYS (colour only reinforces), a
 *  4px band bar underneath, tabular digits. Averages are drawn outlined and say "avg", so an
 *  average is never mistaken for a class score. A class with no band shows "— · too few voices",
 *  never a fake number. Hover or focus reveals the four inputs and what each earned. */
export function ScorePill({
  score,
  band,
  variant = "md",
  provisional = false,
  action,
  breakdown,
  emptyText,
  label,
  className,
  title,
}: {
  score: number | null | undefined;
  band: Band | null | undefined;
  variant?: ScorePillVariant;
  provisional?: boolean;
  /** Shown as a small suffix in the popover ("→ video"). */
  action?: Action | null;
  breakdown?: ScoreBreakdown | null;
  /** For the empty variant: why there is nothing to show. Default "too few voices". */
  emptyText?: string;
  /** Aggregate variant: what this is an average of ("avg", "course avg"). */
  label?: string;
  className?: string;
  title?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [pos, setPos] = React.useState<{ top: number; left: number; above: boolean } | null>(null);
  const anchor = React.useRef<HTMLElement>(null);
  const id = React.useId();

  const isEmpty = variant === "empty" || band == null || score == null;
  const b: Band | null = isEmpty ? null : (band as Band);
  const meta = b ? BAND_META[b] : null;
  const color = meta ? meta.color : "var(--band-none)";
  const aggregate = variant === "aggregate";

  const place = React.useCallback(() => {
    const el = anchor.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const above = r.bottom + 220 > window.innerHeight && r.top > 240;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - 328));
    setPos({ top: above ? r.top - 8 : r.bottom + 8, left, above });
  }, []);

  const show = () => {
    if (!breakdown) return;
    place();
    setOpen(true);
  };
  const hide = () => setOpen(false);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onScroll = () => setOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [open]);

  const size = {
    sm: { num: "text-[13px] leading-none", lab: "text-[10.5px]", pad: "px-1.5 py-1", gap: "gap-1.5", bar: "h-[3px]" },
    md: { num: "text-[15px] leading-none", lab: "text-[11px]", pad: "px-2 py-1.5", gap: "gap-2", bar: "h-1" },
    lg: { num: "text-[40px] leading-none", lab: "text-[13px]", pad: "px-3 py-2", gap: "gap-3", bar: "h-1" },
    aggregate: { num: "text-[15px] leading-none", lab: "text-[11px]", pad: "px-2 py-1.5", gap: "gap-2", bar: "h-1" },
    empty: { num: "text-[13px] leading-none", lab: "text-[10.5px]", pad: "px-1.5 py-1", gap: "gap-1.5", bar: "h-[3px]" },
  }[variant];

  const inner = (
    <>
      <span className={cn("flex items-baseline", size.gap)}>
        <span
          className={cn("font-num font-semibold tracking-[-0.02em]", size.num, isEmpty && "text-muted-foreground")}
          data-numeric
        >
          {isEmpty ? "—" : fmtScore(score as number)}
        </span>
        <span
          className={cn(
            "font-medium whitespace-nowrap",
            size.lab,
            isEmpty ? "text-muted-foreground" : "text-foreground/80",
          )}
        >
          {isEmpty ? (emptyText ?? (score != null ? "too few voices" : "no score")) : aggregate ? (label ?? "avg") : bandLabel(b, provisional)}
          {aggregate && b && <span className="text-muted-foreground"> · {BAND_META[b].label}</span>}
        </span>
      </span>
      <span
        aria-hidden
        className={cn("mt-1 block w-full rounded-full", size.bar, provisional && "opacity-60")}
        style={{
          background: isEmpty ? "var(--band-none)" : color,
          ...(provisional
            ? {
                backgroundImage:
                  "repeating-linear-gradient(90deg, transparent 0 3px, color-mix(in oklch, var(--card) 70%, transparent) 3px 5px)",
              }
            : {}),
        }}
      />
    </>
  );

  const shell = cn(
    "inline-flex flex-col items-start rounded-md align-middle text-left",
    size.pad,
    aggregate ? "border border-dashed bg-transparent" : "bg-card/60",
    breakdown && "focus-visible:ring-ring/50 cursor-default focus-visible:ring-2 focus-visible:outline-none",
    className,
  );

  const srText = isEmpty
    ? `No score${emptyText ? ` — ${emptyText}` : ""}`
    : `Score ${fmtScore(score as number)}, ${bandLabel(b, provisional)}${aggregate ? " (average)" : ""}`;

  return (
    <>
      {breakdown ? (
        <button
          ref={anchor as React.RefObject<HTMLButtonElement>}
          type="button"
          className={shell}
          title={title}
          aria-label={srText}
          aria-expanded={open}
          aria-controls={open ? id : undefined}
          onMouseEnter={show}
          onMouseLeave={hide}
          onFocus={show}
          onBlur={hide}
          onClick={() => (open ? hide() : show())}
        >
          {inner}
        </button>
      ) : (
        <span ref={anchor as React.RefObject<HTMLSpanElement>} className={shell} title={title} aria-label={srText} role="img">
          {inner}
        </span>
      )}
      {open && breakdown && pos && (
        <div
          id={id}
          role="tooltip"
          className="bg-popover text-popover-foreground shadow-pop fixed z-50 w-80 rounded-xl border p-3 text-[12px]"
          style={{
            left: pos.left,
            top: pos.above ? undefined : pos.top,
            bottom: pos.above ? window.innerHeight - pos.top : undefined,
          }}
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-semibold">
              Class Sentiment Score{" "}
              <span className="font-num" data-numeric>
                {isEmpty ? "—" : fmtScore(score as number)}
              </span>
              {!isEmpty && <span className="text-muted-foreground font-normal"> · {bandLabel(b, provisional)}</span>}
            </span>
            {breakdown.version != null && (
              <span className="text-muted-foreground text-[11px] whitespace-nowrap">version {breakdown.version}</span>
            )}
          </div>
          <table className="mt-2 w-full">
            <tbody>
              {breakdown.rows.map((row) => (
                <tr key={row.key} className={cn(!row.included && "text-muted-foreground")}>
                  <td className="py-0.5 pr-2 align-top whitespace-nowrap">{row.label}</td>
                  <td className="text-muted-foreground py-0.5 pr-2 align-top">{row.detail}</td>
                  <td className="py-0.5 text-right align-top whitespace-nowrap" data-numeric>
                    {row.included ? (
                      <>
                        <span className="text-foreground font-medium">{row.earned}</span>
                        <span className="text-muted-foreground"> / {row.weight}</span>
                      </>
                    ) : (
                      <span className="text-muted-foreground">excluded</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(breakdown.rule || action) && (
            <p className="text-muted-foreground mt-2 border-t pt-2">
              <span className="text-foreground font-medium">Rule says: </span>
              {breakdown.rule ?? (b ? `${BAND_META[b].label} → ${ACTION_LABEL[action ?? "none"]}.` : ACTION_LABEL[action ?? "watch"])}
            </p>
          )}
          {breakdown.reason && <p className="text-muted-foreground mt-1">{breakdown.reason}</p>}
        </div>
      )}
    </>
  );
}

/** A 0–100 bar with the band zones shaded and a marker at the score. The zones come from the
 *  configuration's band edges, so a changed edge shows up here at once. */
export function ScoreBullet({
  score,
  band,
  edges = { excellent: 90, good: 75, average: 60 },
  showLabels = true,
  className,
}: {
  score: number | null | undefined;
  band?: Band | null;
  edges?: { excellent: number; good: number; average: number };
  showLabels?: boolean;
  className?: string;
}) {
  const zones: { band: Band; from: number; to: number }[] = [
    { band: "bad", from: 0, to: edges.average },
    { band: "average", from: edges.average, to: edges.good },
    { band: "good", from: edges.good, to: edges.excellent },
    { band: "excellent", from: edges.excellent, to: 100 },
  ];
  const pct = score == null ? null : Math.max(0, Math.min(100, score));
  return (
    <div className={cn("w-full", className)}>
      <div className="relative h-2.5 w-full overflow-visible rounded-full">
        <div className="absolute inset-0 flex overflow-hidden rounded-full">
          {zones.map((z) => (
            <span
              key={z.band}
              className="h-full"
              style={{ width: `${z.to - z.from}%`, background: BAND_META[z.band].soft }}
              aria-hidden
            />
          ))}
        </div>
        {zones.slice(1).map((z) => (
          <span
            key={z.band}
            aria-hidden
            className="bg-card absolute top-0 h-full w-px"
            style={{ left: `${z.from}%` }}
          />
        ))}
        {pct != null && (
          <span
            aria-hidden
            className="ring-card absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2"
            style={{ left: `${pct}%`, background: band ? BAND_META[band].color : "var(--band-none)" }}
          />
        )}
      </div>
      {showLabels && (
        <div className="text-muted-foreground relative mt-1 h-4 text-[10.5px]" aria-hidden>
          <span className="absolute left-0">0</span>
          {zones.slice(1).map((z) => (
            <span key={z.band} className="absolute -translate-x-1/2" style={{ left: `${z.from}%` }} data-numeric>
              {z.from}
            </span>
          ))}
          <span className="absolute right-0">100</span>
        </div>
      )}
      <span className="sr-only">
        {score == null ? "No score" : `Score ${score} of 100${band ? `, ${BAND_META[band].label}` : ""}`}
      </span>
    </div>
  );
}

/** A 100% strip of the four bands with counts — the band mix of a course, a week, a cohort. */
export function BandStrip({
  counts,
  className,
  showCounts = true,
  height = "h-2",
}: {
  counts: Partial<Record<Band, number>>;
  className?: string;
  showCounts?: boolean;
  height?: string;
}) {
  const total = BAND_ORDER.reduce((a, b) => a + (counts[b] ?? 0), 0);
  return (
    <div className={cn("w-full", className)}>
      <div className={cn("flex w-full overflow-hidden rounded-full", height, total === 0 && "bg-muted")} role="img" aria-label={
        total === 0
          ? "No scored classes"
          : BAND_ORDER.map((b) => `${BAND_META[b].label} ${counts[b] ?? 0}`).join(", ")
      }>
        {total > 0 &&
          BAND_ORDER.map((b) => {
            const n = counts[b] ?? 0;
            if (n === 0) return null;
            return (
              <span
                key={b}
                className="h-full"
                style={{ width: `${(n / total) * 100}%`, background: BAND_META[b].color }}
                title={`${BAND_META[b].label} · ${n}`}
              />
            );
          })}
      </div>
      {showCounts && (
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]" aria-hidden>
          {BAND_ORDER.map((b) => (
            <span key={b} className="text-muted-foreground inline-flex items-center gap-1">
              <span className="inline-block size-2 rounded-sm" style={{ background: BAND_META[b].color }} />
              {BAND_META[b].label}
              <span className="text-foreground font-medium" data-numeric>
                {counts[b] ?? 0}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** A quiet band chip: label + dot. For places where a full pill is too much (legends, filters). */
export function BandChip({ band, className }: { band: Band | null; className?: string }) {
  const meta = band ? BAND_META[band] : null;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium", className)}
      style={meta ? { background: meta.soft, color: meta.text } : undefined}
    >
      <span aria-hidden className="inline-block size-1.5 rounded-full" style={{ background: meta ? meta.color : "var(--band-none)" }} />
      {meta ? meta.label : "No band"}
    </span>
  );
}
