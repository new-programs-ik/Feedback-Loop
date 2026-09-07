import * as React from "react";
import Link from "next/link";
import { AlertTriangle, ArrowDownRight, ArrowRight, Users, Wrench } from "lucide-react";
import { BAND_META } from "@/lib/sentiment";
import { Empty, Section } from "@/components/analytics/ui";
import type { Insight, InsightKind } from "@/lib/curriculum";
import { cn } from "@/lib/utils";

/** The sentences the curriculum map produces, as a strip of small cards: an icon for the kind
 *  of finding, the sentence with its name in bold, one line of detail, and the link that opens
 *  the module, the instructor or the map. Server-safe; the overview and the cohorts page share
 *  it so the copy and the look are identical everywhere. */

const KIND: Record<InsightKind, { icon: React.ComponentType<{ className?: string }>; color: string; word: string }> = {
  attendance_drop: { icon: Users, color: BAND_META.average.text, word: "Attendance" },
  rating_dip: { icon: ArrowDownRight, color: BAND_META.bad.text, word: "Rating" },
  consistent_low: { icon: AlertTriangle, color: BAND_META.bad.text, word: "Content" },
  fixer: { icon: Wrench, color: BAND_META.excellent.text, word: "Who lifts it" },
};

/** "**Name** does X" → the name in bold. */
export function BoldSentence({ text }: { text: string }) {
  const parts = text.split("**");
  return (
    <>
      {parts.map((p, i) => (i % 2 ? <strong key={i} className="text-foreground font-semibold">{p}</strong> : <React.Fragment key={i}>{p}</React.Fragment>))}
    </>
  );
}

export function InsightsStrip({
  insights,
  title,
  subtitle,
  limit,
  emptyText = "Nothing stands out yet — the sentences need two cohorts on the same modules.",
  className,
}: {
  insights: Insight[];
  title: string;
  subtitle?: string;
  limit?: number;
  emptyText?: string;
  className?: string;
}) {
  const list = limit ? insights.slice(0, limit) : insights;
  return (
    <Section title={title} subtitle={subtitle} className={className} bodyClassName={list.length ? undefined : "px-0 pb-0"}>
      {list.length === 0 ? (
        <Empty className="pt-1">{emptyText}</Empty>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.map((ins, i) => {
            const meta = KIND[ins.kind];
            const Icon = meta.icon;
            const body = (
              <>
                <div className="flex items-center gap-1.5">
                  <Icon className="size-3.5 shrink-0" aria-hidden />
                  <span className="text-[10.5px] font-semibold tracking-[0.08em] uppercase" style={{ color: meta.color }}>
                    {meta.word}
                  </span>
                </div>
                <p className="text-foreground/90 mt-1.5 text-[13px] leading-snug">
                  <BoldSentence text={ins.title} />
                </p>
                <p className="text-muted-foreground mt-1 text-[11.5px] leading-snug">{ins.detail}</p>
                {ins.href && (
                  <span className="text-primary mt-2 inline-flex items-center gap-1 text-[11px] font-medium">
                    {ins.kind === "fixer" && ins.instructorKey ? "Open the instructor" : ins.kind === "attendance_drop" && !ins.moduleKey ? "Open the map" : "Open the module"}
                    <ArrowRight className="size-3 transition-transform duration-150 group-hover/insight:translate-x-0.5" aria-hidden />
                  </span>
                )}
              </>
            );
            const cls = cn("surface-inset group/insight block h-full rounded-lg border p-3 transition-colors duration-150", ins.href && "hover:bg-accent/40");
            return (
              <li key={`${ins.kind}-${i}`} className="min-w-0" style={{ color: meta.color }}>
                {ins.href ? (
                  <Link href={ins.href} className={cls}>
                    {body}
                  </Link>
                ) : (
                  <div className={cls}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
