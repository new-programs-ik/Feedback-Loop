import type { Metadata } from "next";
import { listCourses, resolveWorkspace } from "@/lib/workspace";
import { WorkspaceProvider } from "@/lib/workspace-context";

type Props = { children: React.ReactNode; params: Promise<{ course: string }> };

export async function generateMetadata({ params }: { params: Promise<{ course: string }> }): Promise<Metadata> {
  const { course } = await params;
  const ws = await resolveWorkspace(course);
  return { title: { default: ws.courseName, template: `%s · ${ws.courseName}` } };
}

/** The course workspace: `/c/<slug>/…`. Resolves the course (404 on an unknown slug), the
 *  member's role and the course list once, and hands them to every page beneath. */
export default async function CourseLayout({ children, params }: Props) {
  const { course } = await params;
  const [ws, courses] = await Promise.all([resolveWorkspace(course), listCourses()]);
  return (
    <WorkspaceProvider courses={courses} defaultSlug={ws.slug} workspace={ws}>
      {children}
    </WorkspaceProvider>
  );
}
