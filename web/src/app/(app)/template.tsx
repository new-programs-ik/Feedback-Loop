"use client";

import { motion } from "motion/react";
import { useReducedMotionSafe } from "@/components/motion/reveal";

/** Next re-mounts a template on every navigation, which is exactly what a page-enter animation
 *  needs: the new page rises in; the old one is simply replaced (no exit — exits on route change
 *  read as lag in a dashboard). The tree is identical on server and client; reduced motion only
 *  zeroes the duration. */
export default function Template({ children }: { children: React.ReactNode }) {
  const reduce = useReducedMotionSafe();
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduce ? { duration: 0 } : { duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
