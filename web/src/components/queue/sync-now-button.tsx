"use client";

import * as React from "react";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { requestSync } from "@/app/(app)/ratings/actions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** "Sync now" with a spinning icon while the worker is asked, and a toast either way — the
 *  worker's "I'm waking up" reason comes back as data so it reads the same in production. */
export function SyncNowButton() {
  const [pending, startTransition] = React.useTransition();
  const run = () =>
    startTransition(async () => {
      const r = await requestSync();
      if (r.ok) {
        toast.success("Sync requested", {
          description: "The ratings sheet is being read now — the queue refreshes in a moment.",
        });
      } else {
        toast.error("Sync could not start", { description: r.error });
      }
    });
  return (
    <Button variant="outline" type="button" onClick={run} disabled={pending} aria-busy={pending} className="min-w-28">
      <RefreshCw className={cn("size-4", pending && "animate-spin")} aria-hidden />
      {pending ? "Syncing…" : "Sync now"}
    </Button>
  );
}
