"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import { fieldClasses } from "@/components/ui/select";
import type { SortDir, SortState } from "@/components/ui/sortable";
import { cn } from "@/lib/utils";

export type SortOption<K extends string> = {
  key: K;
  label: string;
  /** The direction the option opens with — numbers usually "desc", the big ones first. */
  first: SortDir;
  /** What the direction button says, ascending then descending. Default: Low → high / High → low. */
  words?: readonly [asc: string, desc: string];
};

export const NUMBER_WORDS = ["Low → high", "High → low"] as const;
export const NAME_WORDS = ["A → Z", "Z → A"] as const;
export const DATE_WORDS = ["Oldest first", "Newest first"] as const;

/** "Sort by [field] [direction]" for things that are not tables — a card grid, a queue section.
 *  A native select (keyboard and mobile pickers for free) and a button that flips the direction
 *  in plain words, so the current order can always be read off the control itself. */
export function SortControl<K extends string>({
  options,
  state,
  onChange,
  label = "Sort by",
  className,
}: {
  options: readonly SortOption<K>[];
  state: SortState<K>;
  onChange: (next: SortState<K>) => void;
  label?: string;
  className?: string;
}) {
  const id = React.useId();
  const current = options.find((o) => o.key === state.key) ?? options[0];
  const words = current.words ?? NUMBER_WORDS;
  const flipped: SortDir = state.dir === "asc" ? "desc" : "asc";
  const saying = state.dir === "asc" ? words[0] : words[1];
  return (
    <div className={cn("inline-flex items-center gap-1.5 text-[11.5px]", className)} data-slot="sort-control">
      <label htmlFor={id} className="text-muted-foreground">
        {label}
      </label>
      <span className="relative inline-flex">
        <select
          id={id}
          value={state.key}
          onChange={(e) => {
            const o = options.find((x) => x.key === e.target.value) ?? options[0];
            onChange({ key: o.key, dir: o.first });
          }}
          className={cn(fieldClasses, "h-7 cursor-pointer appearance-none py-0 pr-6 pl-2 text-[11.5px] font-medium")}
        >
          {options.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden className="text-muted-foreground pointer-events-none absolute top-1/2 right-1.5 size-3.5 -translate-y-1/2" />
      </span>
      <button
        type="button"
        onClick={() => onChange({ key: state.key, dir: flipped })}
        className={cn(fieldClasses, "text-muted-foreground hover:text-foreground h-7 cursor-pointer px-2 text-[11.5px] font-medium")}
        title={`Flip to ${(flipped === "asc" ? words[0] : words[1]).toLowerCase()}`}
        aria-label={`Order: ${saying}. Flip the order`}
      >
        {saying}
      </button>
    </div>
  );
}
