import { notFound, redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { TEAM_SLUG, getDefaultWorkspace, hrefIn, listCourses } from "@/lib/workspace";

/** Old URLs keep working for a month (Slack links in flight): `/ratings?course=<uuid>&focus=…`
 *  becomes `/c/<slug>/queue?focus=…`, and so on. Anything outside the allow-list is a real 404. */
const ALLOW = new Set([
  "dashboard", "ratings", "feedback", "course-analytics", "instructor-analytics", "reports", "insights", "courses", "instructors",
]);
const KEEP = ["focus", "range", "from", "to", "sme", "sort", "dir", "class", "page", "month", "status", "band", "kind", "cohort", "instructor", "prefill"];

type SP = Record<string, string | string[] | undefined>;
const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default async function LegacyRedirect({
  params,
  searchParams,
}: {
  params: Promise<{ legacy: string[] }>;
  searchParams: Promise<SP>;
}) {
  const { legacy } = await params;
  const sp = await searchParams;
  const [head, ...rest] = legacy;
  if (!head || !ALLOW.has(head) || rest.length > 0) notFound();

  const user = await requireUser();
  const courses = await listCourses();
  const courseParam = first(sp.course);
  const course = courseParam ? courses.find((c) => c.id === courseParam || c.slug === courseParam) : undefined;
  let slug = course?.slug ?? (await getDefaultWorkspace(user));
  const isTeam = slug === TEAM_SLUG;
  // Pages that only exist inside a course fall back to the person's first course.
  const firstCourse = courses.find((c) => c.mine)?.slug ?? courses[0]?.slug ?? null;

  const qs = new URLSearchParams();
  for (const k of KEEP) {
    const v = first(sp[k]);
    if (v) qs.set(k, v);
  }

  let target: string;
  switch (head) {
    case "dashboard":
    case "course-analytics":
      target = hrefIn(slug, "/overview");
      break;
    case "ratings":
      target = hrefIn(slug, "/queue");
      break;
    case "feedback":
      if (isTeam) slug = firstCourse ?? TEAM_SLUG;
      target = slug === TEAM_SLUG ? "/team" : hrefIn(slug, "/feedback");
      break;
    case "instructor-analytics":
      target = hrefIn(slug, "/instructors");
      break;
    case "reports":
      target = hrefIn(slug, "/reports");
      break;
    case "insights":
      target = "/team/insights";
      break;
    case "courses":
      target = "/admin/people";
      break;
    case "instructors":
      target = "/admin/identity";
      break;
    default:
      notFound();
  }
  const query = qs.toString();
  redirect(query ? `${target}?${query}` : target);
}
