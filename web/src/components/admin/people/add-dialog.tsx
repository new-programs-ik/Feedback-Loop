"use client";

import * as React from "react";
import { Select } from "@/components/ui/select";
import type { CohortRow, CourseRow, MemberRole } from "@/lib/admin";
import { ConfirmDialog } from "../confirm-dialog";
import { Typeahead, type TypeaheadOption } from "../typeahead";

/** "Add to a course" — shared by the admin People matrix and each course's Team tab. Only IK
 *  addresses; a typeahead over people who have already signed in, free text for the rest. */
export function AddDialog({
  open,
  courses,
  cohorts,
  staffOptions,
  initialEmail,
  initialCourseId,
  lockCourse = false,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  courses: CourseRow[];
  cohorts: CohortRow[];
  staffOptions: TypeaheadOption[];
  initialEmail: string | null;
  initialCourseId: string;
  lockCourse?: boolean;
  busy: boolean;
  onClose: () => void;
  onSubmit: (v: { courseId: string; email: string; role: MemberRole; cohortId: string | null; isHandler: boolean }) => void;
}) {
  const [emailPick, setEmailPick] = React.useState<TypeaheadOption | null>(initialEmail ? { id: initialEmail, label: initialEmail } : null);
  const [typed, setTyped] = React.useState("");
  const [courseId, setCourseId] = React.useState(initialCourseId);
  const [role, setRole] = React.useState<MemberRole>("pm");
  const [cohortId, setCohortId] = React.useState("");
  const [isHandler, setIsHandler] = React.useState(false);
  const email = (emailPick?.id ?? typed).trim().toLowerCase();
  const valid = /^[a-z0-9._%+-]+@interviewkickstart\.com$/.test(email) && !!courseId;
  const courseCohorts = cohorts.filter((k) => k.course_id === courseId);

  return (
    <ConfirmDialog
      open={open}
      title="Add to a course"
      description="Only @interviewkickstart.com addresses. The login is linked the first time they sign in."
      confirmLabel="Add"
      busy={busy}
      disabled={!valid}
      onConfirm={() => onSubmit({ courseId, email, role, cohortId: cohortId || null, isHandler })}
      onClose={onClose}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1 sm:col-span-2">
          <span className="text-muted-foreground block text-[11.5px] font-medium">IK email</span>
          <Typeahead
            options={staffOptions}
            value={emailPick}
            onChange={(v) => {
              setEmailPick(v);
              if (v) setTyped("");
            }}
            onCreate={(t) => {
              setEmailPick(null);
              setTyped(t);
            }}
            placeholder="name@interviewkickstart.com"
            ariaLabel="IK email"
            disabled={busy}
          />
          {!emailPick && typed && <span className="text-muted-foreground block text-[11px]">Adding {typed}</span>}
          {email && !valid && <span className="text-destructive block text-[11px]">Must be an @interviewkickstart.com address.</span>}
        </label>
        <label className="block space-y-1">
          <span className="text-muted-foreground block text-[11.5px] font-medium">Course</span>
          <Select value={courseId} onChange={(e) => { setCourseId(e.target.value); setCohortId(""); }} disabled={busy || lockCourse} aria-label="Course">
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
        </label>
        <label className="block space-y-1">
          <span className="text-muted-foreground block text-[11.5px] font-medium">Role</span>
          <Select value={role} onChange={(e) => setRole(e.target.value as MemberRole)} disabled={busy} aria-label="Role">
            <option value="owner">Owner — can change settings</option>
            <option value="pm">PM</option>
            <option value="viewer">Viewer</option>
          </Select>
        </label>
        <label className="block space-y-1">
          <span className="text-muted-foreground block text-[11.5px] font-medium">Cohort scope (optional)</span>
          <Select value={cohortId} onChange={(e) => setCohortId(e.target.value)} disabled={busy || courseCohorts.length === 0} aria-label="Cohort">
            <option value="">Whole course</option>
            {courseCohorts.map((k) => (
              <option key={k.id} value={k.id}>{k.name}</option>
            ))}
          </Select>
        </label>
        <label className="flex items-center gap-2 self-end pb-2 text-[12.5px]">
          <input type="checkbox" checked={isHandler} onChange={(e) => setIsHandler(e.target.checked)} disabled={busy} className="accent-primary size-3.5" />
          Make them the handler
        </label>
      </div>
    </ConfirmDialog>
  );
}
