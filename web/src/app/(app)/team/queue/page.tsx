import { QueuePage, type QueueSearchParams } from "@/components/queue/queue-page";
import { TEAM_SLUG } from "@/lib/workspace";

export const metadata = { title: "Queue" };

/** Every course's queue on one page, with course chips to narrow it. */
export default async function TeamQueuePage({ searchParams }: { searchParams: Promise<QueueSearchParams> }) {
  const sp = await searchParams;
  return <QueuePage courseId={null} slug={TEAM_SLUG} sp={sp} />;
}
