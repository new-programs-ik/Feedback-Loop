"use client";

import * as React from "react";

/** The design tokens the 3D scenes need, resolved to sRGB hex so three.js can use them.
 *  Tokens are authored in oklch (which three cannot parse), so every value is passed through a
 *  1×1 2D canvas and read back — the browser's own colour engine does the conversion. Re-read on
 *  every theme flip (the `.dark` class mutation and the toggle's `theme-change` event). */
export type Palette = {
  isDark: boolean;
  bg: string;
  card: string;
  fg: string;
  muted: string;
  primary: string;
  /** The secondary brand hue used by .text-gradient / .bg-mesh. */
  violet: string;
  good: string;
  bad: string;
};

const VIOLET = "oklch(0.62 0.2 300)";
const SENTINEL = "#010203";
let ctx: CanvasRenderingContext2D | null | undefined;

function readback(css: string): string | null {
  if (typeof document === "undefined" || !css) return null;
  if (ctx === undefined) {
    const c = document.createElement("canvas");
    c.width = c.height = 1;
    ctx = c.getContext("2d", { willReadFrequently: true });
  }
  if (!ctx) return null;
  ctx.fillStyle = SENTINEL;
  ctx.fillStyle = css;
  if (ctx.fillStyle === SENTINEL) return null; // the browser rejected the string
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
  if (a === 0) return null;
  return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
}

export function readPalette(): Palette {
  const root = document.documentElement;
  const isDark = root.classList.contains("dark");
  const cs = getComputedStyle(root);
  const token = (name: string, fallback: string) =>
    readback(cs.getPropertyValue(name).trim()) ?? fallback;
  return {
    isDark,
    bg: token("--background", isDark ? "#1b1d25" : "#fafafb"),
    card: token("--card", isDark ? "#24272f" : "#ffffff"),
    fg: token("--foreground", isDark ? "#eeeff3" : "#25283a"),
    muted: token("--muted-foreground", isDark ? "#a4a7b5" : "#6c6f80"),
    primary: token("--primary", isDark ? "#9a8ff0" : "#4f46c8"),
    violet: readback(VIOLET) ?? "#9b5de5",
    good: token("--viz-good", isDark ? "#6fa591" : "#5f9a85"),
    bad: token("--viz-bad", isDark ? "#d8705c" : "#c45d4b"),
  };
}

// One shared store: the palette is read once per theme flip, not once per scene, and the
// snapshot only changes identity when a colour actually changed (the toggle's transient
// `theme-transition` class would otherwise re-render every consumer three times per flip).
let cached: Palette | null = null;
let observer: MutationObserver | null = null;
const subscribers = new Set<() => void>();
const same = (a: Palette, b: Palette) => (Object.keys(a) as (keyof Palette)[]).every((k) => a[k] === b[k]);

function refresh() {
  const next = readPalette();
  if (cached && same(cached, next)) return;
  cached = next;
  subscribers.forEach((cb) => cb());
}
function subscribe(cb: () => void) {
  subscribers.add(cb);
  if (subscribers.size === 1) {
    observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    window.addEventListener("theme-change", refresh);
  }
  return () => {
    subscribers.delete(cb);
    if (subscribers.size === 0) {
      observer?.disconnect();
      observer = null;
      window.removeEventListener("theme-change", refresh);
    }
  };
}
const getPalette = () => (cached ??= readPalette());
const getServerPalette = () => null;

/** null on the server and during hydration (there are no colours to read), then live across
 *  theme flips. */
export function useThemePalette(): Palette | null {
  return React.useSyncExternalStore(subscribe, getPalette, getServerPalette);
}

let webgl: boolean | undefined;
function hasWebGL(): boolean {
  if (webgl !== undefined) return webgl;
  try {
    const c = document.createElement("canvas");
    webgl = !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    webgl = false;
  }
  return webgl;
}
const noop = () => () => {};
const getNoWebGL = () => null;

/** null on the server and during hydration, then whether this browser can draw WebGL. */
export function useWebGL(): boolean | null {
  return React.useSyncExternalStore(noop, hasWebGL, getNoWebGL);
}
