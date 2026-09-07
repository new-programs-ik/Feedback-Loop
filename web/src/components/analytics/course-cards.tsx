"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { NAME_WORDS, SortControl, type SortOption } from "@/components/ui/sort-control";
import { sortRows, type SortSpec, type SortState } from "@/components/ui/sortable";

/** What a course card sorts on; the card itself is rendered on the server and comes along. */
export type CourseCardItem = {
  key: string;
  name: string;
  badShare: number | null;
  avgScore: number | null;
  n: number;
  /** Avg score minus the prior 30 days'. */
  delta: number | null;
  card: React.ReactNode;
};

type Key = "bad" | "score" | "n" | "name" | "delta";

const SPEC: SortSpec<CourseCardItem, Key> = {
  bad: { value: (c) => c.badShare, first: "desc" },
  score: { value: (c) => c.avgScore, first: "asc" },
  n: { value: (c) => c.n, first: "desc" },
  name: { value: (c) => c.name, first: "asc" },
  delta: { value: (c) => c.delta, first: "asc" },
};

/** Every option opens with the courses that need attention first. */
const OPTIONS: SortOption<Key>[] = [
  { key: "bad", label: "Bad share", first: "desc" },
  { key: "score", label: "Avg score", first: "asc" },
  { key: "n", label: "Classes", first: "desc" },
  { key: "name", label: "Name", first: "asc", words: NAME_WORDS },
  { key: "delta", label: "Δ vs prior", first: "asc" },
];

/** The team overview's course cards with a "Sort by" control. Cards are server-rendered and
 *  arrive with their sort values; this decides only the order (worst Bad share first until it is
 *  changed) and slides the cards into place. `quiet` courses — nothing rated — always sit last. */
export function CourseCards({ items, quiet, leading }: { items: CourseCardItem[]; quiet?: React.ReactNode; leading?: React.ReactNode }) {
  const reduce = useReducedMotion();
  const [state, setState] = React.useState<SortState<Key>>({ key: "bad", dir: "desc" });
  const sorted = React.useMemo(() => sortRows(items, SPEC, state), [items, state]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">{leading}</div>
        <SortControl options={OPTIONS} state={state} onChange={setState} />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {sorted.map((c) => (
          <motion.div key={c.key} layout={reduce ? false : "position"} transition={{ type: "spring", stiffness: 520, damping: 42, mass: 0.6 }}>
            {c.card}
          </motion.div>
        ))}
        {quiet}
      </div>
    </div>
  );
}
