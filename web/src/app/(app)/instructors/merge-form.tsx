"use client";

import { useState } from "react";
import { mergeInstructors } from "./actions";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

const field = "border-input h-9 w-full rounded-md border bg-transparent px-3 text-sm";

export function MergeForm({ instructors }: { instructors: { id: string; name: string }[] }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const fromName = instructors.find((i) => i.id === from)?.name ?? "";
  const toName = instructors.find((i) => i.id === to)?.name ?? "";

  return (
    <form
      action={mergeInstructors}
      onSubmit={(e) => {
        if (!from || !to || from === to) { e.preventDefault(); return; }
        if (!confirm(`Merge "${fromName}" into "${toName}"? All classes on "${fromName}" move to "${toName}", and "${fromName}" is removed. This can't be undone.`))
          e.preventDefault();
      }}
      className="flex flex-wrap items-end gap-3"
    >
      <div className="space-y-1">
        <label className="text-muted-foreground text-xs font-medium">Merge this (duplicate)</label>
        <select name="from_id" value={from} onChange={(e) => setFrom(e.target.value)} className={field + " min-w-52"}>
          <option value="">Select…</option>
          {instructors.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
      </div>
      <ArrowRight className="text-muted-foreground mb-2 size-4" />
      <div className="space-y-1">
        <label className="text-muted-foreground text-xs font-medium">Into this (keep)</label>
        <select name="to_id" value={to} onChange={(e) => setTo(e.target.value)} className={field + " min-w-52"}>
          <option value="">Select…</option>
          {instructors.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
      </div>
      <Button type="submit" disabled={!from || !to || from === to}>Merge</Button>
    </form>
  );
}
