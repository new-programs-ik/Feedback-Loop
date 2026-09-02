"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { NAV } from "@/lib/nav";

// Labels for path segments that aren't top-level nav entries.
const EXTRA_LABELS: Record<string, string> = {
  new: "New analysis",
  admin: "Admin",
  users: "Users & Roles",
  "audit-log": "Audit Log",
};

const NAV_LABELS: Record<string, string> = Object.fromEntries(
  NAV.flatMap((s) => s.items).map((i) => [i.href.replace(/^\//, ""), i.label]),
);

/** Topbar breadcrumbs, shown only at depth >= 2 (drill-ins, detail pages). IDs render as a
 *  generic "Details" tail — pages show the real name in their own PageHeader. */
export function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length < 2) return null;

  const crumbs = segments.map((seg, i) => {
    const href = "/" + segments.slice(0, i + 1).join("/");
    const label =
      NAV_LABELS[segments.slice(0, i + 1).join("/")] ??
      NAV_LABELS[seg] ??
      EXTRA_LABELS[seg] ??
      (/^[0-9a-f-]{16,}$/i.test(seg) ? "Details" : seg.replace(/-/g, " "));
    return { href, label, last: i === segments.length - 1 };
  });

  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-sm sm:flex">
      {crumbs.map((c) => (
        <span key={c.href} className="flex min-w-0 items-center gap-1">
          {c.last ? (
            <span className="text-foreground truncate font-medium">{c.label}</span>
          ) : (
            <>
              <Link
                href={c.href}
                className="text-muted-foreground hover:text-foreground truncate transition-colors"
              >
                {c.label}
              </Link>
              <ChevronRight className="text-muted-foreground/50 size-3.5 shrink-0" aria-hidden />
            </>
          )}
        </span>
      ))}
    </nav>
  );
}
