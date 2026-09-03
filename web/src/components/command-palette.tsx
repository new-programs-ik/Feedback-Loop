"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import {
  BookOpen, GraduationCap, Library, ListChecks, Moon, RefreshCw, Search, Sun, SunMoon,
  CornerDownLeft, type LucideIcon,
} from "lucide-react";
import { navForRole } from "@/lib/nav";
import type { Role } from "@/lib/session";
import { cn } from "@/lib/utils";

export const OPEN_PALETTE_EVENT = "feedback-loop:open-palette";

/** Anything can open the palette without prop-drilling: `openCommandPalette()`. */
export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(OPEN_PALETTE_EVENT));
}

type Course = { id: string; name: string };
type Instructor = { id: string; name: string };

function setTheme(mode: "light" | "dark" | "system") {
  if (mode === "system") localStorage.removeItem("theme");
  else localStorage.setItem("theme", mode);
  const dark = mode === "dark" || (mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  window.dispatchEvent(new Event("theme-change"));
}

/** ⌘K / Ctrl-K: jump to any page, course or instructor; run Sync now; switch theme. */
export function CommandPalette({
  role,
  courses,
  instructors,
  syncNow,
}: {
  role: Role;
  courses: Course[];
  instructors: Instructor[];
  syncNow?: () => Promise<void>;
}) {
  const router = useRouter();
  const reduce = useReducedMotion();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [pending, startTransition] = React.useTransition();

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_PALETTE_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_PALETTE_EVENT, onOpen);
    };
  }, []);

  React.useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  const runSync = () => {
    if (!syncNow) return;
    setOpen(false);
    startTransition(async () => {
      try {
        await syncNow();
        toast.success("Sync requested", { description: "The ratings sheet is being read now — the queue refreshes in a moment." });
      } catch (e) {
        toast.error("Sync could not start", { description: e instanceof Error ? e.message : String(e) });
      }
    });
  };

  const pages = navForRole(role).flatMap((s) => s.items.filter((i) => i.live));

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette"
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4 pt-[12vh] backdrop-blur-[2px]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <motion.div
            className="bg-popover text-popover-foreground shadow-pop w-full max-w-xl overflow-hidden rounded-2xl border"
            initial={reduce ? false : { opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? undefined : { opacity: 0, y: -6, scale: 0.985 }}
            transition={{ type: "spring", stiffness: 520, damping: 42, mass: 0.7 }}
            role="dialog"
            aria-label="Command palette"
          >
            <Command
              label="Command palette"
              loop
              onKeyDown={(e) => {
                if (e.key === "Escape") setOpen(false);
              }}
            >
              <div className="flex items-center gap-2.5 border-b px-4">
                <Search className="text-muted-foreground size-4 shrink-0" aria-hidden />
                <Command.Input
                  autoFocus
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Jump to a page, course or instructor…"
                  className="placeholder:text-muted-foreground h-12 w-full bg-transparent text-[14px] outline-none"
                />
                <kbd className="text-muted-foreground hidden rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] sm:inline">esc</kbd>
              </div>
              <Command.List className="max-h-[56vh] overflow-y-auto p-2 [scrollbar-width:thin]">
                <Command.Empty className="text-muted-foreground px-3 py-8 text-center text-sm">
                  Nothing matches “{query}”.
                </Command.Empty>

                <Group heading="Go to">
                  {pages.map((p) => (
                    <Item key={p.href} icon={p.icon} onSelect={() => go(p.href)} value={`page ${p.label}`}>
                      {p.label}
                    </Item>
                  ))}
                </Group>

                {syncNow && (
                  <Group heading="Actions">
                    <Item icon={RefreshCw} onSelect={runSync} value="sync now ratings sheet" hint={pending ? "running…" : "worker"}>
                      Sync ratings now
                    </Item>
                  </Group>
                )}

                <Group heading="Courses">
                  {courses.map((c) => (
                    <Item key={c.id} icon={Library} onSelect={() => go(`/reports?range=monthly&course=${c.id}`)} value={`course ${c.name}`} hint="report">
                      {c.name}
                    </Item>
                  ))}
                  {courses.map((c) => (
                    <Item key={c.id + "-q"} icon={ListChecks} onSelect={() => go(`/ratings?course=${c.id}`)} value={`queue ${c.name}`} hint="queue">
                      {c.name}
                    </Item>
                  ))}
                  {courses.map((c) => (
                    <Item key={c.id + "-a"} icon={BookOpen} onSelect={() => go(`/course-analytics?course=${c.id}`)} value={`analytics ${c.name}`} hint="analytics">
                      {c.name}
                    </Item>
                  ))}
                </Group>

                <Group heading="Instructors">
                  {instructors.map((i) => (
                    <Item
                      key={i.id}
                      icon={GraduationCap}
                      onSelect={() => go(`/instructor-analytics?range=custom&from=2026-01-01&to=2026-12-31&sme=${encodeURIComponent(i.name)}`)}
                      value={`instructor ${i.name}`}
                    >
                      {i.name}
                    </Item>
                  ))}
                </Group>

                <Group heading="Appearance">
                  <Item icon={Sun} onSelect={() => { setTheme("light"); setOpen(false); }} value="theme light">Light theme</Item>
                  <Item icon={Moon} onSelect={() => { setTheme("dark"); setOpen(false); }} value="theme dark">Dark theme</Item>
                  <Item icon={SunMoon} onSelect={() => { setTheme("system"); setOpen(false); }} value="theme system follow os">Follow the system</Item>
                </Group>
              </Command.List>
              <div className="text-muted-foreground flex items-center justify-between border-t px-4 py-2 text-[11px]">
                <span>
                  <kbd className="rounded border px-1 font-mono">↑</kbd> <kbd className="rounded border px-1 font-mono">↓</kbd> to move
                  &nbsp;·&nbsp; <kbd className="rounded border px-1 font-mono">↵</kbd> to open
                </span>
                <span className="font-mono">⌘K</span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Group({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <Command.Group
      heading={heading}
      className="[&_[cmdk-group-heading]]:text-muted-foreground/80 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10.5px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:uppercase"
    >
      {children}
    </Command.Group>
  );
}

function Item({
  icon: Icon,
  children,
  onSelect,
  value,
  hint,
}: {
  icon: LucideIcon;
  children: React.ReactNode;
  onSelect: () => void;
  value: string;
  hint?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors",
        "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground",
      )}
    >
      <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
      <span className="flex-1 truncate">{children}</span>
      {hint && <span className="text-muted-foreground/70 text-[10.5px]">{hint}</span>}
      <CornerDownLeft className="text-muted-foreground/50 size-3 opacity-0 data-[selected=true]:opacity-100" aria-hidden />
    </Command.Item>
  );
}
