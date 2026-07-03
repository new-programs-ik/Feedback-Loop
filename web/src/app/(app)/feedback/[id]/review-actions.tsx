"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";
import { Sparkles } from "lucide-react";
import { approveFeedback, discardFeedback, reviseDraft } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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
  const [text, setText] = useState(initialText);
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revised, setRevised] = useState(false);

  if (done) {
    return <div className="whitespace-pre-wrap text-sm leading-relaxed">{initialText}</div>;
  }

  async function onRevise() {
    if (!instruction.trim() || revising) return;
    setRevising(true);
    setError(null);
    const r = await reviseDraft(classId, instruction, text);
    if (r.error) setError(r.error);
    else if (r.text) {
      setText(r.text);
      setInstruction("");
      setRevised(true);
    }
    setRevising(false);
  }

  return (
    <form className="space-y-4">
      <input type="hidden" name="class_id" value={classId} />
      <textarea
        name="edited_text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={12}
        className="border-input focus-visible:ring-ring w-full rounded-md border bg-transparent p-3 text-sm leading-relaxed shadow-sm outline-none focus-visible:ring-2"
      />
      {revised && <p className="text-xs text-emerald-600">Draft revised ✓ — review it, then approve.</p>}

      {/* Revise-with-AI: tell it what to change, it rewrites the draft right here */}
      <div className="bg-muted/40 space-y-2 rounded-lg border p-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="size-4" /> Not happy with the draft? Tell the AI what to change
        </div>
        <div className="flex gap-2">
          <Input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); onRevise(); }
            }}
            placeholder='e.g. "make it shorter", "softer tone", "focus on the skipped problems"'
          />
          <Button type="button" variant="secondary" onClick={onRevise} disabled={revising || !instruction.trim()}>
            {revising ? "Revising…" : "Revise"}
          </Button>
        </div>
        <p className="text-muted-foreground text-xs">
          The AI rewrites the draft above using your instruction — keep revising until it&apos;s right,
          then approve. It keeps timestamps and never invents new claims.
        </p>
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}

      <p className="text-muted-foreground text-xs">
        You can also edit the text directly. Approving stores your version and keeps the original for comparison.
      </p>
      <Buttons />
    </form>
  );
}
