"use client";

import * as React from "react";
import { useActionState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { createCourse, type CourseState } from "./actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function AddCourseForm() {
  const [state, formAction, pending] = useActionState<CourseState, FormData>(createCourse, {});

  // The outcome arrives as new state; surface it as a toast (the inline line stays for the
  // error case so the message sits beside the field that caused it).
  React.useEffect(() => {
    if (state.ok) toast.success(state.ok, { description: "It's available in New analysis right away." });
    if (state.error) toast.error(state.error);
  }, [state]);

  return (
    <form action={formAction} className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Input
          name="name"
          placeholder="New course name — e.g. B2B, DSA, System Design…"
          className="max-w-md flex-1"
          aria-invalid={state.error ? true : undefined}
          required
        />
        <Button type="submit" isLoading={pending}>
          <Plus aria-hidden /> {pending ? "Adding…" : "Add course"}
        </Button>
      </div>
      {state.error && (
        <p className="text-destructive text-[13px]" role="alert">
          {state.error}
        </p>
      )}
    </form>
  );
}
