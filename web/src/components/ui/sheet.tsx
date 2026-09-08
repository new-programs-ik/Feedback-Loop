"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** A drawer built on the native <dialog> element — focus trap, Esc-to-close and backdrop come
 *  from the platform. `side="left"` is the mobile navigation; `side="right"` is the class drawer
 *  (the one slide the product keeps: it says "this opens over the table you were reading"). */
function Sheet({
  open,
  onClose,
  ariaLabel,
  side = "left",
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  ariaLabel: string;
  side?: "left" | "right";
  /** Right drawers show a header with the title and the close button. */
  title?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  const right = side === "right";
  return (
    <dialog
      ref={ref}
      aria-label={ariaLabel}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        // A click on the backdrop lands on the <dialog> itself, not its children.
        if (e.target === ref.current) onClose();
      }}
      className={cn(
        "m-0 h-dvh max-h-none p-0 backdrop:bg-black/40 motion-reduce:open:animate-none",
        right
          ? "bg-card text-card-foreground ml-auto w-[min(100vw,36rem)] border-l open:animate-in-right"
          : "bg-sidebar text-sidebar-foreground mr-auto w-72 max-w-[85vw] border-r open:animate-in-left",
        className,
      )}
    >
      <div className="flex h-full flex-col">
        <div className={cn("flex items-center gap-3 px-2 py-2", right && "border-b px-5 py-3")}>
          {right && <div className="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-[-0.01em]">{title ?? ariaLabel}</div>}
          <button
            type="button"
            onClick={onClose}
            aria-label={right ? "Close" : "Close menu"}
            className={cn(
              "flex size-9 cursor-pointer items-center justify-center rounded-lg",
              right ? "hover:bg-accent text-muted-foreground hover:text-foreground" : "hover:bg-sidebar-accent ml-auto",
            )}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </dialog>
  );
}

export { Sheet };
