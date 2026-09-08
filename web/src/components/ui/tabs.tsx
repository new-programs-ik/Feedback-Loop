"use client";

import * as React from "react";
import Link from "next/link";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

/** URL-driven segmented control: each tab is a link, and the card-coloured thumb is ONE element
 *  that slides between them (a shared layout animation on a spring). The thumb moves the instant
 *  a tab is clicked — optimistically, before the server confirms — and settles on whatever the
 *  URL says once the navigation lands. Props are plain data, so server pages can render it. */
function SegmentedTabs({
  items,
  className,
  ariaLabel,
}: {
  items: { label: string; href: string; active: boolean }[];
  ariaLabel?: string;
  className?: string;
}) {
  const id = React.useId();
  const reduce = useReducedMotion();
  const serverActive = items.find((i) => i.active)?.href ?? null;
  // The optimistic pick remembers which server state it was made against; once the server moves
  // (navigation done) the override expires on its own — no effect, no flash.
  const [pending, setPending] = React.useState<{ href: string; base: string | null } | null>(null);
  const activeHref = pending && pending.base === serverActive ? pending.href : serverActive;
  const spring = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 520, damping: 42, mass: 0.6 };

  return (
    <LayoutGroup id={id}>
      <nav
        aria-label={ariaLabel}
        data-slot="segmented-tabs"
        className={cn("bg-muted inline-flex items-center gap-0.5 rounded-lg p-0.5", className)}
      >
        {items.map((item) => {
          const active = item.href === activeHref;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={item.active ? "page" : undefined}
              onClick={() => setPending({ href: item.href, base: serverActive })}
              className={cn(
                "relative rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-150",
                "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
                active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {active && (
                <motion.span
                  aria-hidden
                  layoutId={`${id}-thumb`}
                  className="bg-card shadow-soft absolute inset-0 rounded-md"
                  transition={spring}
                />
              )}
              <span className="relative">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </LayoutGroup>
  );
}

export { SegmentedTabs };
