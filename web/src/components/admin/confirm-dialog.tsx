"use client";

import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** A modal built on the native <dialog>: focus trap, Esc and backdrop come from the platform.
 *  `children` is the body (a summary, a form); the footer holds cancel + the one confirming
 *  action. Nothing animates beyond the platform fade — this is a decision, not a flourish. */
export function ConfirmDialog({
  open,
  title,
  description,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  disabled = false,
  onConfirm,
  onClose,
  className,
}: {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  disabled?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  className?: string;
}) {
  const ref = React.useRef<HTMLDialogElement>(null);
  const titleId = React.useId();

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        if (busy) e.preventDefault();
      }}
      onClick={(e) => {
        if (e.target === ref.current && !busy) onClose();
      }}
      className={cn(
        "bg-card text-card-foreground shadow-pop m-auto w-[min(92vw,34rem)] rounded-xl border p-0",
        "backdrop:bg-black/45",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="min-w-0">
          <h2 id={titleId} className="text-[15px] font-semibold tracking-[-0.01em]">
            {title}
          </h2>
          {description && <div className="text-muted-foreground mt-0.5 text-[12.5px]">{description}</div>}
        </div>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close"
          className="hover:bg-accent flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>
      {children && <div className="px-5 py-4">{children}</div>}
      <div className="flex items-center justify-end gap-2 border-t px-5 py-3">
        <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button
          type="button"
          variant={destructive ? "destructive" : "default"}
          onClick={onConfirm}
          isLoading={busy}
          disabled={disabled}
        >
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
