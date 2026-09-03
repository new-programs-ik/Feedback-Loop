"use client";

import { Search } from "lucide-react";
import { openCommandPalette } from "@/components/command-palette";

/** The topbar's search affordance — a quiet field that opens the ⌘K palette. */
export function SearchButton() {
  return (
    <button
      type="button"
      onClick={openCommandPalette}
      className="text-muted-foreground hover:border-foreground/20 hover:text-foreground bg-card/60 hidden h-9 cursor-pointer items-center gap-2 rounded-lg border px-3 text-[13px] transition-colors sm:flex"
      aria-label="Search (Command K)"
    >
      <Search className="size-3.5" aria-hidden />
      <span className="pr-6">Search…</span>
      <kbd className="text-muted-foreground/80 rounded-md border px-1.5 py-px font-mono text-[10.5px]">⌘K</kbd>
    </button>
  );
}
