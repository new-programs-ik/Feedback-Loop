"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Silently refreshes the page every few seconds — used while an analysis is still running. */
export function AutoRefresh({ seconds = 4 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const t = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(t);
  }, [router, seconds]);
  return null;
}
