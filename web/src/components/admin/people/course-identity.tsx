"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { CourseRow } from "@/lib/admin";
import { updateCourseIdentity } from "@/app/(app)/admin/actions";
import { COURSE_HUES, courseInitials } from "../course-hues";
import { CourseSquare } from "../course-square";

/** Colour (one of eight) and initials per course — the identity square every page shows. */
export function CourseIdentityEditor({ courses }: { courses: CourseRow[] }) {
  return (
    <div className="bg-card shadow-soft divide-y overflow-hidden rounded-xl border">
      {courses.map((c) => (
        <CourseRowEditor key={c.id} course={c} />
      ))}
      {courses.length === 0 && <p className="text-muted-foreground px-4 py-6 text-center text-[13px]">No courses yet.</p>}
    </div>
  );
}

function CourseRowEditor({ course }: { course: CourseRow }) {
  const router = useRouter();
  const [color, setColor] = React.useState(course.color ?? "");
  const [initials, setInitials] = React.useState(courseInitials(course.initials, course.name));
  const [pending, startTransition] = React.useTransition();
  const dirty = color !== (course.color ?? "") || initials !== courseInitials(course.initials, course.name);

  const save = () =>
    startTransition(async () => {
      const r = await updateCourseIdentity({ courseId: course.id, color, initials });
      if (!r.ok) {
        toast.error(`Could not save ${course.name}`, { description: r.error });
        return;
      }
      toast.success(`${course.name} updated`);
      router.refresh();
    });

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <CourseSquare name={course.name} slug={course.slug} color={color || null} initials={initials} size="lg" />
      <div className="min-w-40 flex-1">
        <div className="text-[13px] font-medium">{course.name}</div>
        <div className="text-muted-foreground font-mono text-[11px]">/c/{course.slug}</div>
      </div>
      <div className="flex items-center gap-1" role="radiogroup" aria-label={`Colour for ${course.name}`}>
        {COURSE_HUES.map((h) => (
          <button
            key={h.key}
            type="button"
            role="radio"
            aria-checked={color === h.key}
            aria-label={h.label}
            title={h.label}
            onClick={() => setColor(h.key)}
            className={cn(
              "size-6 rounded-md border-2 transition-transform focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
              color === h.key ? "border-foreground scale-110" : "border-transparent hover:scale-105",
            )}
            style={{ background: h.token }}
          />
        ))}
      </div>
      <Input
        value={initials}
        onChange={(e) => setInitials(e.target.value.toUpperCase().slice(0, 3))}
        maxLength={3}
        aria-label={`Initials for ${course.name}`}
        className="w-16 text-center font-mono uppercase"
      />
      <Button type="button" size="sm" variant={dirty ? "default" : "outline"} onClick={save} disabled={!dirty || pending || !initials || !color}>
        Save
      </Button>
    </div>
  );
}
