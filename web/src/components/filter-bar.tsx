import * as React from "react";
import Link from "next/link";
import { Select } from "@/components/ui/select";
import { AutoSubmit } from "@/components/auto-submit";
import { cn } from "@/lib/utils";

export type RangePreset = "7d" | "30d" | "90d" | "month" | "custom";

export function rangeToDates(range: RangePreset, from?: string, to?: string) {
  const today = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const daysAgo = (n: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() - n);
    return d;
  };
  switch (range) {
    case "7d":
      return { from: iso(daysAgo(7)), to: iso(today) };
    case "30d":
      return { from: iso(daysAgo(30)), to: iso(today) };
    case "90d":
      return { from: iso(daysAgo(90)), to: iso(today) };
    case "month":
      return { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(today) };
    case "custom":
      return { from: from || iso(daysAgo(30)), to: to || iso(today) };
  }
}

/** The one filter row used by every data page: GET form (URL = state, shareable, back-button
 *  safe), auto-submits on change, sits in a single line above what it scopes. */
export function FilterBar({
  basePath,
  range,
  from,
  to,
  courseId,
  courses,
  extra,
  className,
}: {
  basePath: string;
  range: RangePreset;
  from?: string;
  to?: string;
  courseId?: string;
  courses?: { id: string; name: string }[];
  /** Extra hidden inputs to preserve other query params (e.g. sort). */
  extra?: Record<string, string>;
  className?: string;
}) {
  const hasFilters = range !== "30d" || !!courseId;
  return (
    <form
      method="get"
      action={basePath}
      data-print-hide
      className={cn("mb-5 flex flex-wrap items-center gap-2", className)}
    >
      {Object.entries(extra ?? {}).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      <AutoSubmit>
        <Select name="range" defaultValue={range} aria-label="Date range" className="w-40">
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="90d">Last 90 days</option>
          <option value="month">This month</option>
          <option value="custom">Custom range…</option>
        </Select>
      </AutoSubmit>
      {range === "custom" && (
        <>
          <input
            type="date"
            name="from"
            defaultValue={from}
            aria-label="From date"
            className="border-input bg-card focus-visible:ring-ring/50 h-9 rounded-md border px-2.5 text-sm focus-visible:ring-2 focus-visible:outline-none"
          />
          <span className="text-muted-foreground text-sm">to</span>
          <input
            type="date"
            name="to"
            defaultValue={to}
            aria-label="To date"
            className="border-input bg-card focus-visible:ring-ring/50 h-9 rounded-md border px-2.5 text-sm focus-visible:ring-2 focus-visible:outline-none"
          />
          <button
            type="submit"
            className="bg-primary text-primary-foreground h-9 cursor-pointer rounded-md px-3 text-sm font-medium"
          >
            Apply
          </button>
        </>
      )}
      {courses && (
        <AutoSubmit>
          <Select name="course" defaultValue={courseId ?? ""} aria-label="Course" className="w-52">
            <option value="">All courses</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </AutoSubmit>
      )}
      {hasFilters && (
        <Link href={basePath} className="text-muted-foreground hover:text-foreground px-1 text-sm">
          Clear
        </Link>
      )}
    </form>
  );
}
