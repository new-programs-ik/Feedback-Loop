"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { Check, ChevronsUpDown, Building2 } from "lucide-react";
import { setWorkspace } from "@/lib/workspace-actions";
import { TEAM_SLUG, hrefIn, pageFromPath, useWorkspace, type CourseSummary } from "@/lib/workspace-context";
import { TEAM_NAV, WORKSPACE_NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** The course identity square: colour + initials. */
export function CourseMark({
  color,
  initials,
  size = "md",
  className,
}: {
  color: string;
  initials: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const dims = { sm: "size-6 text-[9px]", md: "size-8 text-[11px]", lg: "size-10 text-[13px]" }[size];
  return (
    <span
      aria-hidden
      className={cn("flex shrink-0 items-center justify-center rounded-md font-semibold tracking-wide text-white", dims, className)}
      style={{ background: color }}
    >
      {initials}
    </span>
  );
}

const TEAM_PAGES = new Set(TEAM_NAV.map((i) => i.path));
const COURSE_PAGES = new Set(WORKSPACE_NAV.map((i) => i.path));

/** Where the same page lives in another workspace (the drawer/detail tail is dropped). */
function samePageIn(slug: string, pathname: string): string {
  const page = pageFromPath(pathname) ?? "/overview";
  const head = "/" + (page.split("/").filter(Boolean)[0] ?? "overview");
  const allowed = slug === TEAM_SLUG ? TEAM_PAGES : COURSE_PAGES;
  return hrefIn(slug, allowed.has(head) ? head : "/overview");
}

/** The identity block at the top of the rail: colour square, course name, "n cohorts · handler …".
 *  Click (or ⌘K → "Switch to") opens the switcher — My courses, then all courses, then the team
 *  level pinned at the bottom. ⌘1–9 jump straight to a course; ⌘0 to the team level. */
export function WorkspaceSwitcher({ className }: { className?: string }) {
  const ws = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);
  const [, startTransition] = React.useTransition();
  const root = React.useRef<HTMLDivElement>(null);
  const listRef = React.useRef<HTMLDivElement>(null);
  const listId = React.useId();

  const mine = ws.courses.filter((c) => c.mine);
  const others = ws.courses.filter((c) => !c.mine);
  const ordered = React.useMemo(() => [...mine, ...others], [mine, others]);

  const go = React.useCallback(
    (slug: string) => {
      setOpen(false);
      const href = samePageIn(slug, pathname);
      startTransition(async () => {
        try {
          await setWorkspace(slug);
        } catch {
          // the cookie is a convenience; the proxy sets it again on arrival
        }
        router.push(href);
      });
    },
    [pathname, router],
  );

  // ⌘1–9 → the nth course in the list, ⌘0 → the team level. Browsers keep some of these for tab
  // switching; where they let the page see the key, it works.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return;
      if (!/^[0-9]$/.test(e.key)) return;
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      const n = Number(e.key);
      if (n === 0) {
        e.preventDefault();
        go(TEAM_SLUG);
        return;
      }
      const course = ordered[n - 1];
      if (!course) return;
      e.preventDefault();
      go(course.slug);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ordered, go]);

  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const items = [...(listRef.current?.querySelectorAll<HTMLButtonElement>("[data-ws-item]") ?? [])];
        if (!items.length) return;
        e.preventDefault();
        const i = items.indexOf(document.activeElement as HTMLButtonElement);
        const next = e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
        items[next].focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    // focus the current entry
    const current = listRef.current?.querySelector<HTMLButtonElement>("[data-ws-item][aria-current=true]");
    (current ?? listRef.current?.querySelector<HTMLButtonElement>("[data-ws-item]"))?.focus();
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const meta = ws.isTeam
    ? `leadership view · ${ws.courses.length} ${ws.courses.length === 1 ? "course" : "courses"}`
    : [`${ws.cohorts} ${ws.cohorts === 1 ? "cohort" : "cohorts"}`, ws.handler ? `handler ${ws.handler}` : "no handler set"].join(" · ");

  return (
    <div ref={root} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        className="hover:bg-sidebar-accent/60 focus-visible:ring-ring/50 flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        {ws.isTeam ? (
          <span className="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-md" aria-hidden>
            <Building2 className="size-4" />
          </span>
        ) : (
          <CourseMark color={ws.color} initials={ws.initials} />
        )}
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[13px] font-semibold tracking-[-0.01em]">{ws.courseName}</span>
          <span className="text-muted-foreground block truncate text-[11px]">{meta}</span>
        </span>
        <ChevronsUpDown className="text-muted-foreground/70 size-3.5 shrink-0" aria-hidden />
      </button>

      {open && (
        <div
          id={listId}
          ref={listRef}
          role="listbox"
          aria-label="Switch workspace"
          className="bg-popover text-popover-foreground shadow-pop absolute inset-x-0 top-full z-40 mt-1 flex max-h-[70vh] flex-col overflow-hidden rounded-xl border"
        >
          <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
            {mine.length > 0 && <Group label="My courses" items={mine} offset={0} current={ws.slug} onPick={go} />}
            {others.length > 0 && (
              <Group label={mine.length ? "All courses" : "Courses"} items={others} offset={mine.length} current={ws.slug} onPick={go} />
            )}
            {ws.courses.length === 0 && <p className="text-muted-foreground px-2.5 py-3 text-[12px]">No courses yet.</p>}
          </div>
          <div className="border-t p-1.5">
            <button
              type="button"
              role="option"
              aria-selected={ws.isTeam}
              aria-current={ws.isTeam ? "true" : undefined}
              data-ws-item
              onClick={() => go(TEAM_SLUG)}
              className={cn(
                "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] transition-colors",
                "hover:bg-accent focus-visible:bg-accent focus-visible:outline-none",
                ws.isTeam && "font-semibold",
              )}
            >
              <span className="bg-primary text-primary-foreground flex size-6 shrink-0 items-center justify-center rounded-md" aria-hidden>
                <Building2 className="size-3.5" />
              </span>
              <span className="flex-1 truncate">All courses (team)</span>
              <kbd className="text-muted-foreground/70 rounded border px-1 font-mono text-[10px]">⌘0</kbd>
              {ws.isTeam && <Check className="text-primary size-3.5" aria-hidden />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Group({
  label,
  items,
  offset,
  current,
  onPick,
}: {
  label: string;
  items: CourseSummary[];
  offset: number;
  current: string;
  onPick: (slug: string) => void;
}) {
  return (
    <div className="mb-1">
      <div className="text-muted-foreground/80 px-2.5 pt-1.5 pb-1 text-[10.5px] font-semibold tracking-[0.08em] uppercase">{label}</div>
      {items.map((c, i) => {
        const n = offset + i + 1;
        const active = c.slug === current;
        return (
          <button
            key={c.id}
            type="button"
            role="option"
            aria-selected={active}
            aria-current={active ? "true" : undefined}
            data-ws-item
            onClick={() => onPick(c.slug)}
            className={cn(
              "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] transition-colors",
              "hover:bg-accent focus-visible:bg-accent focus-visible:outline-none",
              active && "font-semibold",
            )}
          >
            <CourseMark color={c.color} initials={c.initials} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate">{c.name}</span>
              <span className="text-muted-foreground block truncate text-[11px] font-normal">
                {c.cohorts} {c.cohorts === 1 ? "cohort" : "cohorts"}
                {c.handler ? ` · ${c.handler}` : ""}
              </span>
            </span>
            {n <= 9 && <kbd className="text-muted-foreground/70 rounded border px-1 font-mono text-[10px]">⌘{n}</kbd>}
            {active && <Check className="text-primary size-3.5" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}
