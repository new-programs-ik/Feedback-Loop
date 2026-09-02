"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Left drawer built on the native <dialog> element — focus trap, Esc-to-close and backdrop
 *  come from the platform. Used for the mobile navigation. */
function Sheet({
  open,
  onClose,
  ariaLabel,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  ariaLabel: string;
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

  return (
    <dialog
      ref={ref}
      aria-label={ariaLabel}
      onClose={onClose}
      onClick={(e) => {
        // A click on the backdrop lands on the <dialog> itself, not its children.
        if (e.target === ref.current) onClose();
      }}
      className={cn(
        "bg-sidebar text-sidebar-foreground m-0 h-dvh max-h-none w-72 max-w-[85vw] border-r p-0",
        "backdrop:bg-black/50",
        "open:animate-in-up motion-reduce:open:animate-none",
        className,
      )}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-end p-2">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="hover:bg-sidebar-accent flex size-9 cursor-pointer items-center justify-center rounded-lg"
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
