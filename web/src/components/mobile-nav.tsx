"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { Sheet } from "@/components/ui/sheet";
import { NavList } from "@/components/nav-list";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import type { Role } from "@/lib/session";

/** Hamburger + drawer for < md screens — the sidebar is hidden there. Same switcher and NavList
 *  as the desktop rail. The drawer remembers the path it was opened on, so a navigation (a link
 *  tapped inside it) closes it on its own. */
export function MobileNav({ role }: { role: Role }) {
  const pathname = usePathname();
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const open = openedAt === pathname;
  const close = () => setOpenedAt(null);

  return (
    <div className="md:hidden">
      <button
        type="button"
        onClick={() => setOpenedAt(pathname)}
        aria-label="Open navigation menu"
        className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 cursor-pointer items-center justify-center rounded-lg transition-colors"
      >
        <Menu className="size-5" aria-hidden />
      </button>
      <Sheet open={open} onClose={close} ariaLabel="Navigation menu" side="left">
        <div className="px-3 pb-1">
          <WorkspaceSwitcher />
        </div>
        <NavList id="mobile" role={role} onNavigate={close} />
      </Sheet>
    </div>
  );
}
