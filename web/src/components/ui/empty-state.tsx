import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** The one empty-state pattern used everywhere: icon in a muted circle, a title that names
 *  what's missing, one helpful line, and (optionally) the action that fixes it. */
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
      className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}
    >
      <div className="bg-muted text-muted-foreground mb-3 flex size-11 items-center justify-center rounded-full">
        <Icon className="size-5" aria-hidden />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="text-muted-foreground mt-1 max-w-sm text-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export { EmptyState };
