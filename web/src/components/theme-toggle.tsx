"use client";

import { useEffect, useState } from "react";
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
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
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
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

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
  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={LABEL[theme]}
      title={LABEL[theme]}
      className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 cursor-pointer items-center justify-center rounded-lg transition-colors"
    >
      {/* Until mounted, render the neutral icon so SSR markup matches every client theme. */}
      {mounted ? <Icon className="size-[18px]" /> : <Monitor className="size-[18px]" />}
    </button>
  );
}
