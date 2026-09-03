"use client";

import * as React from "react";
import { motion, useInView } from "motion/react";
import { EASE_OUT, useReducedMotionSafe } from "@/components/motion/reveal";
import { PRINT_SAFE } from "@/components/insights/print-safe";
import { cn } from "@/lib/utils";

const HIDDEN = { opacity: 0, x: -6, clipPath: "inset(-10% 100% -10% -2%)" };
const SHOWN = { opacity: 1, x: 0, clipPath: "inset(-10% -2% -10% -2%)" };

/** Entrance for a Callout: a left-to-right wipe, so the accent bar lands first and the claim
 *  follows it in (~550ms, once). The element that is OBSERVED is a plain, unclipped wrapper —
 *  Chrome's IntersectionObserver honours clip-path, so a box that starts fully clipped would
 *  never count as visible and never reveal. The clip is dropped once the wipe settles so the
 *  card's shadow is untouched; print forces everything visible. */
export function AccentReveal({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.2 });
  const reduce = useReducedMotionSafe();
  const [settled, setSettled] = React.useState(false);
  return (
    <div ref={ref} className={className}>
      <motion.div
        className={PRINT_SAFE}
        initial={HIDDEN}
        animate={inView ? SHOWN : HIDDEN}
        transition={reduce ? { duration: 0 } : { duration: 0.55, ease: EASE_OUT, delay }}
        onAnimationComplete={() => inView && setSettled(true)}
        style={settled ? { clipPath: "none" } : undefined}
      >
        {children}
      </motion.div>
    </div>
  );
}
