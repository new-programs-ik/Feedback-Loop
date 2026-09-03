import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/** Status chips. `outline` is a hairline (quiet metadata: "Live", "ARS"); `soft` is a tint of
 *  the brand colour for labels that should read as a state without shouting ("Coming soon"). */
const badgeVariants = cva(
  "inline-flex w-fit items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap [&_svg]:size-3 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground border-transparent",
        secondary: "bg-secondary text-secondary-foreground border-transparent",
        outline: "border-border/80 text-foreground/85 bg-transparent",
        soft: "bg-primary/10 text-primary dark:bg-primary/15 border-transparent",
        success: "bg-success border-transparent text-white",
        warning: "bg-warning border-transparent text-black",
        destructive: "bg-destructive border-transparent text-white",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
