"use client";

import { useState } from "react";
import { useFormStatus } from "react-dom";
import { Sparkles } from "lucide-react";
import { approveFeedback, discardFeedback, reviseDraft } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/copy-button";

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

/** One editable text (the send-summary OR the detailed feedback) with its own AI-revise agent. */
function EditBlock({
  classId,
  kind,
  fieldName,
  text,
  setText,
  rows,
  placeholder,
}: {
  classId: string;
  kind: "feedback" | "summary";
  fieldName: string;
  text: string;
  setText: (v: string) => void;
  rows: number;
  placeholder: string;
}) {
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revised, setRevised] = useState(false);

  async function onRevise() {
    if (!instruction.trim() || revising) return;
    setRevising(true);
    setError(null);
    const r = await reviseDraft(classId, instruction, text, kind);
    if (r.error) setError(r.error);
    else if (r.text) {
      setText(r.text);
      setInstruction("");
      setRevised(true);
    }
    setRevising(false);
  }

  return (
    <div className="space-y-3">
      <textarea
        name={fieldName}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={rows}
        className="border-input focus-visible:ring-ring w-full rounded-md border bg-transparent p-3 text-sm leading-relaxed shadow-sm outline-none focus-visible:ring-2"
      />
      {revised && <p className="text-xs text-emerald-600">Revised ✓ — review it, then approve.</p>}
      <div className="bg-muted/40 space-y-2 rounded-lg border p-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="size-4" /> Tell the AI what to change
        </div>
        <div className="flex gap-2">
          <Input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); onRevise(); }
            }}
            placeholder={placeholder}
          />
          <Button type="button" variant="secondary" onClick={onRevise} disabled={revising || !instruction.trim()}>
            {revising ? "Revising…" : "Revise"}
          </Button>
        </div>
        {error && <p className="text-destructive text-sm">{error}</p>}
      </div>
    </div>
  );
}

export function ReviewActions({
  classId,
  summaryInitial,
  feedbackInitial,
  done,
}: {
  classId: string;
  summaryInitial: string;
  feedbackInitial: string;
  done: boolean;
}) {
  const [summary, setSummary] = useState(summaryInitial);
  const [feedback, setFeedback] = useState(feedbackInitial);

  if (done) {
    return (
      <div className="space-y-6">
        {summaryInitial && (
          <div>
            <div className="mb-1.5 flex items-center gap-2">
              <span className="text-sm font-medium">Summary sent to the instructor</span>
              <Badge variant="success">Sent</Badge>
              <CopyButton text={summaryInitial} />
            </div>
            <div className="text-sm leading-relaxed whitespace-pre-wrap">{summaryInitial}</div>
          </div>
        )}
        <div>
          <div className="text-muted-foreground mb-1.5 text-sm font-medium">Detailed feedback (internal)</div>
          <div className="text-sm leading-relaxed whitespace-pre-wrap">{feedbackInitial}</div>
        </div>
      </div>
    );
  }

  return (
    <form className="space-y-7">
      <input type="hidden" name="class_id" value={classId} />

      {/* 1) The short note the instructor actually receives */}
      <section className="space-y-2 rounded-lg border border-emerald-300/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            Summary to send to the instructor <Badge variant="success">Send this</Badge>
          </div>
          <CopyButton text={summary} />
        </div>
        <p className="text-muted-foreground text-xs">
          A short, ready-to-send note — states the class rating. Edit it, or ask the AI to rewrite it, then approve.
        </p>
        <EditBlock
          classId={classId} kind="summary" fieldName="summary_edited" text={summary} setText={setSummary}
          rows={6} placeholder='e.g. "warmer tone", "mention the coding part", "shorter"'
        />
      </section>

      {/* 2) The detailed, timestamped analysis kept for the internal team */}
      <section className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          Detailed feedback <Badge variant="outline">internal team</Badge>
        </div>
        <p className="text-muted-foreground text-xs">
          The full timestamped coaching notes — for the team, not sent to the instructor.
        </p>
        <EditBlock
          classId={classId} kind="feedback" fieldName="edited_text" text={feedback} setText={setFeedback}
          rows={12} placeholder='e.g. "focus on the skipped problems", "softer tone"'
        />
      </section>

      <p className="text-muted-foreground text-xs">
        Approving stores both versions (the originals are kept for comparison).
      </p>
      <Buttons />
    </form>
  );
}
