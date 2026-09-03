"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Check, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { approveFeedback, discardFeedback, reviseDraft } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "@/components/copy-button";
import { cn } from "@/lib/utils";

/** approve/discard end in redirect("/feedback"); from a client transition that arrives as a
 *  rejected promise with a NEXT_REDIRECT digest — the navigation is already under way. */
function isRedirect(e: unknown) {
  const digest = (e as { digest?: unknown } | null)?.digest;
  return typeof digest === "string" && digest.startsWith("NEXT_REDIRECT");
}
function friendlyError(e: unknown) {
  const m = e instanceof Error ? e.message : String(e);
  return /server components render|server action|digest|unexpected response|failed to fetch/i.test(m)
    ? "The server could not complete that — refresh and try again."
    : m;
}

function Buttons({ formRef }: { formRef: React.RefObject<HTMLFormElement | null> }) {
  const [pending, startTransition] = React.useTransition();
  const [which, setWhich] = React.useState<"approve" | "discard" | null>(null);

  const submit = (kind: "approve" | "discard") => {
    const form = formRef.current;
    if (!form) return;
    if (kind === "discard" && !confirm("Discard this feedback? The class will be marked no-action.")) return;
    // Same field names the server actions already read — the contract is unchanged.
    const fd = new FormData(form);
    setWhich(kind);
    startTransition(async () => {
      const ok =
        kind === "approve"
          ? { title: "Approved & stored", description: "Both versions are saved — the summary is ready to send." }
          : { title: "Draft discarded", description: "The class is marked no-action; nothing was sent." };
      try {
        if (kind === "approve") await approveFeedback(fd);
        else await discardFeedback(fd);
        toast.success(ok.title, { description: ok.description });
      } catch (e) {
        if (isRedirect(e)) {
          toast.success(ok.title, { description: ok.description });
          return;
        }
        toast.error(kind === "approve" ? "Couldn't approve" : "Couldn't discard", { description: friendlyError(e) });
      } finally {
        setWhich(null);
      }
    });
  };

  return (
    <div className="flex gap-3">
      <Button type="button" onClick={() => submit("approve")} disabled={pending} aria-busy={which === "approve"} className="min-w-36">
        {which === "approve" ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden /> Saving…
          </>
        ) : (
          "Approve & store"
        )}
      </Button>
      <Button type="button" variant="outline" onClick={() => submit("discard")} disabled={pending} aria-busy={which === "discard"}>
        {which === "discard" && <Loader2 className="size-4 animate-spin" aria-hidden />}
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
  const reduce = useReducedMotion();
  const [instruction, setInstruction] = React.useState("");
  const [revising, setRevising] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [revised, setRevised] = React.useState(false);

  async function onRevise() {
    if (!instruction.trim() || revising) return;
    setRevising(true);
    setError(null);
    const r = await reviseDraft(classId, instruction, text, kind);
    if (r.error) {
      setError(r.error);
      toast.error("Revision didn't go through", { description: r.error });
    } else if (r.text) {
      setText(r.text);
      setInstruction("");
      setRevised(true);
      toast.success("Draft revised", { description: "Read it over, then approve." });
    }
    setRevising(false);
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <textarea
          name={fieldName}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={rows}
          aria-busy={revising}
          readOnly={revising}
          className={cn(
            "border-input focus-visible:ring-ring w-full rounded-md border bg-transparent p-3 text-sm leading-relaxed shadow-sm outline-none transition-opacity focus-visible:ring-2",
            revising && "opacity-60",
          )}
        />
        <AnimatePresence>
          {revising && (
            <motion.div
              aria-hidden
              className="shimmer pointer-events-none absolute inset-0 rounded-md opacity-40"
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            />
          )}
        </AnimatePresence>
      </div>
      <div className="min-h-4">
        <AnimatePresence>
          {revised && (
            <motion.p
              className="text-success flex items-center gap-1 text-xs"
              initial={reduce ? false : { opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <Check className="size-3.5" aria-hidden /> Revised — review it, then approve.
            </motion.p>
          )}
        </AnimatePresence>
      </div>
      <div className="bg-muted/40 space-y-2 rounded-lg border p-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className={cn("size-4", revising && "text-primary")} aria-hidden /> Tell the AI what to change
        </div>
        <div className="flex gap-2">
          <Input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); onRevise(); }
            }}
            placeholder={placeholder}
            disabled={revising}
          />
          <Button
            type="button"
            variant="secondary"
            onClick={onRevise}
            disabled={revising || !instruction.trim()}
            aria-busy={revising}
            className="min-w-24"
          >
            {revising ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden /> Revising…
              </>
            ) : (
              "Revise"
            )}
          </Button>
        </div>
        {revising && (
          <p className="text-muted-foreground text-xs" aria-live="polite">
            Rewriting with your note — usually 10–20 seconds.
          </p>
        )}
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
  const formRef = React.useRef<HTMLFormElement>(null);
  const [summary, setSummary] = React.useState(summaryInitial);
  const [feedback, setFeedback] = React.useState(feedbackInitial);

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
    <form ref={formRef} className="space-y-7" onSubmit={(e) => e.preventDefault()}>
      <input type="hidden" name="class_id" value={classId} />

      {/* 1) The short note the instructor actually receives */}
      <section className="border-success/40 space-y-2 rounded-lg border p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            Summary to send to the instructor <Badge variant="success">Send this</Badge>
          </div>
          <CopyButton text={summary} />
        </div>
        <p className="text-muted-foreground text-xs">
          A short, ready-to-send note: the class rating, then up to 4–5 bullets — each one problem and its fix,
          in plain words (timestamps stay in the internal version below). Edit it, or ask the AI to rewrite it, then approve.
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
      <Buttons formRef={formRef} />
    </form>
  );
}
