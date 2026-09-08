import * as React from "react";
import { cn } from "@/lib/utils";
import { BAND_META, bandOf } from "@/lib/sentiment";

export type CalendarDay = { date: string; value: number | null; n: number };

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const iso = (d: Date) => d.toISOString().slice(0, 10);
function monday(isoDate: string) {
  const d = new Date(isoDate + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return iso(d);
}
const addDays = (isoDate: string, n: number) => iso(new Date(+new Date(isoDate + "T00:00:00Z") + n * 86400000));

/** Weeks across, weekdays down; each day tinted by the band of its average score, with the
 *  class count on hover. Answers "do bad classes cluster on certain days?". Server-safe. */
export function CalendarHeatmap({ days, from, to, className }: { days: CalendarDay[]; from: string; to: string; className?: string }) {
  const byDate = new Map(days.map((d) => [d.date, d]));
  const weeks: string[] = [];
  for (let w = monday(from); w <= to; w = addDays(w, 7)) weeks.push(w);
  const monthLabel = (w: string, i: number) => {
    const m = w.slice(0, 7);
    const prev = i > 0 ? weeks[i - 1].slice(0, 7) : null;
    return m !== prev ? new Date(w + "T00:00:00").toLocaleString("en-US", { month: "short" }) : "";
  };
  return (
    <div className={cn("overflow-x-auto", className)}>
      <div className="inline-grid gap-1" style={{ gridTemplateColumns: `28px repeat(${weeks.length}, 16px)` }}>
        <span />
        {weeks.map((w, i) => (
          <span key={w} className="text-muted-foreground h-3 text-[9px] leading-3">
            {monthLabel(w, i)}
          </span>
        ))}
        {DOW.map((d, di) => (
          <React.Fragment key={d}>
            <span className="text-muted-foreground text-[9.5px] leading-4">{di % 2 === 0 ? d : ""}</span>
            {weeks.map((w) => {
              const date = addDays(w, di);
              const cell = byDate.get(date);
              const inRange = date >= from && date <= to;
              const band = cell?.value == null ? null : bandOf(cell.value);
              const title = cell
                ? `${date} · ${cell.value == null ? "no score" : `${Math.round(cell.value)} · ${BAND_META[bandOf(cell.value)].label}`} · ${cell.n} ${cell.n === 1 ? "class" : "classes"}`
                : `${date} · no classes`;
              return (
                <span
                  key={date}
                  title={title}
                  aria-label={title}
                  className={cn("size-4 rounded-[3px]", !inRange && "opacity-0", !cell && inRange && "bg-muted")}
                  style={band ? { background: BAND_META[band].color, opacity: 0.35 + Math.min(0.65, (cell?.n ?? 0) * 0.15) } : undefined}
                />
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
