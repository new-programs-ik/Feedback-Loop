import * as React from "react";
import Link from "next/link";
import { SegmentedTabs } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { AvgScorePill, BandStripOf } from "@/components/analytics/score";
import { Delta, Kpi } from "@/components/analytics/ui";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { fmtPct, plural, prettyDate, type Funnel, type ReportPeriod, type ScoreSummary } from "@/lib/analytics";

/** Print rules for the report pages: A4, page breaks between sections, chrome hidden. */
export function PrintStyles() {
  return (
    <style>{`@media print {
  @page { size: A4; margin: 14mm 12mm; }
  .report-section { break-inside: avoid; page-break-inside: avoid; }
  .report-break { break-before: page; page-break-before: always; }
  .report-page { max-width: none !important; }
  [data-print-hide], nav, aside, header[data-topbar] { display: none !important; }
}`}</style>
  );
}

const ARROW = "text-muted-foreground hover:bg-accent hover:text-foreground inline-flex size-7 items-center justify-center rounded-md border transition-colors";

/** Weekly · Monthly · Custom, URL-driven; ‹ › step through weeks or months; the custom dates
 *  apply with a button. When the synced data ends before today the window ends there and says so. */
export function PeriodTabs({
  basePath,
  period,
  from,
  to,
  prev,
  next,
  stale,
  extra,
}: {
  basePath: string;
  period: ReportPeriod;
  from: string;
  to: string;
  /** A date inside the previous / next period (from `reportPeriod`); null at the edges. */
  prev?: string | null;
  next?: string | null;
  /** The window ends before today because the sheet has nothing newer. */
  stale?: boolean;
  extra?: Record<string, string | undefined>;
}) {
  const q = (p: ReportPeriod, at?: string | null) => {
    const sp = new URLSearchParams();
    sp.set("period", p);
    if (p === "custom") {
      sp.set("from", from);
      sp.set("to", to);
    } else if (at) sp.set("at", at);
    for (const [k, v] of Object.entries(extra ?? {})) if (v) sp.set(k, v);
    return `${basePath}?${sp}`;
  };
  const unit = period === "month" ? "month" : "week";
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3" data-print-hide>
      <SegmentedTabs
        ariaLabel="Report period"
        items={[
          { label: "Weekly", href: q("week"), active: period === "week" },
          { label: "Monthly", href: q("month"), active: period === "month" },
          { label: "Custom", href: q("custom"), active: period === "custom" },
        ]}
      />
      {period !== "custom" && (
        <div className="flex items-center gap-1.5">
          {prev ? (
            <Link href={q(period, prev)} className={ARROW} aria-label={`Previous ${unit}`}>
              <ChevronLeft className="size-4" aria-hidden />
            </Link>
          ) : (
            <span className={cn(ARROW, "opacity-40")} aria-disabled>
              <ChevronLeft className="size-4" aria-hidden />
            </span>
          )}
          <span className="min-w-[7.5rem] text-center text-xs font-medium" data-numeric>
            {prettyDate(from)} – {prettyDate(to)}
          </span>
          {next ? (
            <Link href={q(period, next)} className={ARROW} aria-label={`Next ${unit}`}>
              <ChevronRight className="size-4" aria-hidden />
            </Link>
          ) : (
            <span className={cn(ARROW, "opacity-40")} aria-disabled title="This is the latest period with rated classes">
              <ChevronRight className="size-4" aria-hidden />
            </span>
          )}
        </div>
      )}
      {stale && period !== "custom" && (
        <span className="text-muted-foreground text-xs">Ends on the last rated class in the sheet ({prettyDate(to)}) — nothing newer has synced yet.</span>
      )}
      {period === "custom" && (
        <form method="get" action={basePath} className="flex flex-wrap items-center gap-2">
          <input type="hidden" name="period" value="custom" />
          {Object.entries(extra ?? {}).map(([k, v]) => (v ? <input key={k} type="hidden" name={k} value={v} /> : null))}
          <Input type="date" name="from" defaultValue={from} aria-label="From" className="w-[9.5rem]" />
          <span className="text-muted-foreground text-xs">to</span>
          <Input type="date" name="to" defaultValue={to} aria-label="To" className="w-[9.5rem]" />
          <Button type="submit" size="sm" variant="outline">
            Apply
          </Button>
        </form>
      )}
    </div>
  );
}

/** The report's headline tiles: classes · avg score · band mix · approval · reach · flagged. */
export function HeadlineTiles({ cur, prev, queue }: { cur: ScoreSummary; prev: ScoreSummary; queue: { video: number; transcript: number } }) {
  return (
    <div className="report-section grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      <Kpi label="Classes rated" value={cur.n} sub={<Delta value={cur.n - prev.n} suffix="vs previous period" />} />
      <Kpi label="Avg score" value={<AvgScorePill score={cur.avgScore} />} sub={<Delta value={cur.avgScore == null || prev.avgScore == null ? null : cur.avgScore - prev.avgScore} suffix="pts" />} />
      <Kpi label="Band mix" value={<BandStripOf counts={cur.counts} className="w-full" height="h-2" />} sub={`${cur.counts.excellent} · ${cur.counts.good} · ${cur.counts.average} · ${cur.counts.bad}`} />
      <Kpi label="Approval" value={<span className={cur.approval != null && cur.approval < 80 ? "text-destructive" : ""}>{fmtPct(cur.approval)}</span>} sub={<Delta value={cur.approval == null || prev.approval == null ? null : cur.approval - prev.approval} unit=" pts" />} />
      <Kpi label="Reach" value={fmtPct(cur.reach)} sub={<Delta value={cur.reach == null || prev.reach == null ? null : cur.reach - prev.reach} unit=" pts" />} />
      <Kpi label="Flagged" value={queue.video + queue.transcript} sub={`${queue.video} video · ${queue.transcript} transcript`} />
    </div>
  );
}

const fmtDays = (d: number | null) => (d == null ? "—" : d < 1 ? "<1 d" : `${d.toFixed(d >= 10 ? 0 : 1)} d`);

/** flagged → confirmed → analysed → approved → sent, with the median days per step. */
export function LoopFunnel({ f, feedbackHref }: { f: Funnel; feedbackHref?: string }) {
  const steps = [
    { label: "Flagged", n: f.flagged, days: null as string | null },
    { label: "Confirmed", n: f.confirmed, days: null },
    { label: "Analysed", n: f.analysed, days: fmtDays(f.daysToAnalysis) },
    { label: "Approved", n: f.approved, days: fmtDays(f.daysToApproval) },
    { label: "Sent", n: f.sent, days: fmtDays(f.daysToSend) },
  ];
  const max = Math.max(f.flagged, 1);
  return (
    <div className="report-section">
      <ol className="grid grid-cols-5 gap-2">
        {steps.map((s, i) => (
          <li key={s.label} className="min-w-0">
            <div className="bg-muted relative h-8 overflow-hidden rounded-md">
              <div className="absolute inset-y-0 left-0 rounded-md" style={{ width: `${Math.max(2, (s.n / max) * 100)}%`, background: `color-mix(in oklch, var(--chart-1) ${100 - i * 15}%, var(--muted))` }} />
              <span className="absolute inset-0 flex items-center px-2 text-[13px] font-semibold" data-numeric>
                {s.n}
              </span>
            </div>
            <div className="mt-1 truncate text-[11px] font-medium">{s.label}</div>
            <div className="text-muted-foreground truncate text-[10.5px]" data-numeric>
              {s.days ? `median ${s.days}` : i === 0 ? "by the band" : " "}
            </div>
          </li>
        ))}
      </ol>
      <p className="text-muted-foreground mt-2 text-[11px]">
        {f.flagged === 0 ? "Nothing was flagged in this period." : `${f.sent} of ${f.flagged} flagged ${plural(f.flagged, "class", "classes")} reached the instructor`}
        {f.cost > 0 ? ` · analyses cost $${f.cost.toFixed(2)}` : ""}
        {feedbackHref && (
          <>
            {" · "}
            <Link href={feedbackHref} className="text-primary hover:underline" data-print-hide>
              open feedback
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
