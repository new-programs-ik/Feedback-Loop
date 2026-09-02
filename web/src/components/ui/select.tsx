import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/** Styled NATIVE <select> — keyboard, mobile pickers and form semantics for free.
 *  Matches Input's height/border/ring so mixed filter rows sit on one baseline. */
function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div data-slot="select" className={cn("relative inline-flex w-full", className)}>
      <select
        className={cn(
          "border-input bg-card h-9 w-full cursor-pointer appearance-none rounded-md border py-1 pr-8 pl-3 text-sm shadow-xs transition-colors",
          "focus-visible:ring-ring/50 focus-visible:border-ring focus-visible:ring-2 focus-visible:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="text-muted-foreground pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2"
      />
    </div>
  );
}

export { Select };
