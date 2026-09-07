"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { GLOBAL_LABELS, labelForPage } from "@/lib/nav";
import { hrefIn, pageFromPath, slugFromPath, useWorkspace } from "@/lib/workspace-context";

const looksLikeId = (seg: string) => /^[0-9a-f-]{16,}$/i.test(seg);

/** Topbar breadcrumbs: the course name first, then the page, then "Details" for ids (the page
 *  shows the real name in its own header). Hidden when there is only the workspace root. */
export function Breadcrumbs() {
  const pathname = usePathname();
  const ws = useWorkspace();
  const inWorkspace = slugFromPath(pathname) !== null;

  const crumbs: { href: string; label: string }[] = [];
  if (inWorkspace) {
    crumbs.push({ href: hrefIn(ws.slug, "/overview"), label: ws.courseName });
    const page = pageFromPath(pathname) ?? "/overview";
    const segs = page.split("/").filter(Boolean);
    segs.forEach((seg, i) => {
      if (i === 0 && seg === "overview") return;
      const href = hrefIn(ws.slug, "/" + segs.slice(0, i + 1).join("/"));
      const label =
        i === 0
          ? (labelForPage("/" + seg, ws.isTeam) ?? GLOBAL_LABELS[seg] ?? seg.replace(/-/g, " "))
          : looksLikeId(seg)
            ? "Details"
            : (GLOBAL_LABELS[seg] ?? seg.replace(/-/g, " "));
      crumbs.push({ href, label });
    });
  } else {
    const segs = pathname.split("/").filter(Boolean);
    segs.forEach((seg, i) => {
      const href = "/" + segs.slice(0, i + 1).join("/");
      const label = looksLikeId(seg) ? "Details" : (GLOBAL_LABELS[seg] ?? seg.replace(/-/g, " "));
      crumbs.push({ href, label });
    });
  }
  if (crumbs.length < 2) return null;

  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-sm sm:flex">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={c.href + i} className="flex min-w-0 items-center gap-1">
            {last ? (
              <span className="text-foreground truncate font-medium">{c.label}</span>
            ) : (
              <>
                <Link href={c.href} className="text-muted-foreground hover:text-foreground truncate transition-colors">
                  {c.label}
                </Link>
                <ChevronRight className="text-muted-foreground/50 size-3.5 shrink-0" aria-hidden />
              </>
            )}
          </span>
        );
      })}
    </nav>
  );
}
