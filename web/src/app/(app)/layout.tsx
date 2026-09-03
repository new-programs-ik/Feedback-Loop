import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { AppSidebar } from "@/components/app-sidebar";
import { Topbar } from "@/components/topbar";
import { CommandPalette } from "@/components/command-palette";
import { AppToaster } from "@/components/app-toaster";
import { AppMotionConfig } from "@/components/motion/motion-config";
import { syncNow } from "@/app/(app)/ratings/actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await requireUser();
  const supabase = await createClient();
  const [coursesRes, instructorsRes] = await Promise.all([
    supabase.from("courses").select("id, name").order("name"),
    supabase.from("instructors").select("id, name").order("name"),
  ]);
  const staff = user.role === "admin" || user.role === "pm";

  return (
    <AppMotionConfig>
    <div className="flex min-h-screen">
      <AppSidebar role={user.role} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* a whisper of colour behind the content — the page never reads as a flat grey sheet */}
        <div aria-hidden className="bg-mesh pointer-events-none absolute inset-x-0 top-0 h-[520px] opacity-70" />
        <Topbar user={user} />
        <main className="relative flex-1 p-4 md:p-8">{children}</main>
      </div>
      <CommandPalette
        role={user.role}
        courses={coursesRes.data ?? []}
        instructors={staff ? (instructorsRes.data ?? []) : []}
        syncNow={staff ? syncNow : undefined}
      />
      <AppToaster />
    </div>
    </AppMotionConfig>
  );
}
