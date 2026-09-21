import { notFound } from "next/navigation";
import { requireUser } from "@/lib/session";
import { resolveWorkspace } from "@/lib/workspace";
import { listCohorts, listMembers, listRawTopics, listShares, listStaffProfiles, listTopicAliases, listTopics, type CourseRow } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { SegmentedTabs } from "@/components/ui/tabs";
import { CourseSquare } from "@/components/admin/course-square";
import { TeamTab } from "@/components/admin/settings/team-tab";
import { CohortsTab } from "@/components/admin/settings/cohorts-tab";
import { ModulesTab } from "@/components/admin/settings/modules-tab";
import { NotificationsTab } from "@/components/admin/settings/notifications-tab";
import { ShareLinks } from "@/components/admin/share-links";

export const metadata = { title: "Settings" };

const TABS = ["team", "cohorts", "modules", "notifications", "shares"] as const;
type Tab = (typeof TABS)[number];

/** /c/[course]/settings — the course's own settings. Owners and admins edit; PMs and viewers
 *  read (everyone on the team can read every course — course is a label, not a wall). */
export default async function CourseSettingsPage({
  params,
  searchParams,
}: {
  params: Promise<{ course: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const user = await requireUser();
  const { course: slug } = await params;
  const sp = await searchParams;
  const tab: Tab = (TABS as readonly string[]).includes(sp.tab ?? "") ? (sp.tab as Tab) : "team";

  const ws = await resolveWorkspace(slug);
  if (ws.isTeam || !ws.courseId) notFound();
  const course: CourseRow = { id: ws.courseId, slug: ws.slug, name: ws.courseName, color: ws.color, initials: ws.initials };

  const [members, cohorts, topics, shares, staff, raw] = await Promise.all([
    listMembers(course.id),
    listCohorts(course.id),
    listTopics(course.id),
    listShares(course.id),
    listStaffProfiles(),
    listRawTopics(course.id),
  ]);
  const aliases = await listTopicAliases(topics.rows.map((t) => t.id));
  const canEdit = user.role === "admin" || ws.role === "owner";
  const isStaff = user.role === "admin" || user.role === "pm";

  const href = (t: Tab) => `/c/${slug}/settings${t === "team" ? "" : `?tab=${t}`}`;

  return (
    <div className="animate-in-up">
      <PageHeader
        title={
          <span className="inline-flex items-center gap-2">
            <CourseSquare name={course.name} slug={course.slug} color={course.color} initials={course.initials} size="lg" />
            {course.name} · Settings
          </span>
        }
        description={canEdit ? "You can change these settings." : `Read-only — only ${course.name}'s owner or an admin can change settings.`}
      />
      <div className="mb-5" data-print-hide>
        <SegmentedTabs
          ariaLabel="Settings sections"
          items={[
            { label: "Team", href: href("team"), active: tab === "team" },
            { label: "Cohorts", href: href("cohorts"), active: tab === "cohorts" },
            { label: "Modules", href: href("modules"), active: tab === "modules" },
            { label: "Notifications", href: href("notifications"), active: tab === "notifications" },
            { label: "Shares", href: href("shares"), active: tab === "shares" },
          ]}
        />
      </div>
      {members.error && tab !== "cohorts" && tab !== "modules" && tab !== "shares" && (
        <p className="border-warning/40 bg-warning/5 mb-4 rounded-md border px-3 py-2 text-[12.5px]">Membership is not set up yet — ask an admin.</p>
      )}
      {tab === "team" && <TeamTab course={course} members={members.rows} cohorts={cohorts.rows} staff={staff} canEdit={canEdit && !members.error} />}
      {tab === "cohorts" && <CohortsTab course={course} cohorts={cohorts.rows} canEdit={canEdit} error={cohorts.error} />}
      {tab === "modules" && <ModulesTab course={course} topics={topics.rows} aliases={aliases.rows} raw={raw} canEdit={canEdit} error={topics.error ?? aliases.error} />}
      {tab === "notifications" && <NotificationsTab course={course} members={members.rows} canEdit={canEdit && !members.error} selfEmail={user.email} />}
      {tab === "shares" && (
        <>
          {shares.error && <p className="text-muted-foreground mb-3 text-[12px]">Share links are not set up yet — ask an admin.</p>}
          <ShareLinks shares={shares.rows} courseId={course.id} canCreate={isStaff && !shares.error} />
        </>
      )}
    </div>
  );
}
