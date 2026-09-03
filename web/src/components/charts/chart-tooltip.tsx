"use client";

import * as React from "react";
import { AnimatePresence, motion, useMotionValue, useSpring } from "motion/react";
import { cn } from "@/lib/utils";
import { EASE_OUT } from "@/components/motion/reveal";
import { clamp } from "./chart-kit";
import { SNAP } from "./chart-motion";

export type TooltipRow = {
  value: string;
  label?: string;
  color?: string;
  swatch?: "dot" | "square" | "line";
};

const SWATCH = {
  dot: "size-2 rounded-full",
  square: "size-2.5 rounded-[3px]",
  line: "h-0.5 w-3 rounded-full",
} as const;

/** The one tooltip every chart uses. Anchored at (x, y) inside `boundsRef` — viewBox units when
 *  `viewBox` is given, else px — it measures itself and sits on whichever side fits, so it is
 *  never clipped; moves between anchors ride a spring; `live` mirrors the text for screen readers. */
export function ChartTooltip({
  open,
  x,
  y,
  viewBox,
  boundsRef,
  title,
  rows,
  children,
  live = false,
  gap = 12,
}: {
  open: boolean;
  x: number;
  y: number;
  viewBox?: [number, number];
  boundsRef: React.RefObject<HTMLElement | null>;
  title?: string;
  rows?: TooltipRow[];
  children?: React.ReactNode;
  live?: boolean;
  gap?: number;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const wasOpen = React.useRef(false);
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const sx = useSpring(mx, SNAP);
  const sy = useSpring(my, SNAP);

  // Measure after every render while open: the anchor or the content may have changed.
  React.useLayoutEffect(() => {
    if (!open) {
      wasOpen.current = false;
      return;
    }
    const tip = ref.current;
    const bounds = boundsRef.current;
    if (!tip || !bounds) return;
    const bw = bounds.clientWidth;
    const bh = bounds.clientHeight;
    const k = viewBox ? bw / viewBox[0] : 1;
    const ax = x * k;
    const ay = y * k;
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    let left = ax + gap;
    if (left + tw > bw) left = ax - gap - tw;
    left = clamp(left, 0, Math.max(0, bw - tw));
    const top = clamp(ay - th / 2, 0, Math.max(0, bh - th));
    if (wasOpen.current) {
      mx.set(left);
      my.set(top);
    } else {
      // First appearance lands in place; only moves between anchors animate.
      mx.jump(left);
      my.jump(top);
      sx.jump(left);
      sy.jump(top);
      wasOpen.current = true;
    }
  });

  const liveText = live && open
    ? [title, ...(rows ?? []).map((r) => [r.value, r.label].filter(Boolean).join(" "))].filter(Boolean).join(", ")
    : "";

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            ref={ref}
            key="tip"
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.14, ease: EASE_OUT }}
            style={{ x: sx, y: sy }}
            className="bg-popover text-popover-foreground shadow-pop pointer-events-none absolute top-0 left-0 z-20 min-w-28 rounded-lg border px-3 py-2 text-xs"
            aria-hidden
          >
            {title != null && <div className="text-muted-foreground mb-1 font-medium">{title}</div>}
            {rows?.map((r, i) => (
              <div key={i} className="flex items-center gap-2 leading-5">
                {r.color && (
                  <span className={cn("shrink-0", SWATCH[r.swatch ?? "dot"])} style={{ background: r.color }} />
                )}
                <span className="font-mono font-semibold tabular-nums">{r.value}</span>
                {r.label && <span className="text-muted-foreground">{r.label}</span>}
              </div>
            ))}
            {children}
          </motion.div>
        )}
      </AnimatePresence>
      {live && (
        <div className="sr-only" role="status" aria-live="polite">
          {liveText}
        </div>
      )}
    </>
  );
}
