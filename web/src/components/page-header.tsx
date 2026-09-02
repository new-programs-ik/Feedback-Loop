import * as React from "react";
import { cn } from "@/lib/utils";

/** Every page opens with this: a restrained h1 (products don't shout their own name),
 *  an optional one-line description, actions on the right. */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-5 flex flex-wrap items-center justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-[-0.01em]">{title}</h1>
        {description && <p className="text-muted-foreground mt-0.5 text-[13px]">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
