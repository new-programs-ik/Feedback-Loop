"use client";

import * as React from "react";
import { ArrowRight, Database, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { PreviewRow } from "@/lib/admin";
import { whatIfSummary, type WhatIfSummary } from "@/app/(app)/admin/actions";
import type { ScoringConfig } from "../scoring-config";
import { ScorePill } from "@/components/score/score-pill";
import { BandMix } from "./band-mix";
import { computePreview, fmt1, fmtMoney, fmtPct, type PreviewStats } from "./preview-math";

const pretty = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

/** The right-hand half of the scoring page: everything the candidate config would do to the
 *  chosen range, computed in the browser with the score mirror. Four numbers first, the band mix
 *  before/after, then every class that moves. "Compare with the database" asks Postgres for the
 *  same summary so the two implementations can be checked against each other. */
export function ScoringPreview({
  config,
  baseline,
  baselineLabel,
  rows,
  globalPrior,
  from,
  to,
  loading,
  error,
  onStats,
}: {
  config: ScoringConfig;
  baseline: ScoringConfig;
  baselineLabel: string;
  rows: PreviewRow[];
  globalPrior: { rating: number | null; approval: number | null };
  from: string;
  to: string;
  loading: boolean;
  error: string | null;
  onStats?: (s: PreviewStats) => void;
}) {
  const stats = React.useMemo(() => computePreview(rows, config, baseline, globalPrior, from, to), [rows, config, baseline, globalPrior, from, to]);
  React.useEffect(() => {
    onStats?.(stats);
  }, [stats, onStats]);

  const [showAll, setShowAll] = React.useState(false);
  const [db, setDb] = React.useState<{ summary: WhatIfSummary; for: string } | null>(null);
  const [pending, startTransition] = React.useTransition();
  const configKey = React.useMemo(() => JSON.stringify(config) + from + to, [config, from, to]);
  const dbFresh = db?.for === configKey;

  const compare = () =>
    startTransition(async () => {
      const r = await whatIfSummary(config, from, to);
      if (!r.ok) {
        toast.error("The database could not run this what-if", { description: r.error });
        return;
      }
      setDb({ summary: r.data, for: configKey });
    });

  const shown = showAll ? stats.changed : stats.changed.slice(0, 40);

  return (
    <div className="space-y-4" data-slot="scoring-preview" aria-busy={loading}>
      {error && (
        <p className="border-destructive/40 bg-destructive/5 text-destructive rounded-md border px-3 py-2 text-[12.5px]">{error}</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-live="polite">
        <Tile
          label="Classes that change band"
          value={loading ? "…" : String(stats.bandMoves)}
          note={loading ? "" : `${stats.actionMoves} change what happens · of ${stats.n}`}
        />
        <Tile
          label="Analyses per week"
          value={loading ? "…" : fmt1(stats.analysesPerWeek)}
          note={loading ? "" : `${fmt1(stats.videosPerWeek)} video · ${fmt1(stats.transcriptsPerWeek)} transcript ≈ ${fmtMoney(stats.costPerWeek)}/wk`}
          delta={loading ? undefined : deltaText(stats.analysesPerWeek, stats.videosPerWeekBefore + stats.transcriptsPerWeekBefore, "/wk")}
        />
        <Tile
          label="Dropped from today's queue"
          value={loading ? "…" : String(stats.dropped)}
          note={loading ? "" : `${stats.added} newly analysed · vs what the queue does today`}
          tone={stats.dropped > 0 ? "warn" : "default"}
        />
        <Tile
          label="Flips if one learner answers differently"
          value={loading ? "…" : fmtPct(stats.flipShare)}
          note={loading ? "" : `${stats.flips} of ${stats.n} classes · ${fmtPct(stats.flipShare10)} with 10+ votes`}
          tone={stats.flipShare != null && stats.flipShare > 0.1 ? "warn" : "default"}
        />
      </div>

      <div className="bg-card shadow-soft rounded-xl border p-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">Band mix</h3>
          <span className="text-muted-foreground text-[11px]">
            {pretty(from)} – {pretty(to)} · {stats.n} classes · baseline: {baselineLabel}
          </span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <div className="text-muted-foreground mb-1.5 text-[11px] font-medium">Before</div>
            <BandMix counts={stats.before} />
          </div>
          <div>
            <div className="text-muted-foreground mb-1.5 text-[11px] font-medium">With this draft</div>
            <BandMix counts={stats.after} />
          </div>
        </div>
        <p className="text-muted-foreground mt-3 text-[11px] leading-snug">
          Computed in the browser with the same formula as the database. The guard&apos;s “typical class” is this
          range&apos;s course average; the database may use a wider window — compare below when in doubt.
        </p>
      </div>

      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3.5 pb-2.5">
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">
            Classes that change <span className="text-muted-foreground font-normal">· {stats.changed.length}</span>
          </h3>
          {stats.changed.length > 40 && (
            <button type="button" onClick={() => setShowAll((v) => !v)} className="text-primary text-[12px] font-medium hover:underline">
              {showAll ? "Show first 40" : `Show all ${stats.changed.length}`}
            </button>
          )}
        </div>
        {stats.changed.length === 0 ? (
          <p className="text-muted-foreground border-t px-4 py-6 text-center text-[13px]">
            {loading ? "Scoring the range…" : "No class changes band or action against the baseline."}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Class</TableHead>
                <TableHead>Before</TableHead>
                <TableHead />
                <TableHead>After</TableHead>
                <TableHead>Why</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((c) => (
                <TableRow key={c.row.id}>
                  <TableCell className="max-w-64">
                    <div className="truncate font-medium">{c.row.topic || c.row.session_kind}</div>
                    <div className="text-muted-foreground truncate text-[11px]">
                      {c.row.course_name} · {c.row.instructor || "—"} · {pretty(c.row.class_date)} · rated {c.row.rating.toFixed(2)}
                      {c.row.yes_votes != null && c.row.no_votes != null ? ` · ${c.row.yes_votes} of ${c.row.yes_votes + c.row.no_votes} yes` : ""}
                    </div>
                  </TableCell>
                  <TableCell>
                    <ScorePill variant="sm" score={c.before.score} band={c.before.band} provisional={c.before.provisional} />
                    <div className="text-muted-foreground mt-0.5 text-[10.5px] capitalize">{c.before.action}</div>
                  </TableCell>
                  <TableCell className="px-1">
                    <ArrowRight
                      className={cn("size-3.5", c.direction === "up" ? "text-success" : c.direction === "down" ? "text-destructive" : "text-muted-foreground")}
                      aria-label={c.direction === "up" ? "moves up" : c.direction === "down" ? "moves down" : "action changes"}
                    />
                  </TableCell>
                  <TableCell>
                    <ScorePill variant="sm" score={c.after.score} band={c.after.band} provisional={c.after.provisional} />
                    <div className="text-muted-foreground mt-0.5 text-[10.5px] capitalize">{c.after.action}</div>
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-72 text-[12px] leading-snug">{c.reason}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="bg-card shadow-soft rounded-xl border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-[13px] font-semibold tracking-[-0.01em]">Compare with the database</h3>
            <p className="text-muted-foreground text-[11.5px]">
              Runs <code className="font-mono text-[11px]">scoring_whatif_summary</code> in Postgres over the same range and shows both answers.
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={compare} disabled={pending || loading || rows.length === 0}>
            {pending ? <LoaderCircle className="animate-spin" aria-hidden /> : <Database aria-hidden />}
            {pending ? "Asking…" : dbFresh ? "Run again" : "Compare with the database"}
          </Button>
        </div>
        {db && (
          <div className={cn("mt-3 overflow-x-auto", !dbFresh && "opacity-60")}>
            {!dbFresh && <p className="text-warning mb-2 text-[11px]">The draft changed since this comparison — run it again.</p>}
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-muted-foreground border-b text-left">
                  <th className="py-1.5 pr-3 font-medium">Measure</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Browser</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Database</th>
                </tr>
              </thead>
              <tbody>
                {(["excellent", "good", "average", "bad", "no_data"] as const).map((b) => (
                  <Cmp key={b} label={`Band · ${b === "no_data" ? "too few voices" : b}`} a={stats.after[b]} b={db.summary.band_counts?.[b] ?? db.summary.band_counts?.[b === "no_data" ? "null" : b] ?? 0} />
                ))}
                <Cmp label="Videos / week" a={stats.videosPerWeek} b={db.summary.videos_per_week} decimals={1} />
                <Cmp label="Transcripts / week" a={stats.transcriptsPerWeek} b={db.summary.transcripts_per_week} decimals={1} />
                <Cmp label="Classes that change" a={stats.changed.length} b={db.summary.changed_count} />
                <Cmp label="Dropped from today's queue" a={stats.dropped} b={db.summary.dropped_count} />
                <Cmp label="Flips if one learner answers differently" a={stats.flipShare == null ? null : stats.flipShare * 100} b={db.summary.flip_share == null ? null : db.summary.flip_share <= 1 ? db.summary.flip_share * 100 : db.summary.flip_share} decimals={1} suffix="%" />
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function deltaText(now: number, before: number, suffix: string): string {
  const d = now - before;
  if (Math.abs(d) < 0.05) return `same as today${suffix ? "" : ""}`;
  return `${d > 0 ? "+" : "−"}${fmt1(Math.abs(d))}${suffix} vs baseline`;
}

function Tile({ label, value, note, delta, tone = "default" }: { label: string; value: string; note?: string; delta?: string; tone?: "default" | "warn" }) {
  return (
    <div className="bg-card shadow-soft rounded-xl border p-3.5">
      <p className="text-muted-foreground text-[11px] font-medium">{label}</p>
      <p data-numeric className={cn("mt-1 text-[24px] leading-none font-semibold tracking-[-0.02em]", tone === "warn" && "text-warning")}>
        {value}
      </p>
      <p className="text-muted-foreground mt-1.5 line-clamp-2 min-h-4 text-[11px] leading-4">
        {delta ? `${delta} · ` : ""}
        {note}
      </p>
    </div>
  );
}

function Cmp({ label, a, b, decimals = 0, suffix = "" }: { label: string; a: number | null; b: number | null | undefined; decimals?: number; suffix?: string }) {
  const f = (v: number | null | undefined) => (v == null || Number.isNaN(Number(v)) ? "—" : `${Number(v).toFixed(decimals)}${suffix}`);
  const same = a != null && b != null && Math.abs(Number(a) - Number(b)) < (decimals ? 0.15 : 0.5);
  return (
    <tr className="border-b last:border-0">
      <td className="py-1.5 pr-3">{label}</td>
      <td className="py-1.5 pr-3 text-right" data-numeric>{f(a)}</td>
      <td className={cn("py-1.5 pr-3 text-right", b != null && !same && "text-warning font-semibold")} data-numeric>
        {f(b)}
      </td>
    </tr>
  );
}
