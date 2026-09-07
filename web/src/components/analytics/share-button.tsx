"use client";

import * as React from "react";
import { Check, Copy, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createShareLink } from "@/app/(app)/admin/actions";
import type { ReportPeriod } from "@/lib/analytics";

const KIND: Record<ReportPeriod, "weekly" | "monthly" | "custom"> = { week: "weekly", month: "monthly", custom: "custom" };

/** "Share" — creates a read-only report link (token, 30-day expiry, revocable from the admin
 *  People page) through C3's `createShareLink` action and shows it with a copy button. */
export function ShareButton({
  courseId,
  period,
  expiresInDays = 30,
}: {
  courseId: string | null;
  period: { kind: ReportPeriod; from: string; to: string; label?: string };
  expiresInDays?: number;
}) {
  const [pending, start] = React.useTransition();
  const [url, setUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const share = () =>
    start(async () => {
      setError(null);
      try {
        const r = await createShareLink({ courseId, period: { kind: KIND[period.kind], from: period.from, to: period.to, label: period.label }, expiresInDays });
        if (!r.ok) setError(r.error);
        else setUrl(`${window.location.origin}${r.data.path}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not create a link.");
      }
    });

  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the link is selectable on screen */
    }
  };

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" data-print-hide>
      <Button variant="outline" size="sm" onClick={share} isLoading={pending}>
        <Link2 aria-hidden /> Share
      </Button>
      {url && (
        <>
          <span className="text-muted-foreground max-w-[14rem] truncate font-mono text-[11px]" title={url}>
            {url}
          </span>
          <Button variant="ghost" size="sm" onClick={copy} aria-label="Copy link">
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </>
      )}
      {error && <span className="text-destructive text-[11px]">{error}</span>}
    </span>
  );
}
