import { RefreshCw } from "lucide-react";
import { NavList } from "@/components/nav-list";
import type { Role } from "@/lib/session";

export function AppSidebar({ role }: { role: Role }) {
  return (
    <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border relative hidden w-60 shrink-0 flex-col border-r md:flex">
      {/* a faint brand wash at the top of the rail */}
      <div aria-hidden className="from-primary/8 pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b to-transparent" />

      {/* Brand */}
      <div className="relative flex h-16 items-center gap-2.5 px-5">
        <div className="from-primary ring-primary/15 flex size-8 items-center justify-center rounded-lg bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-white shadow-sm ring-4">
          <RefreshCw className="size-4" strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <div className="text-[15px] font-semibold tracking-tight">Feedback Loop</div>
          <div className="text-muted-foreground text-[11px]">Interview Kickstart</div>
        </div>
      </div>

      <div className="relative min-h-0 flex-1 overflow-y-auto">
        <NavList role={role} />
      </div>

      <div className="border-sidebar-border relative space-y-2 border-t px-5 py-3">
        <div className="text-muted-foreground/70 flex items-center justify-between text-[11px]">
          <span>Search anything</span>
          <kbd className="rounded-md border px-1.5 py-px font-mono text-[10px]">⌘K</kbd>
        </div>
        <div className="text-muted-foreground/60 text-[11px]">AI drafts · humans approve</div>
      </div>
    </aside>
  );
}
