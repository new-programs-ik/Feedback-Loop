import { Badge } from "@/components/ui/badge";
import { LogoutButton } from "@/components/logout-button";
import { MobileNav } from "@/components/mobile-nav";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { ThemeToggle } from "@/components/theme-toggle";
import { SearchButton } from "@/components/search-button";
import type { SessionUser } from "@/lib/session";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "U";
}

export function Topbar({ user }: { user: SessionUser }) {
  return (
    <header
      data-print-hide
      className="glass sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b px-4 md:px-8"
    >
      <div className="flex min-w-0 items-center gap-3">
        <MobileNav role={user.role} />
        <div className="font-semibold tracking-tight md:hidden">Feedback Loop</div>
        <Breadcrumbs />
      </div>
      <div className="flex items-center gap-2.5">
        <SearchButton />
        <ThemeToggle />
        <Badge variant="secondary" className="hidden capitalize lg:inline-flex">
          {user.role === "pm" ? "Program Manager" : user.role}
        </Badge>
        <div className="hidden text-right leading-tight sm:block">
          <div className="text-sm font-medium">{user.name}</div>
          {user.name !== user.email && <div className="text-muted-foreground text-xs">{user.email}</div>}
        </div>
        <div className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-full text-[12px] font-semibold" aria-hidden>
          {initials(user.name)}
        </div>
        <LogoutButton />
      </div>
    </header>
  );
}
