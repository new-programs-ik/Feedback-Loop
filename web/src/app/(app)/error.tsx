"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { Mail, RefreshCw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EASE_OUT } from "@/components/motion/reveal";

/** Where a bug report goes. Overridable per environment; defaults to the New Programs inbox. */
const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "new-programs@interviewkickstart.com";

/** The location never changes while an error card is showing; nothing to subscribe to. */
const subscribeNoop = () => () => {};

/** Route-group error boundary — the app previously had none, so any render error white-screened
 *  the whole shell. Now: a calm card that names the problem, keeps the digest for matching server
 *  logs, and offers the two things a person can do — try again, or tell us. */
export default function AppError({
  error,
  reset,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  /** Next 16: re-fetches and re-renders the segment (preferred over `reset`, which only clears). */
  unstable_retry?: () => void;
}) {
  const reduce = useReducedMotion();
  // The page URL is only known in the browser; the server snapshot is empty so both renders agree.
  const page = React.useSyncExternalStore(
    subscribeNoop,
    () => window.location.href,
    () => "",
  );

  React.useEffect(() => {
    console.error(error);
  }, [error]);

  const retry = unstable_retry ?? reset;
  const subject = encodeURIComponent(`Feedback Loop error${error.digest ? ` · ${error.digest}` : ""}`);
  const body = encodeURIComponent(
    [
      `Page: ${page}`,
      `When: ${new Date().toISOString()}`,
      `Digest: ${error.digest ?? "—"}`,
      `Message: ${error.message}`,
      "",
      "What I was doing:",
      "",
    ].join("\n"),
  );

  return (
    <motion.div
      role="alert"
      className="bg-card shadow-soft mx-auto mt-10 max-w-lg overflow-hidden rounded-xl border"
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: EASE_OUT }}
    >
      <div className="bg-destructive/6 dark:bg-destructive/10 flex items-center gap-3 border-b px-5 py-4">
        <motion.span
          className="bg-destructive/12 text-destructive flex size-9 shrink-0 items-center justify-center rounded-lg"
          initial={reduce ? false : { scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 420, damping: 24, delay: 0.1 }}
        >
          <TriangleAlert className="size-4.5" aria-hidden />
        </motion.span>
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-[-0.01em]">Something went wrong</h2>
          <p className="text-muted-foreground text-[12.5px]">This page hit an unexpected error. Your data is safe.</p>
        </div>
      </div>

      <div className="px-5 py-4">
        <p className="text-muted-foreground text-[13px] leading-relaxed">
          Trying again usually clears it — the page re-fetches everything. If it keeps happening, send a
          report; the reference below is attached so we can find it in the logs.
        </p>
        {error.digest && (
          <p className="text-muted-foreground mt-3 text-[11px]">
            Reference{" "}
            <code className="bg-muted text-foreground rounded px-1.5 py-0.5 font-mono text-[11px]">{error.digest}</code>
          </p>
        )}
        {process.env.NODE_ENV !== "production" && error.message && (
          <details className="mt-3">
            <summary className="text-muted-foreground hover:text-foreground cursor-pointer text-[11px] font-medium select-none">
              Error detail (dev only)
            </summary>
            <pre className="bg-muted mt-2 max-h-40 overflow-auto rounded-md p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
              {error.message}
            </pre>
          </details>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="gradient" onClick={() => retry()}>
            <RefreshCw aria-hidden /> Try again
          </Button>
          <Button asChild variant="outline">
            <a href={`mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`}>
              <Mail aria-hidden /> Report
            </a>
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
