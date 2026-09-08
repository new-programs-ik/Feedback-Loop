"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";
import { Eye, EyeOff, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useThemePalette, useWebGL } from "@/components/three/theme-palette";

/** Plain JSON, computed on the server from byInstructor(rows). */
export type GalaxyPoint = {
  name: string;
  n: number;
  avgRating: number | null;
  approval: number | null;
  avgParticipation: number | null;
  bad: number;
  /** Where a click goes; defaults to the legacy instructor-analytics query link. */
  href?: string;
};

// The canvas (and three.js with it) only ever loads in the browser.
const GalaxyCanvas = dynamic(() => import("./sme-galaxy-canvas").then((m) => m.GalaxyCanvas), {
  ssr: false,
  loading: () => <Shimmer />,
});

function Shimmer() {
  return <div aria-hidden className="shimmer absolute inset-0" />;
}

// "Hide 3D view" is remembered per browser. An external store keeps the server render (always
// shown) and the first client render in agreement, so there is nothing to hydrate wrongly.
const HIDDEN_KEY = "ia:galaxy-hidden";
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
};
const getHidden = () => {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
};
const setHidden = (v: boolean) => {
  try {
    if (v) localStorage.setItem(HIDDEN_KEY, "1");
    else localStorage.removeItem(HIDDEN_KEY);
  } catch {
    /* storage unavailable — the toggle still works for this page view */
  }
  listeners.forEach((l) => l());
};

const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));
const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);

/** The SME galaxy: one sphere per instructor, rating × approval × participation. The section
 *  chrome (title, toggle, legend, hint, the screen-reader list) is ordinary DOM; only the scene
 *  is WebGL, and it degrades to a sentence when WebGL is off — the table below always remains. */
export function SmeGalaxy({ points, query }: { points: GalaxyPoint[]; query: string }) {
  const router = useRouter();
  const reduce = useReducedMotion();
  const palette = useThemePalette();
  const hidden = React.useSyncExternalStore(subscribe, getHidden, () => false);
  const webgl = useWebGL();
  const [inView, setInView] = React.useState(true);
  const [resetKey, setResetKey] = React.useState(0);
  const hostRef = React.useRef<HTMLDivElement>(null);

  // No frames while the section is scrolled away.
  React.useEffect(() => {
    const el = hostRef.current;
    if (!el || hidden) return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.05 });
    io.observe(el);
    return () => io.disconnect();
  }, [hidden, webgl]);

  const href = React.useCallback(
    (name: string) => {
      const own = points.find((pt) => pt.name === name)?.href;
      if (own) return own;
      const p = new URLSearchParams(query);
      p.set("sme", name);
      return `/instructor-analytics?${p}`;
    },
    [points, query],
  );
  const onSelect = React.useCallback((name: string) => router.push(href(name)), [router, href]);

  const shown = points.filter((p) => p.avgRating != null);

  return (
    <section aria-labelledby="sme-galaxy-title" className="bg-card shadow-soft mb-5 overflow-hidden rounded-xl border">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-3.5 pb-3 sm:px-5">
        <div className="min-w-0">
          <h2 id="sme-galaxy-title" className="text-[13px] font-semibold tracking-[-0.01em]">
            SME galaxy
          </h2>
          <p className="text-muted-foreground mt-0.5 max-w-3xl text-xs">
            Every instructor as a sphere — further right is a higher rating, higher up is more of the room wanting them
            back, deeper in is a larger share of attendees who rated; size is how many classes.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1" data-print-hide>
          {!hidden && webgl && (
            <Button variant="ghost" size="sm" onClick={() => setResetKey((k) => k + 1)}>
              <RotateCcw aria-hidden /> Reset view
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setHidden(!hidden)} aria-expanded={!hidden}>
            {hidden ? <Eye aria-hidden /> : <EyeOff aria-hidden />}
            {hidden ? "Show 3D view" : "Hide 3D view"}
          </Button>
        </div>
      </div>

      {!hidden && (
        <div
          ref={hostRef}
          className="bg-card relative h-[320px] border-t md:h-[420px]"
          role="img"
          aria-label={`3D scatter of ${shown.length} instructors by average rating, approval and participation.`}
        >
          {webgl === false ? (
            <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
              <p className="text-muted-foreground max-w-sm text-sm">
                This browser can&apos;t draw the 3D view (WebGL is off). Every instructor is in the table below.
              </p>
            </div>
          ) : webgl && palette ? (
            <React.Suspense fallback={<Shimmer />}>
              <GalaxyCanvas
                points={shown}
                palette={palette}
                reduce={!!reduce}
                inView={inView}
                resetKey={resetKey}
                onSelect={onSelect}
              />
            </React.Suspense>
          ) : (
            <Shimmer />
          )}

          {/* Legend + hint sit on glass so they read on any fog colour. */}
          <div className="pointer-events-none absolute inset-x-3 bottom-3 flex flex-wrap items-end justify-between gap-2">
            <ul className="glass flex items-center gap-3 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium">
              <li className="flex items-center gap-1.5">
                <span className="bg-viz-good size-2 rounded-full" aria-hidden /> Clears both bars
              </li>
              <li className="flex items-center gap-1.5">
                <span className="bg-viz-bad size-2 rounded-full" aria-hidden /> Needs attention
              </li>
              <li className="flex items-center gap-1.5">
                <span className="bg-primary size-2 rounded-full" aria-hidden /> Selected
              </li>
            </ul>
            <p className="text-muted-foreground hidden text-[11px] sm:block">
              Drag to orbit · scroll to zoom once engaged · click a sphere to open
            </p>
          </div>
        </div>
      )}

      {/* Keyboard + screen-reader channel: the same instructors as links. Becomes visible while
          one of them has focus so sighted keyboard users see where they are. */}
      <nav aria-label="Instructors in the 3D view" className="sr-only focus-within:not-sr-only focus-within:border-t">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2 text-xs sm:px-5">
          {shown.map((p) => (
            <li key={p.name}>
              <Link href={href(p.name)} className="hover:text-primary rounded-sm underline-offset-2 hover:underline">
                {p.name}
                <span className="text-muted-foreground">
                  {" "}
                  · {p.n} classes · {fmtAvg(p.avgRating)} · {fmtPct(p.approval)} back · {fmtPct(p.avgParticipation)}{" "}
                  rated
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </section>
  );
}
