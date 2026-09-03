"use client";

import * as React from "react";
import { motion, useReducedMotion, type Variants } from "motion/react";
import { cn } from "@/lib/utils";

/** The house easing: a fast start that settles softly — reads as "placed", not "bounced". */
export const EASE_OUT = [0.22, 1, 0.36, 1] as const;

/** `useReducedMotion()` is null on the server and true/false on the client, so branching the
 *  tree on it breaks hydration. This returns false until mounted (server and first client render
 *  agree), then the real preference — animations simply collapse to zero duration for those users. */
export function useReducedMotionSafe(): boolean {
  const reduce = useReducedMotion();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  return mounted && !!reduce;
}

const item: Variants = {
  hidden: { opacity: 0, y: 10, filter: "blur(2px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.45, ease: EASE_OUT } },
};

/** Fade-and-rise a block into view once, when ~20% of it is on screen. */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section" | "li";
}) {
  const reduce = useReducedMotionSafe();
  const Comp = motion[as];
  return (
    <Comp
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.2 }}
      variants={{
        hidden: item.hidden,
        show: { ...item.show, transition: reduce ? { duration: 0 } : { duration: 0.45, ease: EASE_OUT, delay } },
      }}
    >
      {children}
    </Comp>
  );
}

/** A container whose direct children (each wrapped in StaggerItem) enter one after another. */
export function Stagger({
  children,
  className,
  step = 0.06,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  step?: number;
  delay?: number;
}) {
  const reduce = useReducedMotionSafe();
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.15 }}
      variants={{
        hidden: {},
        show: { transition: reduce ? { staggerChildren: 0, delayChildren: 0 } : { staggerChildren: step, delayChildren: delay } },
      }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className }: { children: React.ReactNode; className?: string }) {
  const reduce = useReducedMotionSafe();
  return (
    <motion.div
      className={cn(className)}
      variants={reduce ? { hidden: item.hidden, show: { ...item.show, transition: { duration: 0 } } } : item}
    >
      {children}
    </motion.div>
  );
}
