"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CourseRow, MemberRow } from "@/lib/admin";
import { setMemberSlack } from "@/app/(app)/c/[course]/settings/actions";

/** Who gets Slack pings for this course. Routing (plan 5f): a flagged class → the cohort's
 *  handler first, then every member with Slack on (one card in the team channel). The toggle only
 *  silences a person; it does not change who is next in line. */
export function NotificationsTab({ course, members, canEdit, selfEmail }: { course: CourseRow; members: MemberRow[]; canEdit: boolean; selfEmail: string }) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [optimistic, setOptimistic] = React.useOptimistic<Record<string, boolean>, { id: string; on: boolean }>({}, (s, { id, on }) => ({ ...s, [id]: on }));

  const toggle = (m: MemberRow, on: boolean) =>
    startTransition(async () => {
      setOptimistic({ id: m.id, on });
      const r = await setMemberSlack({ courseId: course.id, id: m.id, notifySlack: on });
      if (!r.ok) {
        toast.error("Could not change notifications", { description: r.error });
        return;
      }
      router.refresh();
    });

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-[12.5px]">
        A flagged class posts one card in the team channel and mentions everyone on this course who has Slack switched on — the
        handler first; people scoped to a cohort only for that cohort&apos;s classes. With nobody on the course the card says
        “no owner assigned”. Weekly digests are planned; the switch is kept for when they ship.
      </p>
      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        {members.length === 0 ? (
          <p className="text-muted-foreground px-4 py-6 text-center text-[13px]">Nobody is on this course yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Person</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Slack</TableHead>
                <TableHead>Slack ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => {
                const on = optimistic[m.id] ?? m.notify_slack;
                const mine = m.email.toLowerCase() === selfEmail.toLowerCase();
                return (
                  <TableRow key={m.id}>
                    <TableCell>
                      <div className="font-medium">{m.display_name ?? m.email}</div>
                      <div className="text-muted-foreground text-[11px]">{m.email}{mine ? " · you" : ""}</div>
                    </TableCell>
                    <TableCell className="capitalize">{m.role}{m.is_handler ? " · handler" : ""}</TableCell>
                    <TableCell>
                      <label className="inline-flex items-center gap-2 text-[12.5px]">
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={pending || (!canEdit && !mine)}
                          onChange={(e) => toggle(m, e.target.checked)}
                          className="accent-primary size-3.5"
                          aria-label={`Slack notifications for ${m.email}`}
                        />
                        {on ? "on" : "off"}
                      </label>
                    </TableCell>
                    <TableCell className="text-muted-foreground font-mono text-[11px]">{m.slack_user_id ?? "resolved on next sync"}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
