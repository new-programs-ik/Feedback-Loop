"use client";

import * as React from "react";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { deleteCourse } from "./actions";
import { Button } from "@/components/ui/button";

/** Delete an EMPTY course (admin only). Confirms, runs the server action in a transition so the
 *  button shows its own busy state, and toasts the outcome; the list revalidates in place. */
export function DeleteCourseButton({ courseId, name }: { courseId: string; name: string }) {
  const [pending, startTransition] = React.useTransition();

  const onDelete = () => {
    if (!confirm(`Delete "${name}"? It has no cohorts or analyses, so nothing else is affected.`)) return;
    const fd = new FormData();
    fd.set("course_id", courseId);
    startTransition(async () => {
      try {
        const res = await deleteCourse(fd);
        if (res.error) toast.error(res.error);
        else toast.success(`Deleted "${name}".`);
      } catch {
        toast.error("Could not delete the course. Try again.");
      }
    });
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      title="Delete (empty course)"
      aria-label={`Delete ${name}`}
      isLoading={pending}
      onClick={onDelete}
      className="text-muted-foreground hover:text-destructive size-8"
    >
      <Trash2 />
    </Button>
  );
}
