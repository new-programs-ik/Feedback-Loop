import { NextResponse, type NextRequest } from "next/server";
import { getCurrentUser } from "@/lib/session";
import { listCourses } from "@/lib/workspace";
import { fetchScored, reportPeriod, classReason, instructorName, type SearchParams } from "@/lib/analytics";
import { latestRatedDate } from "@/lib/ratings";

/** CSV of every scored class in the report's period, for one course (or every course when the
 *  slug is "team"). Same period parameters as the page: `?period=week|month|custom&from&to`. */
export async function GET(req: NextRequest, { params }: { params: Promise<{ course: string }> }) {
  const user = await getCurrentUser();
  if (!user || user.role === "learner") return new NextResponse("Unauthorized", { status: 401 });
  const { course: slug } = await params;
  const sp: SearchParams = Object.fromEntries(req.nextUrl.searchParams.entries());
  let courseId: string | null = null;
  let name = "all-courses";
  if (slug !== "team") {
    const courses = await listCourses();
    const course = courses.find((c) => c.slug === slug) ?? courses.find((c) => c.id === slug);
    if (!course) return new NextResponse("Unknown course", { status: 404 });
    courseId = course.id;
    name = course.slug;
  }
  const { from, to } = reportPeriod(sp, await latestRatedDate(courseId));
  const rows = await fetchScored({ from, to, courseId });
  const esc = (v: unknown) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = [
    "date", "course", "cohort", "kind", "class", "instructor", "instructor_recorded", "rating", "rated", "attended", "reach_pct",
    "yes_votes", "no_votes", "approval_pct", "score", "band", "action", "provisional", "scored_by", "review_status", "reason",
  ].join(",");
  const lines = rows.map((r) =>
    [
      r.class_date,
      esc(r.course_name ?? r.course_label),
      esc(r.cohort_text ?? ""),
      esc(r.session_kind),
      esc(r.topic),
      esc(instructorName(r)),
      esc(r.instructor),
      r.rating,
      r.num_ratings ?? "",
      r.attended ?? "",
      r.participation_pct ?? "",
      r.yes_votes ?? "",
      r.no_votes ?? "",
      r.approval_pct ?? "",
      r.score ?? "",
      r.band ?? "",
      r.decision_override ?? r.action,
      r.provisional ? "yes" : "",
      r.scored_by,
      r.review_status,
      esc(classReason(r)),
    ].join(","),
  );
  return new NextResponse([header, ...lines].join("\n"), {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${name}-${from}-to-${to}.csv"`,
    },
  });
}
