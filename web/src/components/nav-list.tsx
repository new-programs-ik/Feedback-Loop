"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { navForRole } from "@/lib/nav";
import type { Role } from "@/lib/session";

/** The navigation sections + items, shared verbatim by the desktop sidebar and the mobile
 *  drawer so the two can never drift apart. */
export function NavList({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const pathname = usePathname();
  const sections = navForRole(role);

  return (
    <nav className="space-y-5 px-3 pt-2 pb-4">
      {sections.map((section, i) => (
        <div key={i} className="space-y-0.5">
          {section.title && (
            <div className="text-muted-foreground/80 px-3 pb-1.5 text-[10.5px] font-semibold tracking-[0.08em] uppercase">
              {section.title}
            </div>
          )}
          {section.items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] transition-all duration-150",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
                    : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-foreground",
                )}
              >
                {active && (
                  <span className="bg-primary absolute top-1/2 left-0 h-5 w-1 -translate-y-1/2 rounded-r-full" />
                )}
                <Icon
                  className={cn(
                    "size-4 shrink-0 transition-colors",
                    active ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground",
                  )}
                  strokeWidth={active ? 2.25 : 2}
                />
                <span className="flex-1 truncate">{item.label}</span>
                {!item.live && (
                  <span className="text-muted-foreground/70 rounded-full border px-1.5 py-px text-[9.5px] font-medium">
                    soon
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
