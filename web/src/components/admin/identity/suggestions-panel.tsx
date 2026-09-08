"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { NameStats, SuggestionRow } from "@/lib/admin";
import { acceptSuggestionsAbove, decideSuggestion } from "@/app/(app)/admin/actions";
import { ConfirmDialog } from "../confirm-dialog";

export type SuggestionCard = SuggestionRow & { raw: NameStats; candidate: NameStats };

const span = (s: NameStats) => {
  if (!s.first || !s.last) return "no classes";
  const f = new Date(s.first + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  const l = new Date(s.last + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  return f === l ? f : `${f} – ${l}`;
};

/** Suspected duplicate instructor names, side by side: the spelling the sheet recorded against
 *  the instructor the matcher thinks it is, each with its classes, dates, average and modules.
 *  Accept links the spelling as an alias (the RPC moves the rows); "Not the same person" means
 *  never suggested again. Bulk accept for the confident ones. */
export function SuggestionsPanel({ suggestions }: { suggestions: SuggestionCard[] }) {
  const router = useRouter();
  const [gone, setGone] = React.useOptimistic<Set<string>, string>(new Set(), (prev, id) => new Set(prev).add(id));
  const [pending, startTransition] = React.useTransition();
  const [threshold, setThreshold] = React.useState("0.9");
  const [bulkOpen, setBulkOpen] = React.useState(false);
  const visible = suggestions.filter((s) => !gone.has(s.id));
  const confident = visible.filter((s) => s.score >= Number(threshold)).length;

  const decide = (s: SuggestionCard, accept: boolean) =>
    startTransition(async () => {
      setGone(s.id);
      const r = await decideSuggestion({ id: s.id, accept });
      if (!r.ok) {
        toast.error(accept ? "Could not accept" : "Could not reject", { description: r.error });
        return;
      }
      toast.success(accept ? `“${s.raw_name}” now counts as ${s.candidate_name}` : `Kept “${s.raw_name}” separate`, {
        description: accept ? "Every page, the track record and the Slack card use the merged identity." : "It will not be suggested again.",
      });
      router.refresh();
    });

  const bulk = () =>
    startTransition(async () => {
      const r = await acceptSuggestionsAbove(Number(threshold));
      setBulkOpen(false);
      if (!r.ok) {
        toast.error("Bulk accept failed", { description: r.error });
        return;
      }
      toast.success(`${r.data.accepted} accepted${r.data.failed ? ` · ${r.data.failed} failed` : ""}`);
      router.refresh();
    });

  return (
    <section className="bg-card shadow-soft rounded-xl border" aria-labelledby="dup-title">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4 pb-3">
        <div>
          <h2 id="dup-title" className="text-[14px] font-semibold tracking-[-0.01em]">
            Suspected duplicates <span className="text-muted-foreground font-normal">· {visible.length}</span>
          </h2>
          <p className="text-muted-foreground text-[11.5px]">Same first name, spelling variants, one name a prefix of the other, same-course overlap.</p>
        </div>
        {visible.length > 0 && (
          <div className="flex items-center gap-2">
            <Select value={threshold} onChange={(e) => setThreshold(e.target.value)} className="w-28" aria-label="Bulk accept threshold">
              <option value="0.95">≥ 0.95</option>
              <option value="0.9">≥ 0.90</option>
              <option value="0.85">≥ 0.85</option>
              <option value="0.8">≥ 0.80</option>
            </Select>
            <Button type="button" variant="outline" size="sm" onClick={() => setBulkOpen(true)} disabled={pending || confident === 0}>
              Accept all {confident > 0 ? `(${confident})` : ""}
            </Button>
          </div>
        )}
      </div>
      {visible.length === 0 ? (
        <p className="text-muted-foreground border-t px-4 py-6 text-center text-[13px]">No suggestions waiting. New ones appear after each sync.</p>
      ) : (
        <ul className="divide-y border-t">
          {visible.map((s) => (
            <li key={s.id} className="grid gap-3 px-4 py-3 md:grid-cols-[1fr_auto_1fr_auto] md:items-center">
              <NameCard title={s.raw_name} subtitle={s.raw_has_record ? "has its own record · accepting merges it (undoable)" : "as recorded on the sheet"} stats={s.raw} />
              <div className="text-center">
                <span
                  className={cn(
                    "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[11px] font-semibold",
                    s.score >= 0.9 ? "text-success border-success/40" : s.score >= 0.75 ? "text-foreground" : "text-warning border-warning/40",
                  )}
                  title="Match confidence"
                >
                  {s.score.toFixed(2)}
                </span>
                <div className="text-muted-foreground mt-0.5 max-w-28 text-[10.5px] leading-tight">{s.method ?? "matcher"}</div>
              </div>
              <NameCard title={s.candidate_name} subtitle="existing instructor" stats={s.candidate} />
              <div className="flex items-center gap-1.5 md:flex-col md:items-stretch">
                <Button type="button" size="sm" onClick={() => decide(s, true)} disabled={pending}>
                  <Check aria-hidden /> Accept
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => decide(s, false)} disabled={pending}>
                  <X aria-hidden /> Not the same
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={bulkOpen}
        title={`Accept ${confident} suggestion${confident === 1 ? "" : "s"} at or above ${threshold}?`}
        description="Each spelling becomes an alias of its candidate and its classes move. Every merge stays undoable for 30 days from the Instructors panel."
        confirmLabel="Accept all"
        busy={pending}
        onConfirm={bulk}
        onClose={() => setBulkOpen(false)}
      />
    </section>
  );
}

function NameCard({ title, subtitle, stats }: { title: string; subtitle: string; stats: NameStats }) {
  const avg = stats.avg_score ?? stats.avg_rating;
  const avgLabel = stats.avg_score != null ? "avg score" : "avg rating";
  return (
    <div className="min-w-0">
      <div className="truncate text-[13.5px] font-semibold">{title}</div>
      <div className="text-muted-foreground text-[11px]">{subtitle}</div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px]" data-numeric>
        <span>{stats.classes} {stats.classes === 1 ? "class" : "classes"}</span>
        <span className="text-muted-foreground">{span(stats)}</span>
        {avg != null && (
          <span>
            {stats.avg_score != null ? Math.round(avg) : avg.toFixed(2)} <span className="text-muted-foreground">{avgLabel}</span>
          </span>
        )}
      </div>
      {stats.top_modules.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {stats.top_modules.map((m) => (
            <span key={m.topic} className="text-muted-foreground max-w-48 truncate rounded-full border px-1.5 py-px text-[10.5px]" title={m.topic}>
              {m.topic} · {m.n}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
