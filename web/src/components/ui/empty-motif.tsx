"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { EASE_OUT } from "@/components/motion/reveal";
import { cn } from "@/lib/utils";

/** The thin-line illustration behind every empty state: an open tray with nothing in it, a
 *  dotted orbit where the icon sits, and two ticks. Drawn in stroke by stroke on mount (~1s);
 *  static under reduced motion. Colour is the muted token so it never competes with the text. */
export function EmptyMotif({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  const draw = (delay: number, duration = 0.8) =>
    reduce
      ? {}
      : {
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1 },
          transition: {
            pathLength: { duration, ease: EASE_OUT, delay },
            opacity: { duration: 0.2, delay },
          },
        };
  return (
    <svg
      viewBox="0 0 160 112"
      width="160"
      height="112"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={cn("text-muted-foreground/45", className)}
    >
      {/* the tray */}
      <motion.path d="M30 70v22a6 6 0 0 0 6 6h88a6 6 0 0 0 6-6V70" {...draw(0.15)} />
      <motion.path d="M30 70h28l8 10h28l8-10h28" {...draw(0.35, 0.6)} />
      {/* the orbit the icon sits in */}
      <motion.circle cx="80" cy="34" r="30" strokeDasharray="3 6" {...draw(0, 1.1)} />
      {/* ticks */}
      <motion.path d="M22 26l-5-5" {...draw(0.7, 0.3)} />
      <motion.path d="M138 26l5-5" {...draw(0.8, 0.3)} />
      <motion.path d="M14 44h-6" {...draw(0.9, 0.3)} />
      <motion.path d="M152 44h-6" {...draw(1, 0.3)} />
    </svg>
  );
}
