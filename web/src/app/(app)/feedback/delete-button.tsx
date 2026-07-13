"use client";

import { Trash2 } from "lucide-react";
import { deleteClass } from "./actions";
import { Button } from "@/components/ui/button";

export function DeleteButton({ classId, withLabel = false }: { classId: string; withLabel?: boolean }) {
  return (
    <form
      action={deleteClass}
      onSubmit={(e) => {
        if (!confirm("Delete this analysis permanently? This can't be undone.")) e.preventDefault();
      }}
    >
      <input type="hidden" name="class_id" value={classId} />
      <Button
        type="submit"
        variant={withLabel ? "outline" : "ghost"}
        size={withLabel ? "sm" : "icon"}
        title="Delete"
        className="text-muted-foreground hover:text-destructive"
      >
        <Trash2 className="size-4" />
        {withLabel && "Delete"}
      </Button>
    </form>
  );
}
