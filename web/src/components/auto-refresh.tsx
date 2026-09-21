"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Silently refreshes the page every few seconds while an analysis is running, and stops after
 *  `maxMinutes`: a tab left open overnight must not re-run the page's queries forever. */
export function AutoRefresh({ seconds = 4, maxMinutes = 45 }: { seconds?: number; maxMinutes?: number }) {
  const router = useRouter();
  useEffect(() => {
    const started = Date.now();
    const t = setInterval(() => {
      if (Date.now() - started > maxMinutes * 60_000) {
        clearInterval(t);
        return;
      }
      router.refresh();
    }, seconds * 1000);
    return () => clearInterval(t);
  }, [router, seconds, maxMinutes]);
  return null;
}
