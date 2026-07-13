"use client";

import { useActionState } from "react";
import { createCourse, type CourseState } from "./actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus } from "lucide-react";

export function AddCourseForm() {
  const [state, formAction, pending] = useActionState<CourseState, FormData>(createCourse, {});
  return (
    <form action={formAction} className="space-y-2">
      <div className="flex gap-2">
        <Input name="name" placeholder="New course name — e.g. B2B, DSA, System Design…" className="max-w-md" />
        <Button type="submit" disabled={pending}>
          <Plus className="size-4" /> {pending ? "Adding…" : "Add course"}
        </Button>
      </div>
      {state.error && <p className="text-destructive text-sm">{state.error}</p>}
      {state.ok && <p className="text-sm text-emerald-600">{state.ok}</p>}
    </form>
  );
}
