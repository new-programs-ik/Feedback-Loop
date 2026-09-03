import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

/** The one field chrome shared by Select and Input: 36px tall, card surface, hairline border that
 *  warms on hover, and a soft 3px brand ring on focus. Exported so ad-hoc controls can match. */
export const fieldClasses = cn(
  "border-input bg-card h-9 rounded-md border text-sm shadow-xs",
  "transition-[border-color,box-shadow] duration-150",
  "hover:border-ring/40 focus-visible:border-ring focus-visible:ring-ring/25 focus-visible:ring-[3px] focus-visible:outline-none",
  "aria-invalid:border-destructive aria-invalid:ring-destructive/20",
  "disabled:cursor-not-allowed disabled:opacity-50",
);

/** Styled NATIVE <select> — keyboard, mobile pickers and form semantics for free.
 *  Matches Input's height/border/ring so mixed filter rows sit on one baseline. */
function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div data-slot="select" className={cn("relative inline-flex w-full", className)}>
      <select
        className={cn(fieldClasses, "w-full cursor-pointer appearance-none py-1 pr-8 pl-3")}
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
