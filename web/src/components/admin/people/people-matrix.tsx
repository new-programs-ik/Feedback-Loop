"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Plus, Star, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { cn } from "@/lib/utils";
import type { CohortRow, CourseRow, MemberRole, MemberRow } from "@/lib/admin";
import { addCourseMember, removeCourseMember, setCourseHandler, updateCourseMember } from "@/app/(app)/admin/actions";
import { ConfirmDialog } from "../confirm-dialog";
import { CourseSquare } from "../course-square";
import type { TypeaheadOption } from "../typeahead";
import { AddDialog } from "./add-dialog";

type Staff = { user_id: string; full_name: string | null; email: string | null };
type Person = { email: string; name: string; user_id: string | null };

const ROLE_LABEL: Record<MemberRole, string> = { owner: "Owner", pm: "PM", viewer: "Viewer" };

/** The rows sort by person (A → Z first); the course columns keep their order. */
const PERSON_SPEC: SortSpec<Person, "person"> = { person: { value: (p) => p.name, first: "asc" } };

/** People × courses. Each cell is that person's membership on that course (role, handler star,
 *  cohort scope) or a "+" to add them. Editing happens in one dialog per cell; adding by IK
 *  email at the top. Courses without a handler are flagged in their column header. */
export function PeopleMatrix({
  courses,
  members,
  cohorts,
  staff,
}: {
  courses: CourseRow[];
  members: MemberRow[];
  cohorts: CohortRow[];
  staff: Staff[];
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const people = React.useMemo<Person[]>(() => {
    const map = new Map<string, Person>();
    for (const m of members) {
      const key = m.email.toLowerCase();
      if (!map.has(key)) map.set(key, { email: key, name: m.display_name || key, user_id: m.user_id });
    }
    return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [members]);
  const { sorted: ordered, state: sort, toggle } = useSortable(people, PERSON_SPEC, { key: "person", dir: "asc" });
  const cell = (email: string, courseId: string) => members.find((m) => m.email.toLowerCase() === email && m.course_id === courseId);
  const noHandler = courses.filter((c) => !members.some((m) => m.course_id === c.id && m.is_handler));

  const [add, setAdd] = React.useState<{ email: string | null; courseId: string } | null>(null);
  const [edit, setEdit] = React.useState<MemberRow | null>(null);
  const staffOptions = React.useMemo<TypeaheadOption[]>(
    () => staff.filter((s) => s.email).map((s) => ({ id: s.email!.toLowerCase(), label: s.full_name || s.email!, hint: s.email! })),
    [staff],
  );

  return (
    <div className="space-y-4" data-slot="people-matrix">
      {noHandler.length > 0 && (
        <p className="border-warning/40 bg-warning/5 rounded-md border px-3 py-2 text-[12.5px]">
          No handler set: {noHandler.map((c) => c.name).join(", ")}. Flagged classes on these courses go to the admin channel with “no handler set”.
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-[12px]">
          {people.length} {people.length === 1 ? "person" : "people"} · {members.length} memberships · ★ = handler (exactly one per course)
        </p>
        <Button type="button" size="sm" onClick={() => setAdd({ email: null, courseId: courses[0]?.id ?? "" })} disabled={courses.length === 0}>
          <UserPlus aria-hidden /> Add by IK email
        </Button>
      </div>

      <div className="bg-card shadow-soft overflow-x-auto rounded-xl border">
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="surface-inset border-b">
              <SortButton sortKey="person" state={sort} onToggle={toggle} className="sticky left-0 z-10 min-w-48">
                Person
              </SortButton>
              {courses.map((c) => {
                const missing = noHandler.some((n) => n.id === c.id);
                return (
                  <th key={c.id} className={cn("min-w-28 px-2 py-2 text-left text-[11px] font-medium", missing && "bg-warning/10")} title={missing ? "No handler set" : undefined}>
                    <span className="inline-flex items-center gap-1.5">
                      <CourseSquare name={c.name} slug={c.slug} color={c.color} initials={c.initials} size="sm" />
                      <span className="max-w-32 truncate">{c.name}</span>
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {people.length === 0 ? (
              <tr>
                <td colSpan={courses.length + 1} className="text-muted-foreground px-4 py-8 text-center text-[13px]">
                  Nobody is on a course yet — add the first PM by IK email.
                </td>
              </tr>
            ) : (
              ordered.map((p) => (
                <tr key={p.email} className="border-b last:border-0">
                  <td className="bg-card sticky left-0 z-10 px-4 py-2 align-middle">
                    <div className="truncate font-medium">{p.name}</div>
                    <div className="text-muted-foreground truncate text-[11px]">
                      {p.email}
                      {!p.user_id && " · not signed in yet"}
                    </div>
                  </td>
                  {courses.map((c) => {
                    const m = cell(p.email, c.id);
                    return (
                      <td key={c.id} className="px-2 py-1.5 align-middle">
                        {m ? (
                          <button
                            type="button"
                            onClick={() => setEdit(m)}
                            className="hover:bg-accent focus-visible:ring-ring/50 inline-flex max-w-full items-center gap-1 rounded-md border px-2 py-1 text-left text-[11.5px] focus-visible:ring-2 focus-visible:outline-none"
                            aria-label={`${p.name} on ${c.name}: ${ROLE_LABEL[m.role]}${m.is_handler ? ", handler" : ""}. Edit`}
                          >
                            {m.is_handler && <Star className="text-warning size-3 fill-current" aria-hidden />}
                            <span className="font-medium">{ROLE_LABEL[m.role]}</span>
                            {m.cohort_id && (
                              <span className="text-muted-foreground truncate">· {cohorts.find((k) => k.id === m.cohort_id)?.name ?? "cohort"}</span>
                            )}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setAdd({ email: p.email, courseId: c.id })}
                            className="text-muted-foreground/60 hover:text-foreground hover:bg-accent focus-visible:ring-ring/50 inline-flex size-7 items-center justify-center rounded-md focus-visible:ring-2 focus-visible:outline-none"
                            aria-label={`Add ${p.name} to ${c.name}`}
                          >
                            <Plus className="size-3.5" aria-hidden />
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {add && (
        <AddDialog
          open
          courses={courses}
          cohorts={cohorts}
          staffOptions={staffOptions}
          initialEmail={add.email}
          initialCourseId={add.courseId}
          busy={pending}
          onClose={() => setAdd(null)}
          onSubmit={(v) =>
            startTransition(async () => {
              const r = await addCourseMember(v);
              if (!r.ok) {
                toast.error("Could not add", { description: r.error });
                return;
              }
              setAdd(null);
              toast.success(`${v.email} added`, { description: v.isHandler ? "They are now the handler for this course." : undefined });
              router.refresh();
            })
          }
        />
      )}
      {edit && (
        <EditDialog
          open
          member={edit}
          course={courses.find((c) => c.id === edit.course_id)}
          cohorts={cohorts.filter((k) => k.course_id === edit.course_id)}
          busy={pending}
          onClose={() => setEdit(null)}
          onSave={(patch) =>
            startTransition(async () => {
              const r = await updateCourseMember({ id: edit.id, ...patch });
              if (!r.ok) {
                toast.error("Could not update", { description: r.error });
                return;
              }
              setEdit(null);
              toast.success("Membership updated");
              router.refresh();
            })
          }
          onHandler={() =>
            startTransition(async () => {
              const r = await setCourseHandler({ courseId: edit.course_id, memberId: edit.id });
              if (!r.ok) {
                toast.error("Could not set the handler", { description: r.error });
                return;
              }
              setEdit(null);
              toast.success(`${edit.display_name ?? edit.email} is now the handler`);
              router.refresh();
            })
          }
          onRemove={() =>
            startTransition(async () => {
              const r = await removeCourseMember({ id: edit.id });
              if (!r.ok) {
                toast.error("Could not remove", { description: r.error });
                return;
              }
              setEdit(null);
              toast.success("Removed from the course");
              router.refresh();
            })
          }
        />
      )}
    </div>
  );
}

function EditDialog({
  open,
  member,
  course,
  cohorts,
  busy,
  onClose,
  onSave,
  onHandler,
  onRemove,
}: {
  open: boolean;
  member: MemberRow;
  course: CourseRow | undefined;
  cohorts: CohortRow[];
  busy: boolean;
  onClose: () => void;
  onSave: (patch: { role: MemberRole; cohortId: string | null; notifySlack: boolean }) => void;
  onHandler: () => void;
  onRemove: () => void;
}) {
  const [role, setRole] = React.useState<MemberRole>(member.role);
  const [cohortId, setCohortId] = React.useState(member.cohort_id ?? "");
  const [notify, setNotify] = React.useState(member.notify_slack);
  const [confirmRemove, setConfirmRemove] = React.useState(false);
  return (
    <>
      <ConfirmDialog
        open={open && !confirmRemove}
        title={`${member.display_name ?? member.email} · ${course?.name ?? "course"}`}
        description={member.handed_over_at ? `Took over on ${new Date(member.handed_over_at).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })}.` : undefined}
        confirmLabel="Save"
        busy={busy}
        onConfirm={() => onSave({ role, cohortId: cohortId || null, notifySlack: notify })}
        onClose={onClose}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block space-y-1">
            <span className="text-muted-foreground block text-[11.5px] font-medium">Role</span>
            <Select value={role} onChange={(e) => setRole(e.target.value as MemberRole)} disabled={busy} aria-label="Role">
              <option value="owner">Owner — can change settings</option>
              <option value="pm">PM</option>
              <option value="viewer">Viewer</option>
            </Select>
          </label>
          <label className="block space-y-1">
            <span className="text-muted-foreground block text-[11.5px] font-medium">Cohort scope</span>
            <Select value={cohortId} onChange={(e) => setCohortId(e.target.value)} disabled={busy || cohorts.length === 0} aria-label="Cohort">
              <option value="">Whole course</option>
              {cohorts.map((k) => (
                <option key={k.id} value={k.id}>{k.name}</option>
              ))}
            </Select>
          </label>
          <label className="flex items-center gap-2 text-[12.5px] sm:col-span-2">
            <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} disabled={busy} className="accent-primary size-3.5" />
            Slack notifications for this course
          </label>
          <div className="flex flex-wrap items-center gap-2 border-t pt-3 sm:col-span-2">
            {member.is_handler ? (
              <span className="text-warning inline-flex items-center gap-1 text-[12px] font-medium">
                <Star className="size-3 fill-current" aria-hidden /> Handler for this course
              </span>
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={onHandler} disabled={busy}>
                <Star aria-hidden /> Make handler
              </Button>
            )}
            <Button type="button" size="sm" variant="ghost" className="text-destructive ml-auto" onClick={() => setConfirmRemove(true)} disabled={busy}>
              Remove from course
            </Button>
          </div>
        </div>
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmRemove}
        title={`Remove ${member.display_name ?? member.email} from ${course?.name ?? "this course"}?`}
        description={member.is_handler ? "They are the handler — the course will have no handler until you set one." : "They keep read access to every course; only this membership goes."}
        confirmLabel="Remove"
        destructive
        busy={busy}
        onConfirm={onRemove}
        onClose={() => setConfirmRemove(false)}
      />
    </>
  );
}
