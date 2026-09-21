import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { TEAM_SLUG, getDefaultWorkspace, hrefIn, listCourses } from "@/lib/workspace";

/** `/feedback` has no list of its own: analyses live per course. This sends the person to the
 *  right course's list (a `?course=<id|slug>` wins, then their usual workspace, then their first
 *  course). Approve/Discard/Delete and old links land here, so it must always resolve. */
export default async function FeedbackIndex({
  searchParams,
}: {
  searchParams: Promise<{ course?: string | string[] }>;
}) {
  const user = await requireUser();
  const { course: param } = await searchParams;
  const wanted = Array.isArray(param) ? param[0] : param;
  const courses = await listCourses();
  const picked = wanted ? courses.find((c) => c.id === wanted || c.slug === wanted) : undefined;
  let slug = picked?.slug ?? (await getDefaultWorkspace(user));
  if (slug === TEAM_SLUG) slug = courses.find((c) => c.mine)?.slug ?? courses[0]?.slug ?? TEAM_SLUG;
  redirect(slug === TEAM_SLUG ? "/team" : hrefIn(slug, "/feedback"));
}
