import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { ScoreBullet, ScorePill } from "@/components/score/score-pill";
import { ClassActions } from "@/components/queue/class-actions";
import { Badge } from "@/components/ui/badge";
import {
  fetchClass,
  fetchInstructorRecent,
  fetchPings,
  fetchScoreHistory,
  fetchTopicRows,
  instructorName,
  type ClassRating,
  type PingRow,
  type ScoreHistoryRow,
} from "@/lib/ratings";
import { scoreRow, type Priors } from "@/lib/class-score";
import { ACTION_LABEL, BAND_META, bandOf, flagsToWords, round2, type Band, type ScoringConfig } from "@/lib/sentiment";
import { hrefIn } from "@/lib/workspace-shared";
import { cn } from "@/lib/utils";
import { actionWords, reviewStatusLabel } from "@/lib/labels";

export type ClassDetailData = {
  row: ClassRating;
  recent: ClassRating[];
  topicRows: ClassRating[];
  history: ScoreHistoryRow[];
  pings: PingRow[];
};

/** Everything the drawer and the class page show, in four parallel reads. */
export async function loadClassDetail(id: string): Promise<ClassDetailData | null> {
  const row = await fetchClass(id);
  if (!row) return null;
  const [recent, topicRows, history, pings] = await Promise.all([
    fetchInstructorRecent(row),
    fetchTopicRows(row),
    fetchScoreHistory(id),
    fetchPings(id),
  ]);
  return { row, recent, topicRows, history, pings };
}

const pretty = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
const short = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });
const when = (ts: string | null) => (ts ? new Date(ts).toLocaleString("en-US", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "—");

function Block({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("border-t pt-4", className)}>
      <h3 className="text-muted-foreground mb-2 text-[11px] font-semibold tracking-[0.08em] uppercase">{title}</h3>
      {children}
    </section>
  );
}

/** The class in full: score hero + bullet, the four inputs, the vote and the reach, the
 *  instructor's last six classes, the module average, what the rule says and why, the actions,
 *  the history, and the link to the AI analysis. The drawer and the printable page share it. */
export function ClassDetail({
  data,
  cfg,
  version,
  priors,
  slug,
  full = false,
}: {
  data: ClassDetailData;
  cfg: ScoringConfig;
  version: number | null;
  priors?: Priors | null;
  slug: string;
  full?: boolean;
}) {
  const { row, recent, topicRows, history, pings } = data;
  const scored = scoreRow(row, cfg, priors);
  const recentScored = recent.map((r) => ({ row: r, scored: scoreRow(r, cfg, priors) }));
  const topicScores = topicRows.map((r) => scoreRow(r, cfg, priors).score).filter((v): v is number => v != null);
  const topicAvg = topicScores.length ? round2(topicScores.reduce((a, b) => a + b, 0) / topicScores.length) : null;
  const topicBand: Band | null = topicAvg == null ? null : bandOf(topicAvg, cfg);
  const votes = row.yes_votes != null && row.no_votes != null ? row.yes_votes + row.no_votes : null;
  const yesPct = votes ? ((row.yes_votes ?? 0) / votes) * 100 : null;
  const reach = row.num_ratings != null && row.attended ? Math.min(100, (row.num_ratings / row.attended) * 100) : null;
  const flagWords = flagsToWords(scored.flags.filter((f) => f !== "guarded" && f !== "no_track"));
  const classesHref = hrefIn(slug, "/classes");
  const pageHref = `${classesHref}/${row.id}`;
  const analysisHref = row.class_id ? `/feedback/${row.class_id}` : null;
  const ruleSentence = scored.band
    ? `${BAND_META[scored.band].label}${scored.provisional ? " (based on very few responses)" : ""} → ${ACTION_LABEL[scored.action]}${scored.action === "none" ? " unless a PM asks" : ""}.`
    : `No band — ${ACTION_LABEL[scored.action]}.`;

  return (
    <div className={cn("space-y-4", full && "lg:grid lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:gap-8 lg:space-y-0")}>
      <div className="space-y-4">
        {/* hero */}
        <div className="flex flex-wrap items-start gap-4">
          <ScorePill
            variant="lg"
            score={scored.score}
            band={scored.band}
            provisional={scored.provisional}
            action={scored.action}
            emptyText={scored.score == null ? "no score" : "too few voices"}
            breakdown={{ rows: scored.rows, version, reason: scored.reason }}
          />
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold tracking-[-0.01em]">{row.topic || row.session_kind}</div>
            <div className="text-muted-foreground text-xs">
              {[row.course_name ?? row.course_label, row.cohort_text, instructorName(row), pretty(row.class_date), row.session_kind].filter(Boolean).join(" · ")}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge variant="outline">{reviewStatusLabel(row.review_status)}</Badge>
              {row.escalated && <Badge variant="destructive">Escalated</Badge>}
              {row.decision_override && <Badge variant="outline">PM chose: {actionWords(row.decision_override)}</Badge>}
              {!full && (
                <Link href={pageHref} className="text-muted-foreground hover:text-foreground ml-auto inline-flex items-center gap-1 text-xs" data-print-hide>
                  Full page <ExternalLink className="size-3" aria-hidden />
                </Link>
              )}
            </div>
          </div>
        </div>
        <ScoreBullet score={scored.score} band={scored.band} edges={cfg.bands} />
        <p className="text-sm">
          <span className="font-medium">Rule says: </span>
          {ruleSentence} <span className="text-muted-foreground">{scored.reason}</span>
        </p>
        {flagWords.length > 0 && (
          <ul className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
            {flagWords.map((w) => (
              <li key={w}>· {w}</li>
            ))}
          </ul>
        )}

        {/* the four inputs */}
        <Block title="What the score is made of">
          <table className="w-full text-[13px]">
            <tbody>
              {scored.rows.map((r) => (
                <tr key={r.key} className={cn("border-b last:border-0", !r.included && "text-muted-foreground")}>
                  <td className="py-1.5 pr-3 font-medium whitespace-nowrap">{r.label}</td>
                  <td className="text-muted-foreground py-1.5 pr-3">{r.detail}</td>
                  <td className="py-1.5 text-right whitespace-nowrap" data-numeric>
                    {r.included ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="bg-muted relative inline-block h-1.5 w-16 overflow-hidden rounded-full align-middle" aria-hidden>
                          <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${r.weight ? ((r.earned ?? 0) / r.weight) * 100 : 0}%`, background: scored.band ? BAND_META[scored.band].color : "var(--band-none)" }} />
                        </span>
                        <span className="font-medium">{r.earned}</span>
                        <span className="text-muted-foreground">/ {r.weight}</span>
                      </span>
                    ) : (
                      "excluded"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>

        {/* vote + reach */}
        <Block title="The room">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <div className="flex items-baseline justify-between text-[13px]">
                <span className="font-medium">Would have the instructor back</span>
                <span className="text-muted-foreground" data-numeric>
                  {votes ? `${row.yes_votes} yes · ${row.no_votes} no · ${Math.round(yesPct ?? 0)}%` : "no approval answers"}
                </span>
              </div>
              <div className="bg-muted mt-1.5 flex h-2 w-full overflow-hidden rounded-full" aria-hidden>
                {votes ? (
                  <>
                    <span style={{ width: `${yesPct}%`, background: "var(--viz-good)" }} />
                    <span style={{ width: `${100 - (yesPct ?? 0)}%`, background: "var(--viz-bad)" }} />
                  </>
                ) : null}
              </div>
              <div className="text-muted-foreground mt-1 text-[11px]">bar {cfg.approval.bar}%</div>
            </div>
            <div>
              <div className="flex items-baseline justify-between text-[13px]">
                <span className="font-medium">Rated / attended</span>
                <span className="text-muted-foreground" data-numeric>
                  {reach != null ? `${row.num_ratings} of ${row.attended} rated · ${Math.round(reach)}%` : "attendance unknown"}
                </span>
              </div>
              <div className="bg-muted mt-1.5 h-2 w-full overflow-hidden rounded-full" aria-hidden>
                {reach != null && <span className="block h-full rounded-full" style={{ width: `${reach}%`, background: "var(--chart-1)" }} />}
              </div>
              <div className="text-muted-foreground mt-1 text-[11px]">rating {row.rating.toFixed(2)} / {cfg.rating.scale}</div>
            </div>
          </div>
        </Block>
      </div>

      <div className="space-y-4">
        {/* actions */}
        <Block title="Actions" className={cn(full && "lg:border-t-0 lg:pt-0")}>
          <ClassActions id={row.id} status={row.review_status} escalated={row.escalated} analyzeHref={`/feedback/new?prefill=${row.id}`} analysisHref={analysisHref} />
          {analysisHref && (
            <p className="text-muted-foreground mt-2 text-xs">
              An AI analysis exists for this class —{" "}
              <Link href={analysisHref} className="text-primary hover:underline">open it</Link>.
            </p>
          )}
        </Block>

        {/* the instructor's last six */}
        <Block title={`${instructorName(row)} · last ${recentScored.length || "six"} classes`}>
          {recentScored.length === 0 ? (
            <p className="text-muted-foreground text-sm">No earlier classes recorded for this instructor.</p>
          ) : (
            <ul className="divide-y">
              {recentScored.map(({ row: r, scored: s }) => (
                <li key={r.id} className="flex items-center gap-3 py-1.5 text-[13px]">
                  <ScorePill variant="sm" score={s.score} band={s.band} provisional={s.provisional} />
                  <Link href={`${hrefIn(r.course_slug ?? slug, "/classes")}?class=${r.id}`} className="hover:text-primary min-w-0 flex-1 truncate">
                    {r.topic || r.session_kind}
                  </Link>
                  <span className="text-muted-foreground shrink-0 text-xs" data-numeric>{short(r.class_date)}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>

        {/* module average */}
        <Block title="This module">
          {topicAvg == null ? (
            <p className="text-muted-foreground text-sm">No other class of this module in the last 180 days.</p>
          ) : (
            <div className="flex items-center gap-3 text-[13px]">
              <ScorePill variant="aggregate" score={topicAvg} band={topicBand} label="module avg" />
              <span className="text-muted-foreground">
                over {topicRows.length} other {topicRows.length === 1 ? "class" : "classes"} of “{row.topic}”
                {scored.score != null && (
                  <>
                    {" · this one is "}
                    <span className={cn("font-medium", scored.score >= topicAvg ? "text-foreground" : "text-band-bad-text")} data-numeric>
                      {scored.score >= topicAvg ? "+" : "−"}{Math.abs(round2(scored.score - topicAvg))}
                    </span>
                  </>
                )}
              </span>
            </div>
          )}
        </Block>

        {/* history */}
        <Block title="History">
          {history.length === 0 && pings.length === 0 ? (
            <p className="text-muted-foreground text-sm">No score changes or Slack pings recorded yet.</p>
          ) : (
            <ul className="space-y-1 text-[13px]">
              {history.map((h) => (
                <li key={h.id} className="flex items-baseline gap-2">
                  <span className="text-muted-foreground w-28 shrink-0 text-xs" data-numeric>{when(h.scored_at)}</span>
                  <span>
                    scored {h.score ?? "—"}
                    {h.band ? ` · ${h.band}` : ""}
                    {h.config_version != null ? ` · v${h.config_version}` : ""}
                    {h.note ? ` — ${h.note}` : ""}
                  </span>
                </li>
              ))}
              {pings.map((p) => (
                <li key={p.id} className="flex items-baseline gap-2">
                  <span className="text-muted-foreground w-28 shrink-0 text-xs" data-numeric>{when(p.sent_at)}</span>
                  <span>
                    {p.channel} ping {p.status === "failed" ? "failed" : "sent"}
                    {p.recipient ? ` to ${p.recipient}` : ""}
                    {p.error ? ` — ${p.error}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Block>
      </div>
    </div>
  );
}
