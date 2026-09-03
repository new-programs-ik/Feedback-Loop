"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";

const subscribeNoop = () => () => {};

/** A 3px brand-gradient rule pinned to the top of the viewport that fills as you read — the
 *  long-read convention. Driven by scroll progress through a light spring so it glides rather
 *  than ticks; under reduced motion it tracks the scroll position directly. Portaled to <body>
 *  so no animated ancestor (the page-enter template) can turn `fixed` into page-relative.
 *  Hidden in print. */
export function ReadingProgress() {
  const { scrollYProgress } = useScroll();
  const reduce = useReducedMotion();
  const smooth = useSpring(scrollYProgress, { stiffness: 220, damping: 34, mass: 0.35 });
  const isClient = React.useSyncExternalStore(subscribeNoop, () => true, () => false);
  if (!isClient) return null;
  return createPortal(
    <motion.div
      aria-hidden
      data-print-hide
      className="from-primary pointer-events-none fixed inset-x-0 top-0 z-40 h-[3px] origin-left bg-gradient-to-r to-[oklch(0.62_0.2_300)]"
      style={{ scaleX: reduce ? scrollYProgress : smooth }}
    />,
    document.body,
  );
}
