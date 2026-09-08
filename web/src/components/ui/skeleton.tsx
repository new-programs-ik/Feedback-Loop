import { cn } from "@/lib/utils";

/** Shimmering placeholder shown while a page's data loads. Sized by the caller to match the
 *  element it stands in for, so nothing jumps when the real content lands. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn("shimmer bg-muted rounded-md", className)} {...props} />;
}
