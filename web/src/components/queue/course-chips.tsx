"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export type CourseChipItem = {
  /** null = "All" */
  id: string | null;
  href: string;
  name: string;
  count: number;
};

/** Course scope pills. The active fill is ONE shared element (`layoutId`) that slides to the
 *  chip you click — optimistically, before the server answers, so the scope change feels
 *  instant even though the rows arrive a moment later. Plain links underneath: middle-click,
 *  copy-link and the back button all still work. */
export function CourseChips({ items, activeId }: { items: CourseChipItem[]; activeId: string | null }) {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [optimisticActive, setOptimisticActive] = React.useOptimistic(activeId);
  const [, startTransition] = React.useTransition();

  const go = (e: React.MouseEvent<HTMLAnchorElement>, item: CourseChipItem) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    startTransition(() => {
      setOptimisticActive(item.id);
      router.push(item.href);
    });
  };

  return (
    <LayoutGroup id="course-chips">
      <nav aria-label="Course scope" className="flex flex-wrap items-center gap-1.5">
        {items.map((item) => {
          const active = optimisticActive === item.id;
          return (
            <Link
              key={item.id ?? "all"}
              href={item.href}
              onClick={(e) => go(e, item)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "relative isolate inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                active ? "border-transparent text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
              )}
            >
              {active && (
                <motion.span
                  layoutId="course-pill"
                  aria-hidden
                  className="bg-primary absolute -inset-px -z-10 rounded-full"
                  transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 42, mass: 0.8 }}
                />
              )}
              <span className="max-w-44 truncate">{item.name}</span>
              <span data-numeric className={active ? "text-primary-foreground/70" : "text-muted-foreground/70"}>
                {item.count}
              </span>
            </Link>
          );
        })}
      </nav>
    </LayoutGroup>
  );
}
