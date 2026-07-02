"use client";

import { useFormStatus } from "react-dom";
import { approveFeedback, discardFeedback } from "../actions";
import { Button } from "@/components/ui/button";

function Buttons() {
  const { pending } = useFormStatus();
  return (
    <div className="flex gap-3">
      <Button type="submit" formAction={approveFeedback} disabled={pending}>
        {pending ? "Saving…" : "Approve & store"}
      </Button>
      <Button
        type="submit"
        formAction={discardFeedback}
        variant="outline"
        disabled={pending}
        onClick={(e) => {
          if (!confirm("Discard this feedback? The class will be marked no-action.")) e.preventDefault();
        }}
      >
        Discard
      </Button>
    </div>
  );
}

export function ReviewActions({
  classId,
  initialText,
  done,
}: {
  classId: string;
  initialText: string;
  done: boolean;
}) {
  if (done) {
    return <div className="whitespace-pre-wrap text-sm leading-relaxed">{initialText}</div>;
  }
  return (
    <form className="space-y-3">
      <input type="hidden" name="class_id" value={classId} />
      <textarea
        name="edited_text"
        defaultValue={initialText}
        rows={12}
        className="border-input focus-visible:ring-ring w-full rounded-md border bg-transparent p-3 text-sm leading-relaxed shadow-sm outline-none focus-visible:ring-2"
      />
      <p className="text-muted-foreground text-xs">
        Edit the draft as needed. Approving stores your version and keeps the original for comparison.
      </p>
      <Buttons />
    </form>
  );
}
