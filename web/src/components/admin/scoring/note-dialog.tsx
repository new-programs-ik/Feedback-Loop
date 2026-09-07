"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { fieldClasses } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { ConfirmDialog } from "../confirm-dialog";
import { fmt1, fmtPct, type PreviewStats } from "./preview-math";

/** The one dialog behind Publish, Roll back and Propose: a name (when asked for), a note that
 *  goes into the audit trail, and the four-number summary of what the preview range would do.
 *  The confirm button stays disabled until the note says something. */
export function NoteDialog({
  open,
  title,
  description,
  confirmLabel,
  requireName = false,
  initialName = "",
  initialNote = "",
  summary,
  rangeLabel,
  busy,
  destructive = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel: string;
  requireName?: boolean;
  initialName?: string;
  initialNote?: string;
  summary?: PreviewStats | null;
  rangeLabel?: string;
  busy: boolean;
  destructive?: boolean;
  onConfirm: (v: { name: string; note: string }) => void;
  onClose: () => void;
}) {
  const [name, setName] = React.useState(initialName);
  const [note, setNote] = React.useState(initialNote);
  const [seed, setSeed] = React.useState({ initialName, initialNote, open });
  // Re-seed the fields each time the dialog opens (state adjusted during render, no effect).
  if (seed.open !== open || seed.initialName !== initialName || seed.initialNote !== initialNote) {
    setSeed({ initialName, initialNote, open });
    if (open) {
      setName(initialName);
      setNote(initialNote);
    }
  }
  const ready = note.trim().length >= 3 && (!requireName || name.trim().length > 0);

  return (
    <ConfirmDialog
      open={open}
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      busy={busy}
      disabled={!ready}
      destructive={destructive}
      onConfirm={() => onConfirm({ name: name.trim(), note: note.trim() })}
      onClose={onClose}
    >
      <div className="space-y-3">
        {summary && (
          <div className="surface-inset grid grid-cols-2 gap-2 rounded-lg border p-3 text-[12px] sm:grid-cols-4">
            <Stat label="Change band" value={String(summary.bandMoves)} />
            <Stat label="Analyses / week" value={`${fmt1(summary.analysesPerWeek)}`} sub={`${fmt1(summary.videosPerWeek)} v · ${fmt1(summary.transcriptsPerWeek)} t`} />
            <Stat label="Dropped today" value={String(summary.dropped)} />
            <Stat label="Flip on one vote" value={fmtPct(summary.flipShare)} />
            {rangeLabel && <p className="text-muted-foreground col-span-full text-[11px]">Over {rangeLabel}.</p>}
          </div>
        )}
        {requireName && (
          <label className="block space-y-1">
            <span className="text-muted-foreground block text-[11.5px] font-medium">Name</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="e.g. Two lines + graded, guard k=5" disabled={busy} />
          </label>
        )}
        <label className="block space-y-1">
          <span className="text-muted-foreground block text-[11.5px] font-medium">Note — why (goes into the audit trail)</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            rows={3}
            disabled={busy}
            placeholder="What changed and what the preview showed."
            className={cn(fieldClasses, "placeholder:text-muted-foreground h-auto w-full resize-y px-3 py-2")}
          />
        </label>
      </div>
    </ConfirmDialog>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-muted-foreground text-[10.5px] font-medium">{label}</div>
      <div data-numeric className="text-[17px] leading-tight font-semibold tracking-[-0.01em]">{value}</div>
      {sub && <div className="text-muted-foreground truncate text-[10.5px]">{sub}</div>}
    </div>
  );
}
