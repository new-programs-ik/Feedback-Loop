import * as React from "react";
import Link from "next/link";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { AutoSubmit } from "@/components/auto-submit";
import { cn } from "@/lib/utils";

export type RangePreset = "7d" | "30d" | "45d" | "90d" | "month" | "custom";

export const RANGE_LABEL: Record<RangePreset, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "45d": "Last 45 days",
  "90d": "Last 90 days",
  month: "This month",
  custom: "Custom range…",
};
const PRESETS: RangePreset[] = ["7d", "30d", "45d", "90d", "month", "custom"];

export function parseRange(v: string | undefined | null, fallback: RangePreset = "30d"): RangePreset {
  return v && (PRESETS as string[]).includes(v) ? (v as RangePreset) : fallback;
}

export function rangeToDates(range: RangePreset, from?: string, to?: string) {
  // UTC throughout, like lib/analytics and lib/report-period: mixing a local "today" with UTC
  // ISO strings made "this month" start a day early on any non-UTC machine.
  const now = new Date();
  const todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
  const daysAgo = (n: number) => todayUtc - n * 86_400_000;
  switch (range) {
    case "7d":
      return { from: iso(daysAgo(7)), to: iso(todayUtc) };
    case "30d":
      return { from: iso(daysAgo(30)), to: iso(todayUtc) };
    case "45d":
      return { from: iso(daysAgo(45)), to: iso(todayUtc) };
    case "90d":
      return { from: iso(daysAgo(90)), to: iso(todayUtc) };
    case "month":
      return { from: iso(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)), to: iso(todayUtc) };
    case "custom":
      return { from: from || iso(daysAgo(30)), to: to || iso(todayUtc) };
  }
}

export type FilterOption = { value: string; label: string };
export type FilterDef = {
  /** The query parameter. */
  name: string;
  label: string;
  value?: string | null;
  options: FilterOption[];
  /** Label of the empty option (default "All <label>"). */
  all?: string;
  className?: string;
};

/** The one filter row used by every data page: GET form (URL = state, shareable, back-button
 *  safe), auto-submits on change. From `md` up it is a frosted strip that sticks just under the
 *  topbar, so the scope of what you're reading is always one glance away; on phones it scrolls
 *  with the page. Period first, then any page-specific selects (`filters`), then a Clear link. */
export function FilterBar({
  basePath,
  range,
  from,
  to,
  presets = ["7d", "30d", "90d", "month", "custom"],
  defaultRange = "30d",
  courseId,
  courses,
  filters = [],
  extra,
  sticky = true,
  className,
  children,
}: {
  basePath: string;
  range: RangePreset;
  from?: string;
  to?: string;
  presets?: RangePreset[];
  /** The range the Clear link returns to (decides whether "Clear" shows). */
  defaultRange?: RangePreset;
  courseId?: string;
  courses?: { id: string; name: string }[];
  filters?: FilterDef[];
  /** Extra hidden inputs to preserve other query params (e.g. sort). */
  extra?: Record<string, string>;
  /** Pin under the topbar from `md` up (default). */
  sticky?: boolean;
  className?: string;
  /** Trailing controls (a density toggle, a count). */
  children?: React.ReactNode;
}) {
  const hasFilters = range !== defaultRange || !!courseId || filters.some((f) => !!f.value);
  return (
    <form
      method="get"
      action={basePath}
      data-print-hide
      data-slot="filter-bar"
      className={cn(
        "mb-5 flex flex-wrap items-center gap-2",
        sticky && "glass z-10 -mx-4 border-b px-4 py-2.5 md:sticky md:top-16 md:-mx-8 md:px-8",
        className,
      )}
    >
      {Object.entries(extra ?? {}).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      <AutoSubmit>
        <Select name="range" defaultValue={range} aria-label="Date range" className="w-40">
          {presets.map((p) => (
            <option key={p} value={p}>
              {RANGE_LABEL[p]}
            </option>
          ))}
        </Select>
      </AutoSubmit>
      {range === "custom" && (
        <>
          <Input type="date" name="from" defaultValue={from} aria-label="From date" className="w-[9.75rem]" />
          <span className="text-muted-foreground text-sm">to</span>
          <Input type="date" name="to" defaultValue={to} aria-label="To date" className="w-[9.75rem]" />
          <Button type="submit">Apply</Button>
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
      {filters.map((f) => (
        <AutoSubmit key={f.name}>
          <Select name={f.name} defaultValue={f.value ?? ""} aria-label={f.label} className={cn("w-44", f.className)}>
            <option value="">{f.all ?? `All ${f.label.toLowerCase()}`}</option>
            {f.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </AutoSubmit>
      ))}
      {hasFilters && (
        <Link
          href={basePath}
          className="text-muted-foreground hover:text-foreground hover:bg-accent inline-flex h-9 items-center rounded-md px-2.5 text-sm transition-colors"
        >
          Clear
        </Link>
      )}
      {children && <div className="ml-auto flex items-center gap-2">{children}</div>}
    </form>
  );
}
