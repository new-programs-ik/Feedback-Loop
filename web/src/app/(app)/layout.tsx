import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { getDefaultWorkspace, listCourses } from "@/lib/workspace";
import { WorkspaceProvider } from "@/lib/workspace-context";
import { AppSidebar } from "@/components/app-sidebar";
import { Topbar } from "@/components/topbar";
import { CommandPalette } from "@/components/command-palette";
import { AppToaster } from "@/components/app-toaster";
import { AppMotionConfig } from "@/components/motion/motion-config";
import { syncNow } from "@/app/(app)/c/[course]/queue/actions";

/** The app shell. The course list, the member's role in each course and the default workspace
 *  are loaded once per request (React cache) and shared with the sidebar, the palette and every
 *  page beneath; the provider derives the current workspace from the URL. */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await requireUser();
  const staff = user.role === "admin" || user.role === "pm";
  const supabase = await createClient();
  const [courses, defaultSlug, instructorsRes] = await Promise.all([
    listCourses(),
    getDefaultWorkspace(user),
    staff ? supabase.from("instructors").select("id, name").order("name") : Promise.resolve({ data: [] as { id: string; name: string }[] }),
  ]);

  return (
    <AppMotionConfig>
      <WorkspaceProvider courses={courses} defaultSlug={defaultSlug}>
        <div className="flex min-h-screen">
          <AppSidebar role={user.role} />
          <div className="relative flex min-w-0 flex-1 flex-col">
            <Topbar user={user} />
            <main className="relative flex-1 p-4 md:p-8">{children}</main>
          </div>
          <CommandPalette role={user.role} instructors={instructorsRes.data ?? []} syncNow={staff ? syncNow : undefined} />
          <AppToaster />
        </div>
      </WorkspaceProvider>
    </AppMotionConfig>
  );
}
