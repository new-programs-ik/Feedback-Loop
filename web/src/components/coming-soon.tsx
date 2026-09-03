"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EASE_OUT, Stagger, StaggerItem } from "@/components/motion/reveal";

/** A wireframe of the page that will live here: a card frame, six columns that breathe slowly,
 *  and a trend line that draws itself once. Quiet by design — brand tint at 25%, hairline chrome. */
function Illustration() {
  const reduce = useReducedMotion();
  const base = 92;
  const bars = [
    { x: 22, h: 26 },
    { x: 40, h: 44 },
    { x: 58, h: 34 },
    { x: 76, h: 56 },
    { x: 94, h: 40 },
    { x: 112, h: 62 },
  ];
  return (
    <svg
      viewBox="0 0 200 120"
      className="h-auto w-full max-w-[240px]"
      aria-hidden
      fill="none"
      stroke="currentColor"
      strokeWidth="1.25"
      strokeLinecap="round"
    >
      <rect x="8" y="8" width="184" height="104" rx="10" className="text-border" />
      <path d="M8 30h184" className="text-border" />
      <circle cx="20" cy="19" r="2.5" className="text-muted-foreground/50" />
      <circle cx="30" cy="19" r="2.5" className="text-muted-foreground/50" />
      <path d={`M20 ${base}h108`} className="text-border" />
      {bars.map((b, i) => (
        <motion.rect
          key={b.x}
          x={b.x}
          width="10"
          rx="2"
          fill="currentColor"
          stroke="none"
          className="text-primary/25"
          // `attrY` drives the SVG attribute (plain `y` would be a translate transform).
          initial={{ attrY: base - b.h, height: b.h }}
          animate={
            reduce
              ? undefined
              : { attrY: [base - b.h, base - b.h * 0.7, base - b.h], height: [b.h, b.h * 0.7, b.h] }
          }
          transition={{ duration: 3.6 + i * 0.4, repeat: Infinity, ease: "easeInOut", delay: i * 0.25 }}
        />
      ))}
      <motion.path
        d="M136 84c8-8 14-26 24-26s12 18 24 10"
        className="text-primary"
        strokeWidth="1.5"
        initial={reduce ? undefined : { pathLength: 0 }}
        animate={reduce ? undefined : { pathLength: 1 }}
        transition={{ duration: 1.2, ease: EASE_OUT, delay: 0.3 }}
      />
      <motion.circle
        cx="184"
        cy="68"
        r="3"
        fill="currentColor"
        stroke="none"
        className="text-primary"
        // Motion scales SVG around the element's own centre (fill-box) — no origin override needed.
        animate={reduce ? undefined : { scale: [1, 1.5, 1], opacity: [1, 0.55, 1] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut", delay: 1.5 }}
      />
    </svg>
  );
}

/** Polished placeholder for modules that are planned but not yet built. */
export function ComingSoon({
  title,
  description,
  cards = ["Overview", "Trends", "Details"],
}: {
  title: string;
  description: string;
  cards?: string[];
}) {
  return (
    <div className="space-y-6">
      <div className="bg-card shadow-soft grid gap-6 rounded-xl border p-6 sm:p-8 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[22px] font-semibold tracking-[-0.02em]">{title}</h1>
            <Badge variant="soft">
              <Sparkles aria-hidden /> Coming soon
            </Badge>
          </div>
          <p className="text-muted-foreground mt-2 max-w-xl text-[13.5px] leading-relaxed">{description}</p>
          <p className="text-muted-foreground/80 mt-3 text-xs">
            This module is on the roadmap — the pieces below are what it will show once its data source is wired in.
          </p>
        </div>
        <div className="text-muted-foreground mx-auto w-full max-w-[240px] md:mx-0">
          <Illustration />
        </div>
      </div>

      <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((c) => (
          <StaggerItem key={c}>
           <div className="bg-card shadow-soft hover-lift h-full rounded-xl border p-5">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[13px] font-semibold tracking-[-0.01em]">{c}</div>
              <Badge variant="outline" className="text-muted-foreground">
                planned
              </Badge>
            </div>
            <div className="surface-inset mt-4 space-y-2.5 rounded-lg border border-dashed p-4" aria-hidden>
              <div className="bg-muted-foreground/15 h-2 w-2/5 rounded-full" />
              <div className="bg-muted-foreground/15 h-2 w-4/5 rounded-full" />
              <div className="bg-muted-foreground/15 h-2 w-3/5 rounded-full" />
              <div className="mt-3 flex items-end gap-1.5">
                {[40, 65, 50, 80, 60].map((h, i) => (
                  <div key={i} className="bg-primary/15 w-4 rounded-t-[3px]" style={{ height: h * 0.4 }} />
                ))}
              </div>
            </div>
           </div>
          </StaggerItem>
        ))}
      </Stagger>
    </div>
  );
}
