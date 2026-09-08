"use client";

import * as React from "react";
import { animate, useInView, useReducedMotion } from "motion/react";

/** A number that counts up from 0 the first time it scrolls into view. Tabular digits so the
 *  width never jitters mid-count; formatting is done per frame with Intl so 2,757 stays 2,757. */
export function CountUp({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  duration = 1.1,
  className,
}: {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
}) {
  const ref = React.useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const reduce = useReducedMotion();
  const fmt = React.useMemo(
    () => new Intl.NumberFormat("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }),
    [decimals],
  );

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!inView) return;
    if (reduce) {
      el.textContent = prefix + fmt.format(value) + suffix;
      return;
    }
    const controls = animate(0, value, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        el.textContent = prefix + fmt.format(v) + suffix;
      },
    });
    return () => controls.stop();
  }, [inView, value, duration, fmt, prefix, suffix, reduce]);

  // Server render shows the final value so the page never paints an empty number.
  return (
    <span ref={ref} data-numeric className={className}>
      {prefix}
      {fmt.format(value)}
      {suffix}
    </span>
  );
}
