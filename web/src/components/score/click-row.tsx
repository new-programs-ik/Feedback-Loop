"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

/** A table row that opens a URL when clicked (or Enter is pressed on it) — the classes table's
 *  "row click opens the drawer". Inner links and buttons keep working; the row is focusable so
 *  the keyboard path exists too. */
export function ClickRow({
  href,
  active = false,
  className,
  children,
}: {
  href: string;
  active?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const go = () => router.push(href, { scroll: false });
  return (
    <tr
      data-slot="table-row"
      data-state={active ? "selected" : undefined}
      tabIndex={0}
      aria-current={active ? "true" : undefined}
      onClick={(e) => {
        const t = e.target as HTMLElement;
        if (t.closest("a, button, input, select, label, [data-no-row-click]")) return;
        go();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) go();
      }}
      className={cn(
        "group/row hover:bg-muted/40 data-[state=selected]:bg-muted/60 cursor-pointer border-b transition-colors duration-150",
        "focus-visible:bg-accent/40 focus-visible:outline-none",
        className,
      )}
    >
      {children}
    </tr>
  );
}
