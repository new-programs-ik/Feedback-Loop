import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { listScoringConfigs } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { AdminNav } from "@/components/admin/admin-nav";
import { ScoringWorkbench } from "@/components/admin/scoring/scoring-workbench";
import { lastMonths } from "@/components/admin/scoring/months";

export const metadata = { title: "Scoring" };

/** /admin/scoring — the Class Sentiment Score's settings as stored, versioned rows. Edit a draft
 *  on the left, watch a month of real classes re-score on the right, publish with a name and a
 *  note, roll back by activating an earlier version. */
export default async function ScoringAdminPage() {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  const { configs, error } = await listScoringConfigs();
  const { months, defaultMonth } = lastMonths(12);
  const active = configs.find((c) => c.status === "active");

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Scoring"
        description={
          active
            ? `Version ${active.version} · ${active.name} is live. Every stored class score carries the version that produced it.`
            : "No version is active yet — the preview uses the manager's original settings as the baseline."
        }
      />
      <AdminNav />
      <ScoringWorkbench mode="admin" versions={configs} versionsError={error} months={months} defaultMonth={defaultMonth} />
    </div>
  );
}
