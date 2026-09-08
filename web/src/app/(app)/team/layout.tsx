import type { Metadata } from "next";
import { TEAM_SLUG, listCourses, resolveWorkspace } from "@/lib/workspace";
import { WorkspaceProvider } from "@/lib/workspace-context";

export const metadata: Metadata = { title: { default: "All courses", template: "%s · All courses" } };

/** The leadership level: `/team/…` — every course at once. Same provider as a course
 *  workspace, with the course set to null. */
export default async function TeamLayout({ children }: { children: React.ReactNode }) {
  const [ws, courses] = await Promise.all([resolveWorkspace(TEAM_SLUG), listCourses()]);
  return (
    <WorkspaceProvider courses={courses} defaultSlug={TEAM_SLUG} workspace={ws}>
      {children}
    </WorkspaceProvider>
  );
}
