"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { CourseRow } from "@/lib/admin";
import { mapLabelToCourse, requestSyncNow } from "@/app/(app)/admin/actions";

/** "Sync now": asks the worker to read the sheet; the reason comes back as data so the toast can
 *  say "it may be waking up" in production too. */
export function SyncNowButton() {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const run = () =>
    startTransition(async () => {
      const r = await requestSyncNow();
      if (r.ok) {
        toast.success("Sync requested", { description: "The sheet is being read now — this page refreshes in a moment." });
        window.setTimeout(() => router.refresh(), 6000);
      } else toast.error("Sync could not start", { description: r.error });
    });
  return (
    <Button variant="outline" type="button" onClick={run} disabled={pending} aria-busy={pending} className="min-w-28">
      <RefreshCw className={cn("size-4", pending && "animate-spin")} aria-hidden />
      {pending ? "Syncing…" : "Sync now"}
    </Button>
  );
}

/** Unmapped sheet labels → a course. Each mapping sticks for every future sync and backfills
 *  the rows already here. */
export function MapLabels({ labels, courses }: { labels: { label: string; classes: number }[]; courses: CourseRow[] }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [picks, setPicks] = React.useState<Record<string, string>>({});
  const [gone, setGone] = React.useOptimistic<Set<string>, string>(new Set(), (p, l) => new Set(p).add(l));
  const visible = labels.filter((l) => !gone.has(l.label));

  const map = (label: string) => {
    const courseId = picks[label];
    if (!courseId) return;
    startTransition(async () => {
      setGone(label);
      const r = await mapLabelToCourse({ alias: label, courseId });
      if (!r.ok) {
        toast.error("Could not map the label", { description: r.error });
        return;
      }
      toast.success(`“${label}” → ${courses.find((c) => c.id === courseId)?.name ?? "course"}`, { description: `${r.data.updated} existing classes moved.` });
      router.refresh();
    });
  };

  if (visible.length === 0) return <p className="text-muted-foreground text-[12.5px]">Every sheet label maps to a course.</p>;
  return (
    <div className="space-y-2">
      {visible.map((l) => (
        <div key={l.label} className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{l.label}</Badge>
          <span className="text-muted-foreground text-[11px]" data-numeric>{l.classes} classes</span>
          <span className="text-muted-foreground text-sm">→</span>
          <Select value={picks[l.label] ?? ""} onChange={(e) => setPicks((p) => ({ ...p, [l.label]: e.target.value }))} className="w-56" aria-label={`Course for ${l.label}`}>
            <option value="" disabled>Pick the course…</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
          <Button variant="outline" size="sm" type="button" onClick={() => map(l.label)} disabled={pending || !picks[l.label]}>
            Map
          </Button>
        </div>
      ))}
    </div>
  );
}
