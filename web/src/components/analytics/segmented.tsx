"use client";

import * as React from "react";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

/** A state-driven segmented control (the URL-driven twin is `SegmentedTabs`): a radio group of
 *  buttons with ONE card-coloured thumb that slides between them. Arrow keys move the choice, so
 *  it behaves like a native radio group for keyboard users. */
export function Segmented<V extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  size = "md",
  className,
}: {
  value: V;
  onChange: (v: V) => void;
  options: { value: V; label: string; title?: string }[];
  ariaLabel: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const id = React.useId();
  const reduce = useReducedMotion();
  const spring = reduce ? { duration: 0 } : { type: "spring" as const, stiffness: 520, damping: 42, mass: 0.6 };
  const onKeyDown = (e: React.KeyboardEvent) => {
    const i = options.findIndex((o) => o.value === value);
    if (i < 0) return;
    let next = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % options.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + options.length) % options.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = options.length - 1;
    else return;
    e.preventDefault();
    onChange(options[next].value);
    (e.currentTarget.querySelectorAll<HTMLButtonElement>("button")[next] as HTMLButtonElement | undefined)?.focus();
  };
  return (
    <LayoutGroup id={id}>
      <div
        role="radiogroup"
        aria-label={ariaLabel}
        onKeyDown={onKeyDown}
        className={cn("bg-muted inline-flex items-center gap-0.5 rounded-lg p-0.5", className)}
      >
        {options.map((o) => {
          const active = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              title={o.title}
              onClick={() => onChange(o.value)}
              className={cn(
                "relative rounded-md font-medium transition-colors duration-150",
                size === "sm" ? "px-2 py-1 text-[11px]" : "px-3 py-1.5 text-sm",
                "focus-visible:ring-ring/50 focus-visible:ring-2 focus-visible:outline-none",
                active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {active && <motion.span aria-hidden layoutId={`${id}-thumb`} className="bg-card shadow-soft absolute inset-0 rounded-md" transition={spring} />}
              <span className="relative">{o.label}</span>
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
