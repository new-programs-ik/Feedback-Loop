import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { EmptyMotif } from "@/components/ui/empty-motif";
import { cn } from "@/lib/utils";

/** The one empty-state pattern used everywhere: a thin-line motif that draws itself in, the icon
 *  in a muted circle above the empty tray, a title that names what's missing, one helpful line,
 *  and (optionally) the action that fixes it. Server-safe — the motif is the only client island. */
function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-slot="empty-state"
      className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}
    >
      <div className="relative mb-2 h-28 w-40">
        <EmptyMotif className="absolute inset-0" />
        <div className="bg-muted text-muted-foreground absolute top-3 left-1/2 flex size-11 -translate-x-1/2 items-center justify-center rounded-full">
          <Icon className="size-5" aria-hidden />
        </div>
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="text-muted-foreground mt-1 max-w-sm text-sm leading-relaxed">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export { EmptyState };
