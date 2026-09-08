import { redirect } from "next/navigation";
import { resolveWorkspace } from "@/lib/workspace";

/** The AI engine lives at the root (`/feedback/new`, unchanged); inside a workspace the link
 *  carries the course along. */
export default async function NewAnalysisInCourse({
  params,
  searchParams,
}: {
  params: Promise<{ course: string }>;
  searchParams: Promise<{ prefill?: string }>;
}) {
  const { course } = await params;
  const sp = await searchParams;
  const ws = await resolveWorkspace(course);
  const qs = new URLSearchParams();
  if (ws.courseId) qs.set("course", ws.courseId);
  if (sp.prefill) qs.set("prefill", sp.prefill);
  const q = qs.toString();
  redirect(q ? `/feedback/new?${q}` : "/feedback/new");
}
