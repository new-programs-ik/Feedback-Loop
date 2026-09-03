import * as React from "react";
import { cn } from "@/lib/utils";

/** Every page opens with this: a restrained h1 (products don't shout their own name),
 *  an optional one-line description, actions on the right (they drop below on narrow screens).
 *  `kicker` is the small uppercase line above the title for editorial pages. */
export function PageHeader({
  title,
  description,
  kicker,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  kicker?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-3", className)}>
      <div className="min-w-0">
        {kicker && (
          <div className="text-primary mb-1 text-[10.5px] font-bold tracking-[0.14em] uppercase">{kicker}</div>
        )}
        <h1 className="text-lg font-semibold tracking-[-0.01em]">{title}</h1>
        {description && <p className="text-muted-foreground mt-0.5 text-[13px]">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
