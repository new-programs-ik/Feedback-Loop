"use client";

import * as React from "react";
import { animate, useInView, useReducedMotion, type Transition } from "motion/react";
import { EASE_OUT } from "@/components/motion/reveal";

/** Enter timings: line draw-ins and column growth. */
export const DRAW = { duration: 0.9, ease: EASE_OUT } satisfies Transition;
export const GROW = { duration: 0.55, ease: EASE_OUT } satisfies Transition;
/** Follow physics for crosshairs, halos and the tooltip — stiff enough to feel attached. */
export const SNAP = { type: "spring", stiffness: 520, damping: 44, mass: 0.7 } satisfies Transition;
/** The small overshoot a halo or end-dot pops in with. */
export const POP = { type: "spring", stiffness: 420, damping: 22 } satisfies Transition;

/** Every chart renders its FINAL state on the server and through hydration (no empty boxes, no
 *  layout shift). `play` flips true once, when the chart scrolls into view — never under reduced
 *  motion — and `enter` stays true for the `settle` window while the enter keyframes run. After
 *  that, charts hand their `animate` props plain targets so later changes (legend toggles,
 *  hover) use short live transitions instead of the choreographed delays. */
export function useChartPlay(
  ref: React.RefObject<Element | null>,
  { amount = 0.3, settle = 1.8 }: { amount?: number; settle?: number } = {},
) {
  const inView = useInView(ref, { once: true, amount });
  const reduce = useReducedMotion();
  const play = inView && !reduce;
  const [settled, setSettled] = React.useState(false);
  React.useEffect(() => {
    if (!play) return;
    const t = setTimeout(() => setSettled(true), settle * 1000);
    return () => clearTimeout(t);
  }, [play, settle]);
  return { play, enter: play && !settled, reduce: reduce === true };
}

/** Touch has no hover: a tap sets the hovered mark, the finger lifting must NOT clear it — a tap
 *  anywhere outside the chart does. */
export function useTapOutside(ref: React.RefObject<Element | null>, active: boolean, clear: () => void) {
  React.useEffect(() => {
    if (!active) return;
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) clear();
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  }, [ref, active, clear]);
}

/** Leave handler that ignores the synthetic leave a lifted finger fires. */
export const leaveUnlessTouch = (clear: () => void) => (e: React.PointerEvent) => {
  if (e.pointerType !== "touch") clear();
};

/** An SVG <text> that counts up to `value` once `play` flips; the server renders the final
 *  number so nothing is ever blank, and the final number is restored if the count is cut short. */
export function CountText({
  value,
  play,
  decimals = 0,
  delay = 0,
  duration = 0.8,
  ...rest
}: { value: number; play: boolean; decimals?: number; delay?: number; duration?: number } & React.SVGProps<SVGTextElement>) {
  const ref = React.useRef<SVGTextElement>(null);
  const fmt = React.useMemo(
    () => new Intl.NumberFormat("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }),
    [decimals],
  );
  React.useEffect(() => {
    const el = ref.current;
    if (!el || !play) return;
    const controls = animate(0, value, {
      duration,
      delay,
      ease: EASE_OUT,
      onUpdate: (v) => {
        el.textContent = fmt.format(v);
      },
    });
    return () => {
      controls.stop();
      el.textContent = fmt.format(value);
    };
  }, [play, value, delay, duration, fmt]);
  return (
    <text ref={ref} {...rest}>
      {fmt.format(value)}
    </text>
  );
}
