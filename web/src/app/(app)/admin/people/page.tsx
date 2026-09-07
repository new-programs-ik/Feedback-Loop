import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { getCourses, listCohorts, listMembers, listShares, listStaffProfiles } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { AdminNav } from "@/components/admin/admin-nav";
import { PeopleMatrix } from "@/components/admin/people/people-matrix";
import { CourseIdentityEditor } from "@/components/admin/people/course-identity";
import { ShareLinks } from "@/components/admin/share-links";

export const metadata = { title: "People" };

/** /admin/people — who owns what. The people × courses matrix, the course identity editor and
 *  every share link across courses. */
export default async function PeoplePage() {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  const [courses, members, cohorts, staff, shares] = await Promise.all([getCourses(), listMembers(), listCohorts(), listStaffProfiles(), listShares(null)]);
  const handlers = members.rows.filter((m) => m.is_handler).length;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="People and ownership"
        description={`${members.rows.length} memberships across ${courses.length} courses · ${handlers} of ${courses.length} courses have a handler`}
      />
      <AdminNav />
      {members.error && (
        <p className="border-warning/40 bg-warning/5 mb-4 rounded-md border px-3 py-2 text-[12.5px]">
          Course membership is not available yet ({members.error}) — the <code className="font-mono text-[11.5px]">course_members</code> table arrives with migration 0018.
        </p>
      )}
      <div className="space-y-8">
        <section className="space-y-3" aria-labelledby="matrix-title">
          <h2 id="matrix-title" className="text-[15px] font-semibold tracking-[-0.01em]">People × courses</h2>
          <PeopleMatrix courses={courses} members={members.rows} cohorts={cohorts.rows} staff={staff} />
        </section>
        <section className="space-y-3" aria-labelledby="identity-title">
          <h2 id="identity-title" className="text-[15px] font-semibold tracking-[-0.01em]">Course identity</h2>
          <p className="text-muted-foreground -mt-2 text-[12.5px]">One of eight colours and up to three initials — used only as the identity square, never for data.</p>
          <CourseIdentityEditor courses={courses} />
        </section>
        <section className="space-y-3" aria-labelledby="shares-title">
          <h2 id="shares-title" className="text-[15px] font-semibold tracking-[-0.01em]">Share links</h2>
          {shares.error && <p className="text-muted-foreground text-[12px]">Share links are not available yet ({shares.error}).</p>}
          <ShareLinks shares={shares.rows} courseId={null} courses={courses} canCreate={!shares.error} />
        </section>
      </div>
    </div>
  );
}
