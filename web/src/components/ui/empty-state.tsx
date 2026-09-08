import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** The one empty-state pattern used everywhere: a small icon, one sentence that names what is
 *  missing, and (optionally) the action that fixes it. No illustrations. */
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
    <div data-slot="empty-state" className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <div className="bg-muted text-muted-foreground mb-3 flex size-9 items-center justify-center rounded-full">
        <Icon className="size-4" aria-hidden />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="text-muted-foreground mt-1 max-w-sm text-sm leading-relaxed">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export { EmptyState };
