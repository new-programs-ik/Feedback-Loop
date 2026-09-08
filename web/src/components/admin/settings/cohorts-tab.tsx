"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CohortRow, CourseRow } from "@/lib/admin";
import { renameCohort } from "@/app/(app)/c/[course]/settings/actions";

const month = (s: string | null) => {
  if (!s) return "—";
  const d = new Date((s.length === 7 ? s + "-01" : s) + "T00:00:00");
  return Number.isNaN(+d) ? s : d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
};

/** The cohorts the sync parsed for this course, with an inline rename for the display name. */
export function CohortsTab({ course, cohorts, canEdit, error }: { course: CourseRow; cohorts: CohortRow[]; canEdit: boolean; error: string | null }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [editing, setEditing] = React.useState<{ id: string; name: string } | null>(null);

  const save = () =>
    startTransition(async () => {
      if (!editing) return;
      const r = await renameCohort({ courseId: course.id, id: editing.id, name: editing.name });
      if (!r.ok) {
        toast.error("Could not rename", { description: r.error });
        return;
      }
      setEditing(null);
      toast.success("Cohort renamed");
      router.refresh();
    });

  return (
    <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
      {error && <p className="text-muted-foreground border-b px-4 py-2 text-[12px]">Cohort details are partial until migration 0017 ({error}).</p>}
      {cohorts.length === 0 ? (
        <p className="text-muted-foreground px-4 py-6 text-center text-[13px]">No cohorts parsed for this course yet — they arrive with the sync.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Cohort</TableHead>
              <TableHead>Region</TableHead>
              <TableHead>Start</TableHead>
              <TableHead>Key</TableHead>
              {canEdit && <TableHead className="text-right">Rename</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {cohorts.map((k) => (
              <TableRow key={k.id}>
                <TableCell className="font-medium">
                  {editing?.id === k.id ? (
                    <form
                      className="flex items-center gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        save();
                      }}
                    >
                      <Input value={editing.name} onChange={(e) => setEditing({ id: k.id, name: e.target.value })} aria-label="Cohort name" className="w-64" autoFocus />
                      <Button type="submit" size="sm" disabled={pending || !editing.name.trim()}>Save</Button>
                      <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)} disabled={pending}>Cancel</Button>
                    </form>
                  ) : (
                    k.name
                  )}
                </TableCell>
                <TableCell>{k.region ?? "—"}</TableCell>
                <TableCell>{month(k.start_month)}</TableCell>
                <TableCell className="text-muted-foreground font-mono text-[11px]">{k.cohort_key ?? "—"}</TableCell>
                {canEdit && (
                  <TableCell className="text-right">
                    {editing?.id !== k.id && (
                      <Button type="button" size="sm" variant="ghost" onClick={() => setEditing({ id: k.id, name: k.name })} disabled={pending}>
                        <Pencil aria-hidden /> Rename
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
