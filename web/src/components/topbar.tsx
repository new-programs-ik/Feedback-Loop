import { Badge } from "@/components/ui/badge";
import { LogoutButton } from "@/components/logout-button";
import type { SessionUser } from "@/lib/session";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "U";
}

export function Topbar({ user }: { user: SessionUser }) {
  return (
    <header className="bg-background/80 sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b px-4 backdrop-blur-sm md:px-8">
      <div className="font-semibold tracking-tight md:hidden">Feedback Loop</div>
      <div className="flex-1" />
      <div className="flex items-center gap-3">
        <Badge variant="secondary" className="hidden capitalize sm:inline-flex">
          {user.role === "pm" ? "Program Manager" : user.role}
        </Badge>
        <div className="hidden text-right leading-tight sm:block">
          <div className="text-sm font-medium">{user.name}</div>
          {user.name !== user.email && (
            <div className="text-muted-foreground text-xs">{user.email}</div>
          )}
        </div>
        <div className="from-primary/90 flex size-9 items-center justify-center rounded-full bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-[13px] font-semibold text-white shadow-sm">
          {initials(user.name)}
        </div>
        <LogoutButton />
      </div>
    </header>
  );
}
