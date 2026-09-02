"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Menu, RefreshCw } from "lucide-react";
import { Sheet } from "@/components/ui/sheet";
import { NavList } from "@/components/nav-list";
import type { Role } from "@/lib/session";

/** Hamburger + drawer for < md screens — the sidebar is hidden there. Same NavList as desktop. */
export function MobileNav({ role }: { role: Role }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Route change (link tapped inside the drawer) closes it.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation menu"
        className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 cursor-pointer items-center justify-center rounded-lg transition-colors"
      >
        <Menu className="size-5" aria-hidden />
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} ariaLabel="Navigation menu">
        <div className="flex items-center gap-2.5 px-5 pb-2">
          <div className="from-primary flex size-8 items-center justify-center rounded-lg bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-white shadow-sm">
            <RefreshCw className="size-4" strokeWidth={2.5} />
          </div>
          <div className="text-[15px] font-semibold tracking-tight">Feedback Loop</div>
        </div>
        <NavList role={role} onNavigate={() => setOpen(false)} />
      </Sheet>
    </div>
  );
}
