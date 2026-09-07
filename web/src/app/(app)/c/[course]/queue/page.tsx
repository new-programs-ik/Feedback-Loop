import { QueuePage, type QueueSearchParams } from "@/components/queue/queue-page";
import { resolveWorkspace } from "@/lib/workspace";

export const metadata = { title: "Needs analysis" };

export default async function CourseQueuePage({
  params,
  searchParams,
}: {
  params: Promise<{ course: string }>;
  searchParams: Promise<QueueSearchParams>;
}) {
  const { course } = await params;
  const [ws, sp] = await Promise.all([resolveWorkspace(course), searchParams]);
  return <QueuePage courseId={ws.courseId} slug={ws.slug} sp={sp} />;
}
