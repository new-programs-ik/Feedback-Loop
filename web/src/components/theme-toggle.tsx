"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

const subscribeNoop = () => () => {};
import { Moon, Sun, Monitor } from "lucide-react";

type Theme = "light" | "dark" | "system";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function apply(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const root = document.documentElement;
  // Cross-fade colours for the flip (the class is defined in globals.css), then drop it so
  // ordinary interactions are not slowed down by a global transition.
  root.classList.add("theme-transition");
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
  window.setTimeout(() => root.classList.remove("theme-transition"), 300);
  window.dispatchEvent(new Event("theme-change"));
}

const NEXT: Record<Theme, Theme> = { light: "dark", dark: "system", system: "light" };
const LABEL: Record<Theme, string> = {
  light: "Theme: light — switch to dark",
  dark: "Theme: dark — switch to system",
  system: "Theme: follows your system — switch to light",
};

/** Three-state theme control. Reads the same localStorage key the layout's inline
 *  no-flash script reads, so first paint and React state can never disagree. */
export function ThemeToggle() {
  // Lazy init from the same source as the inline script (per the Next preventing-flash guide).
  const [theme, setTheme] = useState<Theme>(readTheme);
  // true only after hydration — server and first client render agree on the neutral icon.
  const mounted = useSyncExternalStore(subscribeNoop, () => true, () => false);

  // Follow live OS changes while in "system" mode.
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);

  const cycle = () => {
    const next = NEXT[theme];
    setTheme(next);
    try {
      if (next === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", next);
    } catch {
      /* storage unavailable — theme still applies for this page view */
    }
    apply(next);
  };

  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  // The label follows the icon: neutral until mounted so server and client markup agree.
  const label = mounted ? LABEL[theme] : "Theme";
  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={label}
      title={label}
      className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 cursor-pointer items-center justify-center rounded-lg transition-colors"
    >
      {/* Until mounted, render the neutral icon so SSR markup matches every client theme. */}
      {mounted ? <Icon className="size-[18px]" /> : <Monitor className="size-[18px]" />}
    </button>
  );
}
