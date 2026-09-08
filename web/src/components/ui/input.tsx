import * as React from "react";
import { fieldClasses } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/** Text/date/month input on the shared field chrome (36px, card surface, brand focus ring).
 *  Native date pickers follow the theme via `color-scheme`. */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        fieldClasses,
        "placeholder:text-muted-foreground dark:scheme-dark flex w-full px-3 py-1",
        "file:text-foreground file:border-0 file:bg-transparent file:text-sm file:font-medium",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
