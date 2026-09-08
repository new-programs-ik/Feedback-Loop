"use client";

import * as React from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { confirmRating, dismissRating, escalateRating } from "@/app/(app)/c/[course]/queue/actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableCell } from "@/components/ui/table";
import { EASE_OUT } from "@/components/motion/reveal";
import { cn } from "@/lib/utils";

export type ReviewStatus = "new" | "notified" | "confirmed";

const STATUS: Record<ReviewStatus, { label: string; variant: "secondary" | "outline" | "success" }> = {
  new: { label: "new", variant: "secondary" },
  notified: { label: "handler pinged", variant: "outline" },
  confirmed: { label: "confirmed", variant: "success" },
};

/** Review status as a chip. Re-keyed on change, so the flip to "confirmed" is a small enter
 *  rather than a hard swap. */
export function StatusBadge({ s }: { s: ReviewStatus }) {
  const reduce = useReducedMotion();
  const m = STATUS[s];
  return (
    <AnimatePresence initial={false} mode="wait">
      <motion.span
        key={s}
        className="inline-flex"
        initial={reduce ? false : { opacity: 0, y: 3 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduce ? undefined : { opacity: 0, y: -3 }}
        transition={{ duration: 0.16 }}
      >
        <Badge variant={m.variant}>{m.label}</Badge>
      </motion.span>
    </AnimatePresence>
  );
}

/** Production strips the message off an error thrown by a Server Action; keep the real text
 *  when we have it, otherwise say something the PM can act on. */
export function friendlyError(e: unknown) {
  const m = e instanceof Error ? e.message : String(e);
  return /server components render|server action|digest|unexpected response|failed to fetch/i.test(m)
    ? "The server could not complete that — refresh and try again."
    : m;
}

/** The row itself: a motion <tr> that can fade out (optimistic removal), and — for the `?focus=`
 *  row — scrolls into view and tints once. The tint is a CSS variable motion drives from
 *  0 → 1 → rest, mixed with the primary token, so it is right in both themes. */
function RowShell({
  id,
  gone,
  focus,
  children,
}: {
  id: string;
  gone: boolean;
  focus: boolean;
  children: React.ReactNode;
}) {
  const reduce = useReducedMotion();
  const ref = React.useRef<HTMLTableRowElement>(null);

  React.useEffect(() => {
    if (!focus || !ref.current) return;
    ref.current.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  }, [focus, reduce]);

  return (
    <AnimatePresence initial={false}>
      {!gone && (
        <motion.tr
          key={id}
          ref={ref}
          data-slot="table-row"
          className="group border-b align-top hover:bg-muted/40"
          style={
            focus
              ? { backgroundColor: "color-mix(in oklch, var(--primary) calc(var(--glow, 0) * 22%), transparent)" }
              : undefined
          }
          initial={false}
          animate={{ opacity: 1, x: 0, ...(focus ? { "--glow": reduce ? 0.3 : [0, 1, 0.3] } : {}) }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, x: -12 }}
          transition={{
            opacity: { duration: 0.18 },
            x: { duration: 0.18, ease: EASE_OUT },
            "--glow": { duration: 1.4, times: [0, 0.35, 1], ease: "easeOut", delay: 0.25 },
          }}
        >
          {children}
        </motion.tr>
      )}
    </AnimatePresence>
  );
}

const ACTIONS =
  "flex items-center justify-end gap-1 transition-opacity opacity-70 group-hover:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100";

type Kind = "confirm" | "dismiss" | "escalate";

/** One queue row. The leading cells are rendered on the server and passed as children; this
 *  component owns the two that react: the status (flips optimistically) and the actions —
 *  Analyze · Confirm · Dismiss · Escalate. Dismiss fades the row out at once; Confirm flips the
 *  chip — confirmed rows STAY in the queue (that is the point of confirming). */
export function QueueRow({
  id,
  status,
  focus,
  analyzeHref,
  escalated = false,
  children,
}: {
  id: string;
  status: ReviewStatus;
  focus: boolean;
  analyzeHref: string;
  escalated?: boolean;
  children: React.ReactNode;
}) {
  const [pending, startTransition] = React.useTransition();
  const [busy, setBusy] = React.useState<Kind | null>(null);
  const [view, setView] = React.useOptimistic<{ gone: boolean; status: ReviewStatus; escalated: boolean }>({
    gone: false,
    status,
    escalated,
  });

  const run = (kind: Kind) => {
    const fd = new FormData();
    fd.set("id", id);
    setBusy(kind);
    startTransition(async () => {
      setView(
        kind === "dismiss"
          ? { gone: true, status, escalated }
          : kind === "confirm"
            ? { gone: false, status: "confirmed", escalated }
            : { gone: false, status: "new", escalated: true },
      );
      try {
        if (kind === "dismiss") await dismissRating(fd);
        else if (kind === "confirm") await confirmRating(fd);
        else await escalateRating(fd);
        toast.success(kind === "dismiss" ? "Dismissed" : kind === "confirm" ? "Confirmed" : "Escalated to video", {
          description:
            kind === "dismiss"
              ? "No analysis for this class — the hourly sync won't re-flag it."
              : kind === "confirm"
                ? "Marked for analysis — hit Analyze when you're ready."
                : "It moves to the video section, whatever the numbers say.",
        });
      } catch (e) {
        toast.error(
          kind === "dismiss" ? "Couldn't dismiss" : kind === "confirm" ? "Couldn't confirm" : "Couldn't escalate",
          { description: friendlyError(e) },
        );
      } finally {
        setBusy(null);
      }
    });
  };

  return (
    <RowShell id={id} gone={view.gone} focus={focus}>
      {children}
      <TableCell className="whitespace-nowrap">
        <StatusBadge s={view.status} />
      </TableCell>
      <TableCell>
        <div className={cn(ACTIONS, busy && "opacity-100")}>
          <Button asChild size="sm">
            <Link href={analyzeHref}>Analyze</Link>
          </Button>
          {view.status !== "confirmed" && (
            <Button variant="outline" size="sm" type="button" disabled={pending} aria-busy={busy === "confirm"} onClick={() => run("confirm")}>
              {busy === "confirm" && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
              Confirm
            </Button>
          )}
          <Button variant="ghost" size="sm" type="button" disabled={pending} aria-busy={busy === "dismiss"} onClick={() => run("dismiss")}>
            {busy === "dismiss" && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
            Dismiss
          </Button>
          {!view.escalated && (
            <Button variant="ghost" size="sm" type="button" disabled={pending} aria-busy={busy === "escalate"} onClick={() => run("escalate")} className="text-muted-foreground">
              {busy === "escalate" && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
              Escalate
            </Button>
          )}
        </div>
      </TableCell>
    </RowShell>
  );
}

/** Watch-list row: Escalate → video. The row fades out at once; after the server revalidates
 *  it reappears in the video section. */
export function WatchRow({ id, focus = false, children }: { id: string; focus?: boolean; children: React.ReactNode }) {
  const [pending, startTransition] = React.useTransition();
  const [gone, setGone] = React.useOptimistic(false);

  const run = () => {
    const fd = new FormData();
    fd.set("id", id);
    startTransition(async () => {
      setGone(true);
      try {
        await escalateRating(fd);
        toast.success("Escalated to video", {
          description: "It's now in the video section, whatever the numbers say.",
        });
      } catch (e) {
        toast.error("Couldn't escalate", { description: friendlyError(e) });
      }
    });
  };

  return (
    <RowShell id={id} gone={gone} focus={focus}>
      {children}
      <TableCell className="text-right">
        <Button
          variant="outline"
          size="sm"
          type="button"
          disabled={pending}
          aria-busy={pending}
          onClick={run}
          className={cn("transition-opacity", pending ? "opacity-100 disabled:opacity-100" : "opacity-70 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100")}
        >
          {pending && <Loader2 className="size-3.5 animate-spin" aria-hidden />}
          Escalate → video
        </Button>
      </TableCell>
    </RowShell>
  );
}
