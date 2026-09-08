"use client";

import { MotionConfig } from "motion/react";

/** App-wide motion policy: users who asked their OS for reduced motion get transform and
 *  layout animations switched off automatically (opacity fades stay), without any component
 *  having to branch its tree — which keeps server and client markup identical. */
export function AppMotionConfig({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
