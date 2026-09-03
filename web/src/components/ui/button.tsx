import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

/** Buttons press (a 2% scale over 120ms — felt, not seen), ring on keyboard focus only, and
 *  can carry their own busy state: `isLoading` swaps the leading icon for a spinner and disables
 *  the control while keeping the label so the button never changes width mid-action. */
const buttonVariants = cva(
  [
    "inline-flex cursor-pointer items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap select-none",
    "transition-[color,background-color,border-color,box-shadow,transform,filter] duration-150 ease-out",
    "active:scale-[0.98] active:duration-[120ms] motion-reduce:active:scale-100",
    "focus-visible:ring-ring/60 focus-visible:ring-offset-background focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none",
    "disabled:pointer-events-none disabled:opacity-50 aria-busy:cursor-progress",
    "[&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
        destructive: "bg-destructive text-white shadow-xs hover:bg-destructive/90",
        outline: "bg-card hover:bg-accent hover:text-accent-foreground border shadow-xs",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        /** The brand gradient — reserved for the one primary CTA on a page. */
        gradient:
          "from-primary bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-white shadow-[inset_0_1px_0_0_rgb(255_255_255/0.18),0_1px_2px_rgb(16_24_40/0.2)] hover:brightness-[1.06] hover:shadow-[inset_0_1px_0_0_rgb(255_255_255/0.22),0_8px_18px_-8px_color-mix(in_oklch,var(--primary)_70%,transparent)]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-6",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  isLoading = false,
  disabled,
  children,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
    /** Shows a spinner in place of the leading icon and disables the button. Ignored with `asChild`. */
    isLoading?: boolean;
  }) {
  if (asChild) {
    return (
      <Slot data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props}>
        {children}
      </Slot>
    );
  }
  return (
    <button
      data-slot="button"
      aria-busy={isLoading || undefined}
      disabled={disabled || isLoading}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    >
      {isLoading ? (
        <>
          <LoaderCircle className="animate-spin" aria-hidden />
          {/* `contents` keeps the flex gap; the label's own icon hides so the spinner takes its seat. */}
          <span className="contents [&>svg]:hidden">{children}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
}

export { Button, buttonVariants };
