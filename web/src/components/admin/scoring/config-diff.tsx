"use client";

import * as React from "react";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ScoringConfigRow } from "@/lib/admin";
import { diffConfigs } from "../scoring-config";

/** Two versions side by side, every setting as a row, differences marked. Defaults to the
 *  active version against the newest draft — the comparison an admin wants most often. */
export function ConfigDiff({ versions }: { versions: ScoringConfigRow[] }) {
  const active = versions.find((v) => v.status === "active");
  const newest = versions.find((v) => v.id !== active?.id);
  const [aId, setA] = React.useState(active?.id ?? versions[0]?.id ?? "");
  const [bId, setB] = React.useState(newest?.id ?? versions[0]?.id ?? "");
  const [onlyChanges, setOnlyChanges] = React.useState(true);
  const a = versions.find((v) => v.id === aId);
  const b = versions.find((v) => v.id === bId);
  if (versions.length < 2 || !a || !b) return null;
  const rows = diffConfigs(a.config, b.config);
  const shown = onlyChanges ? rows.filter((r) => r.changed) : rows;
  const changedCount = rows.filter((r) => r.changed).length;
  const label = (v: ScoringConfigRow) => `v${v.version} · ${v.name}${v.status === "active" ? " (active)" : v.status === "draft" ? " (draft)" : ""}`;

  return (
    <section className="bg-card shadow-soft rounded-xl border" aria-labelledby="diff-title">
      <div className="flex flex-wrap items-end gap-3 px-4 pt-4 pb-3">
        <div className="min-w-0 flex-1">
          <h2 id="diff-title" className="text-[13px] font-semibold tracking-[-0.01em]">Compare two versions</h2>
          <p className="text-muted-foreground text-[11.5px]">{changedCount} of {rows.length} settings differ.</p>
        </div>
        <label className="block space-y-1">
          <span className="text-muted-foreground block text-[11px] font-medium">A</span>
          <Select value={aId} onChange={(e) => setA(e.target.value)} className="w-64" aria-label="Version A">
            {versions.map((v) => <option key={v.id} value={v.id}>{label(v)}</option>)}
          </Select>
        </label>
        <label className="block space-y-1">
          <span className="text-muted-foreground block text-[11px] font-medium">B</span>
          <Select value={bId} onChange={(e) => setB(e.target.value)} className="w-64" aria-label="Version B">
            {versions.map((v) => <option key={v.id} value={v.id}>{label(v)}</option>)}
          </Select>
        </label>
        <label className="flex h-9 items-center gap-2 text-[12px]">
          <input type="checkbox" checked={onlyChanges} onChange={(e) => setOnlyChanges(e.target.checked)} className="accent-primary size-3.5" />
          Only differences
        </label>
      </div>
      <div className="overflow-x-auto border-t">
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="surface-inset text-muted-foreground text-left text-[11px]">
              <th className="px-4 py-2 font-medium">Setting</th>
              <th className="px-3 py-2 text-right font-medium">A · v{a.version}</th>
              <th className="px-3 py-2 text-right font-medium">B · v{b.version}</th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 ? (
              <tr>
                <td colSpan={3} className="text-muted-foreground px-4 py-5 text-center">These two versions are identical.</td>
              </tr>
            ) : (
              shown.map((r) => (
                <tr key={r.path} className={cn("border-t", r.changed && "bg-primary/[0.04]")}>
                  <td className="px-4 py-1.5">{r.label}</td>
                  <td className={cn("px-3 py-1.5 text-right font-mono text-[12px]", r.changed && "text-muted-foreground line-through decoration-1")}>{r.before}</td>
                  <td className={cn("px-3 py-1.5 text-right font-mono text-[12px]", r.changed && "font-semibold")}>{r.after}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
