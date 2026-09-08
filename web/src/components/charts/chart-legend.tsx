"use client";

import * as React from "react";

/** What a ChartCard's legend chips have hidden. Charts read it to fade series out; labels
 *  match series by NAME, falling back to legend POSITION (the scatter's two classes). */
export type LegendState = {
  labels: string[];
  hidden: ReadonlySet<string>;
  toggle: (label: string) => void;
};

export const ChartLegendContext = React.createContext<LegendState | null>(null);

export function useSeriesHidden(): (name: string, index: number) => boolean {
  const ctx = React.useContext(ChartLegendContext);
  return React.useCallback(
    (name, index) => {
      if (!ctx || ctx.hidden.size === 0) return false;
      if (ctx.labels.includes(name)) return ctx.hidden.has(name);
      const byIndex = ctx.labels[index];
      return byIndex != null && ctx.hidden.has(byIndex);
    },
    [ctx],
  );
}
