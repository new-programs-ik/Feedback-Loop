"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { navForRole } from "@/lib/nav";
import { Badge } from "@/components/ui/badge";
import type { Role } from "@/lib/session";

export function AppSidebar({ role }: { role: Role }) {
  const pathname = usePathname();
  const sections = navForRole(role);

  return (
    <aside className="bg-sidebar text-sidebar-foreground hidden w-64 shrink-0 flex-col border-r md:flex">
      <div className="flex h-14 items-center gap-2 border-b px-5">
        <div className="bg-primary size-6 rounded" />
        <span className="font-semibold">IK · New Programs</span>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto p-3">
        {sections.map((section, i) => (
          <div key={i} className="space-y-1">
            {section.title && (
              <div className="text-muted-foreground px-2 text-xs font-medium uppercase tracking-wider">
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
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                  )}
                >
                  <Icon className="size-4 shrink-0" />
                  <span className="flex-1">{item.label}</span>
                  {!item.live && (
                    <Badge variant="outline" className="px-1 py-0 text-[10px]">
                      soon
                    </Badge>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
