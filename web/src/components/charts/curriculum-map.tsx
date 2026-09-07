"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { BAND_META, BAND_ORDER, type Band } from "@/lib/sentiment";
import { RATING_LINE, kindMix, ratingBand, ratioBand, reachBand } from "@/lib/curriculum";
import { Segmented } from "@/components/analytics/segmented";
import { ChartTooltip, type TooltipRow } from "./chart-tooltip";

/** The curriculum map: one row per cohort, one column per module in curriculum order. Every
 *  cell carries the raw numbers a PM asked for — the rating, then who rated over who came —
 *  and a tint that encodes one metric at a time (the score band by default; the rating alone,
 *  the room against the cohort's first class, or the share that rated). A click, or Enter,
 *  opens the class drawer for that cell (the live session when there were two); arrow keys walk
 *  the grid; the first column and the header stay put while the grid scrolls inside the card.
 *  The footer row is the module's average line: rating, room, and the fall against the module
 *  before it (red from −10%). Prints as it looks. */

export type MapMetric = "score" | "rating" | "attendance" | "reach";

export type MapCell = {
  /** The class a click opens — the live session when the cohort also had a review. */
  openId: string;
  sessions: number;
  rating: number | null;
  rated: number | null;
  attended: number | null;
  reach: number | null;
  score: number | null;
  band: Band | null;
  kinds: string[];
  instructors: string[];
  initials: string;
  dateLabel: string;
};

export type MapCohort = {
  key: string;
  name: string;
  href?: string;
  startLabel: string;
  trackLabel?: string;
  size: number | null;
  retention: number | null;
  firstAttended: number | null;
  active: boolean;
  /** Column index of the cohort's last module — empties right of it are "not yet". */
  lastOrder: number | null;
  cells: Record<string, MapCell>;
};

export type MapModule = {
  key: string;
  name: string;
  short: string;
  href?: string;
  order: number | null;
  n: number;
  avgRating: number | null;
  avgAttended: number | null;
  dropAttended: number | null;
  dropPairs: number;
};

const METRICS: { value: MapMetric; label: string; title: string }[] = [
  { value: "rating", label: "Rating", title: "Tint by the rating alone" },
  { value: "attendance", label: "Attendance", title: "Tint by the room against the cohort's first class" },
  { value: "reach", label: "Reach", title: "Tint by the share of the room that rated" },
  { value: "score", label: "Score", title: "Tint by the Class Sentiment Score band" },
];

const SCALES: Record<MapMetric, { label: string; steps: [string, string, string, string] }> = {
  score: { label: "Tint = the score band", steps: ["Excellent", "Good", "Average", "Bad"] },
  rating: { label: "Tint = the rating alone", steps: ["4.82+", "4.55+", "4.35+", "under 4.35"] },
  attendance: { label: "Tint = the room vs the cohort's first class", steps: ["90%+", "75%+", "60%+", "under 60%"] },
  reach: { label: "Tint = the share of the room that rated", steps: ["60%+", "40%+", "25%+", "under 25%"] },
};

function tintOf(cell: MapCell, cohort: MapCohort, metric: MapMetric): Band | null {
  switch (metric) {
    case "rating":
      return ratingBand(cell.rating);
    case "attendance":
      return ratioBand(cell.attended != null && cohort.firstAttended ? cell.attended / cohort.firstAttended : null);
    case "reach":
      return reachBand(cell.reach);
    case "score":
      return cell.band;
  }
}

const fmt2 = (v: number | null) => (v == null ? "—" : v.toFixed(2));

function RetentionChip({ value }: { value: number | null }) {
  if (value == null) return null;
  const band = ratioBand(value);
  return (
    <span
      className="inline-flex items-center rounded px-1 py-px text-[10px] font-semibold"
      style={band ? { background: BAND_META[band].soft, color: BAND_META[band].text } : undefined}
      title="Retention: the last module's room over the first module's room"
      data-numeric
    >
      {Math.round(value * 100)}% kept
    </span>
  );
}

export function CurriculumMap({
  cohorts,
  modules,
  hrefPrefix,
  initialMetric = "score",
  maxHeight = "72vh",
  className,
}: {
  cohorts: MapCohort[];
  modules: MapModule[];
  /** `…?class=` — the cell's class id is appended and pushed (scroll kept), like a row click. */
  hrefPrefix: string;
  initialMetric?: MapMetric;
  maxHeight?: string;
  className?: string;
}) {
  const router = useRouter();
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const [metric, setMetric] = React.useState<MapMetric>(initialMetric);
  const [showInstructors, setShowInstructors] = React.useState(false);
  const [focus, setFocus] = React.useState<{ r: number; c: number; x: number; y: number } | null>(null);

  const at = (r: number, c: number): MapCell | undefined => cohorts[r]?.cells[modules[c]?.key];
  const open = React.useCallback((cell: MapCell) => router.push(`${hrefPrefix}${encodeURIComponent(cell.openId)}`, { scroll: false }), [router, hrefPrefix]);

  const place = (el: HTMLElement, r: number, c: number) => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const a = el.getBoundingClientRect();
    const b = wrap.getBoundingClientRect();
    setFocus({ r, c, x: a.left - b.left + a.width / 2, y: a.top - b.top + 6 });
  };
  const clear = () => setFocus(null);

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!focus) return;
    let { r, c } = focus;
    if (e.key === "Enter") {
      const cell = at(r, c);
      if (cell) {
        e.preventDefault();
        open(cell);
      }
      return;
    }
    if (e.key === "ArrowRight") c = Math.min(modules.length - 1, c + 1);
    else if (e.key === "ArrowLeft") c = Math.max(0, c - 1);
    else if (e.key === "ArrowDown") r = Math.min(cohorts.length - 1, r + 1);
    else if (e.key === "ArrowUp") r = Math.max(0, r - 1);
    else if (e.key === "Home") c = 0;
    else if (e.key === "End") c = modules.length - 1;
    else if (e.key === "Escape") {
      (e.target as HTMLElement).blur();
      clear();
      return;
    } else return;
    e.preventDefault();
    wrapRef.current?.querySelector<HTMLElement>(`[data-cell="${r}-${c}"]`)?.focus();
  };

  // ── the tooltip ──
  const focusedCohort = focus ? cohorts[focus.r] : undefined;
  const focusedModule = focus ? modules[focus.c] : undefined;
  const focused = focus ? at(focus.r, focus.c) : undefined;
  const tint = focused && focusedCohort ? tintOf(focused, focusedCohort, metric) : null;
  const tipRows: TooltipRow[] = focused
    ? [
        { value: fmt2(focused.rating), label: focused.rating != null && focused.rating < RATING_LINE ? `rating · under the ${RATING_LINE} line` : "rating", color: tint ? BAND_META[tint].color : undefined, swatch: "square" },
        { value: `${focused.rated ?? "—"} of ${focused.attended ?? "—"}`, label: `rated${focused.reach != null ? ` · ${Math.round(focused.reach)}% of the room` : ""}` },
        { value: focused.score == null ? "—" : String(Math.round(focused.score)), label: focused.band ? `score · ${BAND_META[focused.band].label}` : "score" },
        { value: focused.dateLabel, label: `${focused.instructors.join(", ")} · ${kindMix(focused.kinds)}` },
      ]
    : focus && focusedCohort
      ? [{ value: focusedCohort.active && focusedCohort.lastOrder != null && focus.c > focusedCohort.lastOrder ? "Not reached yet" : "Not taught to this cohort" }]
      : [];
  const tipTitle = focus ? `${focusedCohort?.name ?? ""} × ${focusedModule?.name ?? ""}` : undefined;
  const scale = SCALES[metric];

  if (cohorts.length === 0 || modules.length === 0) {
    return (
      <div className={cn("text-muted-foreground px-4 py-6 text-[13px]", className)}>
        {cohorts.length === 0 ? "No cohort has a class in this period." : "No module has two rated classes yet — most rows still carry the generic session label."}
      </div>
    );
  }

  return (
    <div ref={wrapRef} className={cn("relative", className)} onKeyDown={onKeyDown}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 py-2" data-print-hide>
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
          <span className="font-medium">{scale.label}</span>
          {BAND_ORDER.map((b, i) => (
            <span key={b} className="inline-flex items-center gap-1">
              <span aria-hidden className="inline-block size-2.5 rounded-[3px]" style={{ background: BAND_META[b].soft, boxShadow: `inset 0 0 0 1px ${BAND_META[b].color}` }} />
              {scale.steps[i]}
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented size="sm" ariaLabel="Tint cells by" value={metric} onChange={setMetric} options={METRICS} />
          <button
            type="button"
            aria-pressed={showInstructors}
            onClick={() => setShowInstructors((v) => !v)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-[11px] font-medium transition-colors duration-150",
              "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
              showInstructors ? "bg-accent text-accent-foreground border-transparent" : "text-muted-foreground hover:text-foreground hover:bg-muted/60",
            )}
            title="Print each instructor's initials in the corner of their cells"
          >
            <span aria-hidden className={cn("inline-block size-1.5 rounded-full", showInstructors ? "bg-primary" : "bg-muted-foreground/40")} />
            Show instructors
          </button>
        </div>
      </div>

      <div className="overflow-auto print:max-h-none print:overflow-visible" style={{ maxHeight }}>
        <table className="print-exact w-max min-w-full border-separate border-spacing-0 text-[12px]" role="grid" aria-label="Cohorts by module" aria-rowcount={cohorts.length} aria-colcount={modules.length}>
          <thead>
            <tr>
              <th className="bg-card sticky top-0 left-0 z-[3] border-r border-b px-3 py-2 text-left align-bottom">
                <span className="block text-[11px] font-medium">Cohort</span>
                <span className="text-muted-foreground block text-[10px] font-normal" data-numeric>
                  {cohorts.length} {cohorts.length === 1 ? "cohort" : "cohorts"} × {modules.length} {modules.length === 1 ? "module" : "modules"}
                </span>
              </th>
              {modules.map((m) => (
                <th key={m.key} className="bg-card sticky top-0 z-[2] border-b px-1 py-1.5 text-center align-bottom" style={{ minWidth: 78 }}>
                  <span className="text-foreground block max-w-[92px] truncate text-[11px] font-medium" title={m.name}>
                    {m.href ? (
                      <Link href={m.href} className="hover:text-primary">
                        {m.short}
                      </Link>
                    ) : (
                      m.short
                    )}
                  </span>
                  <span className="text-muted-foreground block text-[10px] font-normal" data-numeric>
                    {m.order != null ? `W${Math.round(m.order)}` : "—"}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cohorts.map((cohort, ri) => (
              <tr key={cohort.key}>
                <th scope="row" className="bg-card sticky left-0 z-[1] border-r border-b px-3 py-1 text-left align-middle font-normal">
                  <span className="block max-w-56 truncate text-[12px] font-medium" title={cohort.name}>
                    {cohort.href ? (
                      <Link href={cohort.href} className="hover:text-primary">
                        {cohort.name}
                      </Link>
                    ) : (
                      cohort.name
                    )}
                  </span>
                  <span className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-[10px] whitespace-nowrap">
                    <span data-numeric>
                      {cohort.startLabel}
                      {cohort.size != null ? ` · ${cohort.size} learners` : ""}
                      {cohort.active ? " · running" : ""}
                    </span>
                    <RetentionChip value={cohort.retention} />
                  </span>
                </th>
                {modules.map((m, ci) => {
                  const cell = cohort.cells[m.key];
                  if (!cell) {
                    const upcoming = cohort.active && cohort.lastOrder != null && ci > cohort.lastOrder;
                    return (
                      <td key={m.key} className="border-b p-0.5">
                        <div
                          role="gridcell"
                          tabIndex={0}
                          data-cell={`${ri}-${ci}`}
                          aria-label={`${cohort.name} × ${m.name}: ${upcoming ? "not reached yet" : "not taught"}`}
                          className="text-muted-foreground/40 focus-visible:ring-ring/60 flex h-11 min-w-[78px] items-center justify-center rounded-md outline-none focus-visible:ring-2"
                          onPointerEnter={(e) => place(e.currentTarget, ri, ci)}
                          onPointerLeave={clear}
                          onFocus={(e) => place(e.currentTarget, ri, ci)}
                          onBlur={clear}
                        >
                          <span aria-hidden>{upcoming ? "·" : "—"}</span>
                        </div>
                      </td>
                    );
                  }
                  const band = tintOf(cell, cohort, metric);
                  const low = cell.rating != null && cell.rating < RATING_LINE;
                  const label = `${cohort.name} × ${m.name}: rated ${fmt2(cell.rating)}, ${cell.rated ?? "—"} of ${cell.attended ?? "—"} rated${cell.score != null ? `, score ${Math.round(cell.score)}` : ""}. ${cell.dateLabel}, ${cell.instructors.join(", ")}. Press Enter to open the class.`;
                  return (
                    <td key={m.key} className="border-b p-0.5">
                      <div
                        role="gridcell"
                        tabIndex={0}
                        data-cell={`${ri}-${ci}`}
                        aria-label={label}
                        className={cn(
                          "focus-visible:ring-ring/60 relative flex h-11 min-w-[78px] cursor-pointer flex-col items-center justify-center rounded-md leading-none outline-none transition-[box-shadow] duration-150 focus-visible:ring-2",
                          "hover:shadow-[inset_0_0_0_1.5px_var(--ring)]",
                        )}
                        style={band ? { background: BAND_META[band].soft } : { background: "color-mix(in oklch, var(--muted) 60%, transparent)" }}
                        onClick={() => open(cell)}
                        onPointerEnter={(e) => place(e.currentTarget, ri, ci)}
                        onPointerLeave={clear}
                        onFocus={(e) => place(e.currentTarget, ri, ci)}
                        onBlur={clear}
                      >
                        {showInstructors && (
                          <span aria-hidden className="text-foreground/70 absolute top-0.5 left-1 text-[9px] font-semibold tracking-wide">
                            {cell.initials}
                          </span>
                        )}
                        {cell.sessions > 1 && (
                          <span aria-hidden className="text-foreground/60 absolute top-0.5 right-1 text-[9px] font-medium" title="live class + test review">
                            +R
                          </span>
                        )}
                        <span className={cn("font-num text-[13px] font-semibold", low ? "text-destructive" : "text-foreground")} data-numeric>
                          {fmt2(cell.rating)}
                        </span>
                        <span className="text-muted-foreground mt-1 text-[11px]" data-numeric>
                          {cell.rated ?? "—"}
                          <span className="opacity-60">/</span>
                          {cell.attended ?? "—"}
                        </span>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="bg-card sticky bottom-0 left-0 z-[3] border-t border-r px-3 py-1.5 text-left align-middle">
                <span className="block text-[11px] font-medium">Module average</span>
                <span className="text-muted-foreground block text-[10px] font-normal">rating · room · vs the module before</span>
              </th>
              {modules.map((m) => {
                const drop = m.dropPairs >= 2 ? m.dropAttended : null;
                const red = drop != null && drop <= -10;
                return (
                  <td key={m.key} className="bg-card sticky bottom-0 z-[2] border-t px-1 py-1.5 text-center align-middle">
                    <span className={cn("font-num block text-[12px] font-semibold", m.avgRating != null && m.avgRating < RATING_LINE ? "text-destructive" : "text-foreground")} data-numeric>
                      {fmt2(m.avgRating)}
                    </span>
                    <span className="text-muted-foreground block text-[10px]" data-numeric>
                      {m.avgAttended != null ? `${Math.round(m.avgAttended)} in room` : "—"}
                    </span>
                    <span className={cn("block text-[10px] font-semibold", red ? "text-destructive" : "text-muted-foreground")} data-numeric title={drop != null ? `Attendance against the module before, averaged over ${m.dropPairs} cohorts` : "Needs two cohorts with the module before it"}>
                      {drop == null ? " " : `${drop < 0 ? "▼" : "▲"} ${Math.abs(Math.round(drop))}%`}
                    </span>
                  </td>
                );
              })}
            </tr>
          </tfoot>
        </table>
      </div>
      <ChartTooltip open={focus != null} x={focus?.x ?? 0} y={focus?.y ?? 0} boundsRef={wrapRef} title={tipTitle} rows={tipRows} live>
        {focused && <div className="text-muted-foreground mt-1 text-[10.5px]">Click or press Enter to open the class</div>}
      </ChartTooltip>
    </div>
  );
}

/** The map's loading twin: the same card geometry, so nothing reflows when the data lands. */
export function CurriculumMapSkeleton({ rows = 6, cols = 8 }: { rows?: number; cols?: number }) {
  return (
    <div className="bg-card shadow-soft overflow-hidden rounded-xl border" aria-hidden>
      <div className="px-4 pt-3.5 pb-2.5">
        <div className="shimmer h-3 w-44 rounded" />
        <div className="shimmer mt-2 h-2.5 w-72 max-w-[70vw] rounded" />
      </div>
      <div className="flex items-center justify-between border-y px-4 py-2">
        <div className="shimmer h-2.5 w-56 rounded" />
        <div className="shimmer h-6 w-56 rounded-lg" />
      </div>
      <div className="overflow-hidden px-3 py-2">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex items-center gap-1 py-0.5">
            <div className="shimmer h-9 w-48 shrink-0 rounded" />
            {Array.from({ length: cols }).map((_, c) => (
              <div key={c} className="shimmer h-11 w-[78px] shrink-0 rounded-md" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
