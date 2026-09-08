"use client";

import * as React from "react";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export type InsightSection = { id: string; n: number; short: string; title: string };

/** Headroom under the sticky topbar; matches the sections' `scroll-mt-28` (112px). */
const TOP_OFFSET = 112;

/** The study's table of contents. On xl+ it is a left rail that stays put while you read; below
 *  that it is a frosted pill row stuck under the topbar. One highlight element slides between
 *  entries (shared layout, spring). The current section comes from an IntersectionObserver
 *  watching a reading band near the top of the viewport; clicking scrolls smoothly and moves the
 *  highlight at once (the observer is muted for the ride so it cannot flicker through the
 *  sections in between). Not printed. */
export function SectionNav({ sections, className }: { sections: InsightSection[]; className?: string }) {
  const id = React.useId();
  const reduce = useReducedMotion();
  const [active, setActive] = React.useState(sections[0]?.id ?? "");
  // While a click-driven smooth scroll is in flight the observer is muted (see `go`).
  const locked = React.useRef(false);
  const lockTimer = React.useRef<number | undefined>(undefined);
  const rowRef = React.useRef<HTMLDivElement>(null);
  const spring = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 480, damping: 40, mass: 0.6 };

  React.useEffect(() => {
    const els = sections
      .map((s) => document.getElementById(s.id))
      .filter((e): e is HTMLElement => e != null);
    if (els.length === 0) return;

    const inBand = new Set<string>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) inBand.add(e.target.id);
          else inBand.delete(e.target.id);
        }
        if (locked.current) return;
        // Of everything crossing the band, the furthest-down section is the one being read —
        // its heading has just arrived while the previous section's tail is leaving.
        const current = [...sections].reverse().find((s) => inBand.has(s.id));
        if (current) setActive(current.id);
      },
      { rootMargin: `-${TOP_OFFSET}px 0px -60% 0px` },
    );
    els.forEach((el) => io.observe(el));

    // A short final section may never reach the band: at the foot of the page it wins anyway.
    const onScroll = () => {
      if (locked.current) return;
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 8;
      if (atBottom) setActive(els[els.length - 1].id);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.clearTimeout(lockTimer.current);
    };
  }, [sections]);

  // Keep the active pill in view inside the horizontal row.
  React.useEffect(() => {
    const row = rowRef.current;
    const pill = row?.querySelector<HTMLElement>(`[data-section="${active}"]`);
    if (!row || !pill) return;
    const left = pill.offsetLeft - 16;
    const right = pill.offsetLeft + pill.offsetWidth + 16;
    if (left < row.scrollLeft || right > row.scrollLeft + row.clientWidth) {
      row.scrollTo({ left: Math.max(0, left), behavior: reduce ? "auto" : "smooth" });
    }
  }, [active, reduce]);

  const go = (e: React.MouseEvent<HTMLAnchorElement>, sectionId: string) => {
    const el = document.getElementById(sectionId);
    if (!el) return;
    e.preventDefault();
    locked.current = true;
    window.clearTimeout(lockTimer.current);
    lockTimer.current = window.setTimeout(() => {
      locked.current = false;
    }, reduce ? 50 : 900);
    setActive(sectionId);
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    history.replaceState(null, "", `#${sectionId}`);
  };

  return (
    <LayoutGroup id={id}>
      {/* xl and up: the rail */}
      <nav aria-label="Sections" data-print-hide className={cn("hidden xl:block", className)}>
        <div className="sticky top-24">
          <p className="text-muted-foreground/80 mb-2 pl-3 text-[10.5px] font-semibold tracking-[0.08em] uppercase">
            In this study
          </p>
          <ul className="space-y-0.5">
            {sections.map((s) => {
              const on = s.id === active;
              return (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    onClick={(e) => go(e, s.id)}
                    aria-current={on ? "location" : undefined}
                    className={cn(
                      "relative flex items-baseline gap-2 rounded-md py-1.5 pr-2 pl-3 text-[12.5px] leading-snug transition-colors duration-150",
                      "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
                      on ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {on && (
                      <motion.span
                        aria-hidden
                        layoutId={`${id}-rail`}
                        className="bg-accent/70 absolute inset-0 rounded-md"
                        transition={spring}
                      />
                    )}
                    {on && (
                      <motion.span
                        aria-hidden
                        layoutId={`${id}-bar`}
                        className="bg-primary absolute top-[calc(50%-8px)] left-0 h-4 w-0.5 rounded-full"
                        transition={spring}
                      />
                    )}
                    <span className="text-muted-foreground relative w-3 shrink-0 text-[11px]" data-numeric>
                      {s.n}
                    </span>
                    <span className="relative">{s.short}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      </nav>

      {/* below xl: the pill row */}
      <nav
        aria-label="Sections"
        data-print-hide
        className="glass sticky top-16 z-10 -mx-4 mt-6 border-b px-4 py-2 md:-mx-8 md:px-8 xl:hidden"
      >
        <div
          ref={rowRef}
          className="flex gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {sections.map((s) => {
            const on = s.id === active;
            return (
              <a
                key={s.id}
                href={`#${s.id}`}
                data-section={s.id}
                onClick={(e) => go(e, s.id)}
                aria-current={on ? "location" : undefined}
                className={cn(
                  "relative shrink-0 rounded-full px-3 py-1 text-[12.5px] font-medium whitespace-nowrap transition-colors duration-150",
                  "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
                  on ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {on && (
                  <motion.span
                    aria-hidden
                    layoutId={`${id}-pill`}
                    className="bg-primary absolute inset-0 rounded-full"
                    transition={spring}
                  />
                )}
                <span className="relative">
                  <span className="mr-1 opacity-70" data-numeric>
                    {s.n}
                  </span>
                  {s.short}
                </span>
              </a>
            );
          })}
        </div>
      </nav>
    </LayoutGroup>
  );
}
