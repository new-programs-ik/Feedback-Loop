import { RefreshCw } from "lucide-react";
import { NavList } from "@/components/nav-list";
import type { Role } from "@/lib/session";

export function AppSidebar({ role }: { role: Role }) {
  return (
    <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border hidden w-60 shrink-0 flex-col border-r md:flex">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2.5 px-5">
        <div className="from-primary flex size-8 items-center justify-center rounded-lg bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-white shadow-sm">
          <RefreshCw className="size-4" strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <div className="text-[15px] font-semibold tracking-tight">Feedback Loop</div>
          <div className="text-muted-foreground text-[11px]">Interview Kickstart</div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <NavList role={role} />
      </div>

      <div className="text-muted-foreground/60 border-sidebar-border border-t px-5 py-3 text-[11px]">
        AI drafts · humans approve
      </div>
    </aside>
  );
}
