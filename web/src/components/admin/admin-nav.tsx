"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/admin/scoring", label: "Scoring" },
  { href: "/admin/identity", label: "Identity" },
  { href: "/admin/people", label: "People" },
  { href: "/admin/sync", label: "Sync" },
  { href: "/admin/audit", label: "Audit" },
] as const;

/** The five admin surfaces as one quiet strip under the page title, so an admin can move
 *  between them without the rail (which the shell owns). Active = underline, not a fill. */
export function AdminNav({ className }: { className?: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Admin sections" className={cn("mb-5 flex flex-wrap gap-x-1 border-b", className)}>
      {ITEMS.map((it) => {
        const active = pathname === it.href || pathname.startsWith(it.href + "/");
        return (
          <Link
            key={it.href}
            href={it.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors",
              active ? "border-primary text-foreground" : "text-muted-foreground hover:text-foreground border-transparent",
            )}
          >
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}
