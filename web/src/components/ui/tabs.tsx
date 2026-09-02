import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

/** URL-driven segmented control (server-safe): each tab is a link; the active one wears the
 *  card-colored thumb. Used for the Reports range presets and any page-level mode switch. */
function SegmentedTabs({
  items,
  className,
  ariaLabel,
}: {
  items: { label: string; href: string; active: boolean }[];
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <nav
      aria-label={ariaLabel}
      data-slot="segmented-tabs"
      className={cn("bg-muted inline-flex items-center gap-0.5 rounded-lg p-0.5", className)}
    >
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={item.active ? "page" : undefined}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            item.active
              ? "bg-card text-foreground shadow-soft"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

export { SegmentedTabs };
