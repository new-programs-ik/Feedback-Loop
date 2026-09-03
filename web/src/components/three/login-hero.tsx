"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { useThemePalette, useWebGL } from "@/components/three/theme-palette";

const LoginScene = dynamic(() => import("./login-scene").then((m) => m.LoginScene), { ssr: false });

// The page's own breakpoint for the two-column layout (Tailwind `lg`), as an external store so
// the server render (stacked) and the hydrating client agree, then the real value takes over.
const WIDE = "(min-width: 1024px)";
const subscribeWide = (cb: () => void) => {
  const mq = window.matchMedia(WIDE);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
const getWide = () => window.matchMedia(WIDE).matches;
const getServerWide = () => false;

/** The sign-in page's scene, mounted over the page's own gradient backdrop. Until the palette
 *  is read (right after hydration) or when WebGL is unavailable, that backdrop is the whole hero. */
export function LoginHero() {
  const palette = useThemePalette();
  const webgl = useWebGL();
  const reduce = useReducedMotion();
  const wide = React.useSyncExternalStore(subscribeWide, getWide, getServerWide);

  if (!palette || !webgl) return null;
  return (
    <div aria-hidden className="absolute inset-0">
      <React.Suspense fallback={null}>
        <LoginScene palette={palette} reduce={!!reduce} wide={wide} />
      </React.Suspense>
    </div>
  );
}
