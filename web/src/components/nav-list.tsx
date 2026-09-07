"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";
import { isActive, navForRole } from "@/lib/nav";
import { useWorkspace } from "@/lib/workspace-context";
import type { Role } from "@/lib/session";

/** The navigation sections + items, shared verbatim by the desktop sidebar and the mobile
 *  drawer so the two can never drift apart. The items follow the current workspace (a course, or
 *  the team level). The active highlight is ONE element that slides between items. */
export function NavList({ role, onNavigate, id = "sidebar" }: { role: Role; onNavigate?: () => void; id?: string }) {
  const pathname = usePathname();
  const ws = useWorkspace();
  const sections = navForRole(role, ws.slug);
  const reduce = useReducedMotion();

  return (
    <LayoutGroup id={id}>
      <nav className="space-y-5 px-3 pt-3 pb-4">
        {sections.map((section, i) => (
          <div key={section.title ?? i} className="space-y-0.5">
            {section.title && (
              <div className="text-muted-foreground/80 px-3 pb-1.5 text-[10.5px] font-semibold tracking-[0.08em] uppercase">
                {section.title}
              </div>
            )}
            {section.items.map((item) => {
              const active = isActive(item, pathname);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group relative flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px] transition-colors duration-150",
                    active ? "text-sidebar-accent-foreground font-semibold" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId={`${id}-active`}
                      className="bg-sidebar-accent absolute inset-0 rounded-lg"
                      transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 38, mass: 0.6 }}
                    />
                  )}
                  {!active && (
                    <span className="bg-sidebar-accent/0 group-hover:bg-sidebar-accent/50 absolute inset-0 rounded-lg transition-colors duration-150" />
                  )}
                  {active && (
                    <motion.span
                      layoutId={`${id}-bar`}
                      className="bg-primary absolute top-1/2 left-0 h-4 w-0.5 -translate-y-1/2 rounded-r-full"
                      transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 38, mass: 0.6 }}
                    />
                  )}
                  <Icon
                    className={cn("relative size-4 shrink-0", active ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground")}
                    strokeWidth={active ? 2.25 : 2}
                  />
                  <span className="relative flex-1 truncate">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </LayoutGroup>
  );
}
