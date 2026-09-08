"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowLeftRight, Star, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, fieldClasses } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { CohortRow, CourseRow, MemberRole, MemberRow } from "@/lib/admin";
import { addTeamMember, handOverCourse, removeTeamMember, updateTeamMember } from "@/app/(app)/c/[course]/settings/actions";
import { ConfirmDialog } from "../confirm-dialog";
import { AddDialog } from "../people/add-dialog";
import type { TypeaheadOption } from "../typeahead";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—");
const ROLE_LABEL: Record<MemberRole, string> = { owner: "Owner", pm: "PM", viewer: "Viewer" };

/** This course's people: who is on it, who handles it, hand-over with a note. */
export function TeamTab({
  course,
  members,
  cohorts,
  staff,
  canEdit,
}: {
  course: CourseRow;
  members: MemberRow[];
  cohorts: CohortRow[];
  staff: { user_id: string; full_name: string | null; email: string | null }[];
  canEdit: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [addOpen, setAddOpen] = React.useState(false);
  const [handOpen, setHandOpen] = React.useState(false);
  const [removeId, setRemoveId] = React.useState<string | null>(null);
  const [toId, setToId] = React.useState("");
  const [note, setNote] = React.useState("");
  const handler = members.find((m) => m.is_handler) ?? null;
  const memberById = (id: string) => members.find((m) => m.id === id);
  const staffOptions = React.useMemo<TypeaheadOption[]>(
    () => staff.filter((s) => s.email).map((s) => ({ id: s.email!.toLowerCase(), label: s.full_name || s.email!, hint: s.email! })),
    [staff],
  );

  const changeRole = (m: MemberRow, role: MemberRole) =>
    startTransition(async () => {
      const r = await updateTeamMember({ courseId: course.id, id: m.id, role });
      if (!r.ok) {
        toast.error("Could not change the role", { description: r.error });
        return;
      }
      toast.success(`${m.display_name ?? m.email} is now ${ROLE_LABEL[role]}`);
      router.refresh();
    });

  const handOver = () =>
    startTransition(async () => {
      const r = await handOverCourse({ courseId: course.id, toMemberId: toId, note });
      if (!r.ok) {
        toast.error("Hand-over failed", { description: r.error });
        return;
      }
      setHandOpen(false);
      setNote("");
      toast.success(`${memberById(toId)?.display_name ?? "They"} now handle${memberById(toId) ? "s" : ""} ${course.name}`, {
        description: "Recorded in the audit trail; Slack routing follows on the next sync.",
      });
      router.refresh();
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px]">
          Handler:{" "}
          {handler ? (
            <span className="font-medium">
              <Star className="text-warning mr-1 inline size-3 fill-current" aria-hidden />
              {handler.display_name ?? handler.email}
            </span>
          ) : (
            <span className="text-warning font-medium">nobody yet — flagged classes go to the admin channel</span>
          )}
        </p>
        {canEdit && (
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setHandOpen(true)} disabled={members.length === 0}>
              <ArrowLeftRight aria-hidden /> Hand over to…
            </Button>
            <Button type="button" size="sm" onClick={() => setAddOpen(true)}>
              <UserPlus aria-hidden /> Add by IK email
            </Button>
          </div>
        )}
      </div>

      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        {members.length === 0 ? (
          <p className="text-muted-foreground px-4 py-6 text-center text-[13px]">Nobody is on this course yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Person</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Since</TableHead>
                <TableHead>Hand-over</TableHead>
                {canEdit && <TableHead className="text-right">Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <div className="flex items-center gap-1.5 font-medium">
                      {m.is_handler && <Star className="text-warning size-3 fill-current" aria-label="handler" />}
                      {m.display_name ?? m.email}
                    </div>
                    <div className="text-muted-foreground text-[11px]">
                      {m.email}
                      {!m.user_id && " · not signed in yet"}
                    </div>
                  </TableCell>
                  <TableCell>
                    {canEdit ? (
                      <Select value={m.role} onChange={(e) => changeRole(m, e.target.value as MemberRole)} disabled={pending} className="w-28" aria-label={`Role for ${m.email}`}>
                        <option value="owner">Owner</option>
                        <option value="pm">PM</option>
                        <option value="viewer">Viewer</option>
                      </Select>
                    ) : (
                      ROLE_LABEL[m.role]
                    )}
                  </TableCell>
                  <TableCell className="text-[12px]">{m.cohort_id ? (cohorts.find((k) => k.id === m.cohort_id)?.name ?? "one cohort") : "whole course"}</TableCell>
                  <TableCell className="text-[12px] whitespace-nowrap">{when(m.created_at)}</TableCell>
                  <TableCell className="text-muted-foreground text-[12px]">
                    {m.handed_over_at ? `took over ${when(m.handed_over_at)}${m.handed_over_from ? ` from ${memberById(m.handed_over_from)?.display_name ?? "a previous handler"}` : ""}` : "—"}
                  </TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button type="button" size="sm" variant="ghost" className="text-destructive" onClick={() => setRemoveId(m.id)} disabled={pending}>
                        Remove
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {addOpen && (
        <AddDialog
          open
          courses={[course]}
          cohorts={cohorts}
          staffOptions={staffOptions}
          initialEmail={null}
          initialCourseId={course.id}
          lockCourse
          busy={pending}
          onClose={() => setAddOpen(false)}
          onSubmit={(v) =>
            startTransition(async () => {
              const r = await addTeamMember({ courseId: course.id, email: v.email, role: v.role, cohortId: v.cohortId });
              if (!r.ok) {
                toast.error("Could not add", { description: r.error });
                return;
              }
              if (v.isHandler) {
                const h = await handOverCourse({ courseId: course.id, toMemberId: r.data.id, note: "Added as handler" });
                if (!h.ok) toast.error("Added, but could not make them the handler", { description: h.error });
              }
              setAddOpen(false);
              toast.success(`${v.email} added to ${course.name}`);
              router.refresh();
            })
          }
        />
      )}

      <ConfirmDialog
        open={handOpen}
        title={`Hand over ${course.name}`}
        description="The new handler receives the Slack pings for flagged classes. Both people can read the note in the audit trail."
        confirmLabel="Hand over"
        busy={pending}
        disabled={!toId || note.trim().length < 3 || toId === handler?.id}
        onConfirm={handOver}
        onClose={() => setHandOpen(false)}
      >
        <div className="space-y-3">
          <label className="block space-y-1">
            <span className="text-muted-foreground block text-[11.5px] font-medium">Hand over to</span>
            <Select value={toId} onChange={(e) => setToId(e.target.value)} aria-label="New handler">
              <option value="">Pick a member…</option>
              {members.map((m) => (
                <option key={m.id} value={m.id} disabled={m.is_handler}>
                  {m.display_name ?? m.email}
                  {m.is_handler ? " (current handler)" : ""}
                </option>
              ))}
            </Select>
          </label>
          <label className="block space-y-1">
            <span className="text-muted-foreground block text-[11.5px] font-medium">Note</span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              maxLength={1000}
              placeholder="What the new handler should know — open flags, cohorts in flight, anything pending."
              className={cn(fieldClasses, "placeholder:text-muted-foreground h-auto w-full resize-y px-3 py-2")}
            />
          </label>
        </div>
      </ConfirmDialog>

      <ConfirmDialog
        open={!!removeId}
        title={`Remove ${memberById(removeId ?? "")?.display_name ?? "this person"} from ${course.name}?`}
        description={memberById(removeId ?? "")?.is_handler ? "They are the handler — the course will have no handler until you hand it over." : "They keep read access; only this membership goes."}
        confirmLabel="Remove"
        destructive
        busy={pending}
        onConfirm={() =>
          startTransition(async () => {
            if (!removeId) return;
            const r = await removeTeamMember({ courseId: course.id, id: removeId });
            setRemoveId(null);
            if (!r.ok) {
              toast.error("Could not remove", { description: r.error });
              return;
            }
            toast.success("Removed");
            router.refresh();
          })
        }
        onClose={() => setRemoveId(null)}
      />
    </div>
  );
}
