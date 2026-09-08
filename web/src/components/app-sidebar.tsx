import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { NavList } from "@/components/nav-list";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import type { Role } from "@/lib/session";

export function AppSidebar({ role }: { role: Role }) {
  return (
    <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border relative hidden w-60 shrink-0 flex-col border-r md:flex">
      {/* Brand */}
      <Link href="/" className="flex h-14 items-center gap-2.5 px-5">
        <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-md" aria-hidden>
          <RefreshCw className="size-3.5" strokeWidth={2.5} />
        </span>
        <span className="leading-tight">
          <span className="block text-[13px] font-semibold tracking-tight">Feedback Loop</span>
          <span className="text-muted-foreground block text-[10.5px]">Interview Kickstart · New Programs</span>
        </span>
      </Link>

      {/* Workspace identity + switcher */}
      <div className="border-sidebar-border border-y px-3 py-2">
        <WorkspaceSwitcher />
      </div>

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        <NavList role={role} />
      </div>

      <div className="border-sidebar-border relative space-y-1.5 border-t px-5 py-3">
        <div className="text-muted-foreground/70 flex items-center justify-between text-[11px]">
          <span>Search anything</span>
          <kbd className="rounded-md border px-1.5 py-px font-mono text-[10px]">⌘K</kbd>
        </div>
        <div className="text-muted-foreground/70 flex items-center justify-between text-[11px]">
          <span>Switch course</span>
          <kbd className="rounded-md border px-1.5 py-px font-mono text-[10px]">⌘1–9</kbd>
        </div>
      </div>
    </aside>
  );
}
