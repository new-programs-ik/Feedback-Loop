import { Badge } from "@/components/ui/badge";
import { LogoutButton } from "@/components/logout-button";
import type { SessionUser } from "@/lib/session";

export function Topbar({ user }: { user: SessionUser }) {
  return (
    <header className="flex h-14 items-center justify-between gap-4 border-b px-4 md:px-6">
      <div className="font-semibold md:hidden">IK · NP</div>
      <div className="flex-1" />
      <div className="flex items-center gap-3">
        <Badge variant="outline" className="capitalize">
          {user.role}
        </Badge>
        <div className="text-right leading-tight">
          <div className="text-sm font-medium">{user.name}</div>
          <div className="text-muted-foreground text-xs">{user.email}</div>
        </div>
        <div className="bg-muted size-8 rounded-full" />
        <LogoutButton />
      </div>
    </header>
  );
}
