"use client";

import * as React from "react";
import { ArrowRight, GitMerge } from "lucide-react";
import { toast } from "sonner";
import { mergeInstructors } from "./actions";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

export function MergeForm({ instructors }: { instructors: { id: string; name: string }[] }) {
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [pending, startTransition] = React.useTransition();
  const fromName = instructors.find((i) => i.id === from)?.name ?? "";
  const toName = instructors.find((i) => i.id === to)?.name ?? "";
  const ready = !!from && !!to && from !== to;

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!ready) return;
    if (
      !confirm(
        `Merge "${fromName}" into "${toName}"? All classes on "${fromName}" move to "${toName}", and "${fromName}" is removed. This can't be undone.`,
      )
    )
      return;
    const fd = new FormData(e.currentTarget);
    startTransition(async () => {
      try {
        const res = await mergeInstructors(fd);
        if (res.error) {
          toast.error(res.error);
          return;
        }
        toast.success(`Merged "${fromName}" into "${toName}".`, {
          description: "Every class and cohort reference now points at the kept name.",
        });
        setFrom("");
        setTo("");
      } catch {
        toast.error("Could not merge. Try again.");
      }
    });
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
      <div className="space-y-1">
        <label htmlFor="merge-from" className="text-muted-foreground text-xs font-medium">
          Merge this (duplicate)
        </label>
        <Select id="merge-from" name="from_id" value={from} onChange={(e) => setFrom(e.target.value)} className="min-w-52">
          <option value="">Select…</option>
          {instructors.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </Select>
      </div>
      <ArrowRight className="text-muted-foreground mb-2.5 size-4" aria-hidden />
      <div className="space-y-1">
        <label htmlFor="merge-to" className="text-muted-foreground text-xs font-medium">
          Into this (keep)
        </label>
        <Select id="merge-to" name="to_id" value={to} onChange={(e) => setTo(e.target.value)} className="min-w-52">
          <option value="">Select…</option>
          {instructors.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </Select>
      </div>
      <Button type="submit" disabled={!ready} isLoading={pending}>
        <GitMerge aria-hidden /> {pending ? "Merging…" : "Merge"}
      </Button>
    </form>
  );
}
