import { cn } from "@/lib/utils";
import { courseColor, courseInitials } from "@/lib/workspace-shared";

/** The course identity square: fixed hue, initials on it. Server-safe. `color` may be the
 *  stored 1–8 index, a CSS colour, or missing (then the slug decides). */
export function CourseSquare({
  name,
  slug,
  color,
  initials,
  size = "md",
  className,
}: {
  name: string;
  slug: string;
  color: string | null | undefined;
  initials?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const s = size === "sm" ? "size-5 text-[9px]" : size === "lg" ? "size-9 text-[13px]" : "size-6 text-[10px]";
  return (
    <span
      aria-hidden
      className={cn("inline-flex shrink-0 items-center justify-center rounded-md font-semibold tracking-tight text-white", s, className)}
      style={{ background: courseColor(color, slug) }}
    >
      {courseInitials(initials, name)}
    </span>
  );
}
