"use client";

import * as React from "react";
import { Loader2, RefreshCcw, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { deleteClass, markAsSent, retryAnalysis } from "../actions";
import { Button } from "@/components/ui/button";

/** These actions end in redirect(). From a client transition Next surfaces that as a rejected
 *  promise carrying a NEXT_REDIRECT digest — the navigation is already happening, so it IS the
 *  success path. Anything else is a real failure (and production strips its message). */
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

type Msg = { ok: { title: string; description?: string }; fail: string };

function useServerAction() {
  const [pending, startTransition] = React.useTransition();
  const run = (fn: (fd: FormData) => Promise<void | { error?: string }>, fd: FormData, msg: Msg) =>
    startTransition(async () => {
      try {
        const result = await fn(fd);
        if (result && typeof result === "object" && result.error) {
          toast.error(msg.fail, { description: result.error });
          return;
        }
        toast.success(msg.ok.title, { description: msg.ok.description });
      } catch (e) {
        if (isRedirect(e)) {
          toast.success(msg.ok.title, { description: msg.ok.description });
          return;
        }
        toast.error(msg.fail, { description: friendlyError(e) });
      }
    });
  return { pending, run };
}

const withClass = (classId: string) => {
  const fd = new FormData();
  fd.set("class_id", classId);
  return fd;
};

export function MarkSentButton({ classId }: { classId: string }) {
  const { pending, run } = useServerAction();
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={pending}
      aria-busy={pending}
      onClick={() =>
        run(markAsSent, withClass(classId), {
          ok: { title: "Marked as sent", description: "Logged to the audit trail — the instructor has the summary." },
          fail: "Couldn't mark as sent",
        })
      }
    >
      {pending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Send className="size-3.5" aria-hidden />}
      Mark as sent
    </Button>
  );
}

export function RetryButton({ classId }: { classId: string }) {
  const { pending, run } = useServerAction();
  return (
    <Button
      type="button"
      disabled={pending}
      aria-busy={pending}
      onClick={() =>
        run(retryAnalysis, withClass(classId), {
          ok: { title: "Analysis restarted", description: "Re-fetching the transcript from Vimeo — this page updates on its own." },
          fail: "Couldn't restart the analysis",
        })
      }
    >
      <RefreshCcw className={pending ? "size-4 animate-spin" : "size-4"} aria-hidden />
      {pending ? "Restarting…" : "Retry analysis"}
    </Button>
  );
}

export function DeleteAnalysisButton({ classId }: { classId: string }) {
  const { pending, run } = useServerAction();
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      title="Delete"
      aria-label="Delete this analysis"
      disabled={pending}
      aria-busy={pending}
      className="text-muted-foreground hover:text-destructive"
      onClick={() => {
        if (!confirm("Delete this analysis permanently? This can't be undone.")) return;
        run(deleteClass, withClass(classId), {
          ok: { title: "Analysis deleted", description: "The class, its analysis and its drafts are gone." },
          fail: "Couldn't delete",
        });
      }}
    >
      {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Trash2 className="size-4" aria-hidden />}
    </Button>
  );
}
