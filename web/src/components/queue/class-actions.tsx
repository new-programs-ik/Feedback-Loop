"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, MessageSquareText } from "lucide-react";
import { toast } from "sonner";
import { confirmRating, dismissRating, escalateRating } from "@/app/(app)/c/[course]/queue/actions";
import { Button } from "@/components/ui/button";
import { friendlyError } from "@/components/queue/queue-row";
import type { ReviewStatus } from "@/lib/ratings";

type Kind = "confirm" | "dismiss" | "escalate";

/** The class drawer's actions: Analyze · Confirm · Dismiss · Escalate, on the same server
 *  actions as the queue; the page refreshes so the status and the score history follow. */
export function ClassActions({
  id,
  status,
  escalated,
  analyzeHref,
  analysisHref,
}: {
  id: string;
  status: ReviewStatus;
  escalated: boolean;
  analyzeHref: string;
  /** Set when an AI analysis already exists for this class. */
  analysisHref?: string | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [busy, setBusy] = React.useState<Kind | null>(null);

  const run = (kind: Kind) => {
    const fd = new FormData();
    fd.set("id", id);
    setBusy(kind);
    startTransition(async () => {
      try {
        if (kind === "dismiss") await dismissRating(fd);
        else if (kind === "confirm") await confirmRating(fd);
        else await escalateRating(fd);
        toast.success(kind === "dismiss" ? "Dismissed" : kind === "confirm" ? "Confirmed" : "Escalated to video");
        router.refresh();
      } catch (e) {
        toast.error("That did not go through", { description: friendlyError(e) });
      } finally {
        setBusy(null);
      }
    });
  };

  const canConfirm = status === "new" || status === "notified";
  const canDismiss = status !== "dismissed" && status !== "analysis_started";

  return (
    <div className="flex flex-wrap items-center gap-1.5" data-print-hide>
      {analysisHref ? (
        <Button asChild size="sm">
          <Link href={analysisHref}>
            <MessageSquareText aria-hidden /> Open analysis
          </Link>
        </Button>
      ) : (
        <Button asChild size="sm">
          <Link href={analyzeHref}>Analyze</Link>
        </Button>
      )}
      {canConfirm && (
        <Button variant="outline" size="sm" type="button" disabled={pending} onClick={() => run("confirm")}>
          {busy === "confirm" && <Loader2 className="size-3.5 animate-spin" aria-hidden />} Confirm
        </Button>
      )}
      {canDismiss && (
        <Button variant="ghost" size="sm" type="button" disabled={pending} onClick={() => run("dismiss")}>
          {busy === "dismiss" && <Loader2 className="size-3.5 animate-spin" aria-hidden />} Dismiss
        </Button>
      )}
      {!escalated && (
        <Button variant="ghost" size="sm" type="button" disabled={pending} onClick={() => run("escalate")} className="text-muted-foreground">
          {busy === "escalate" && <Loader2 className="size-3.5 animate-spin" aria-hidden />} Escalate → video
        </Button>
      )}
    </div>
  );
}
