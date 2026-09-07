import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { listScoringConfigs } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { ScoringWorkbench } from "@/components/admin/scoring/scoring-workbench";
import { lastMonths } from "@/components/admin/scoring/months";

export const metadata = { title: "What-if" };

/** /tools/what-if — the same editor and live preview every PM can play with. Nothing here
 *  changes the live score; "Propose to admin" saves the settings as a draft with a note. */
export default async function WhatIfPage() {
  const user = await requireUser();
  if (user.role !== "admin" && user.role !== "pm") redirect("/");
  const { configs, error } = await listScoringConfigs();
  const { months, defaultMonth } = lastMonths(12);
  const active = configs.find((c) => c.status === "active");

  return (
    <div className="animate-in-up">
      <PageHeader
        title="What-if simulator"
        description={`Change any setting of the Class Sentiment Score and see what a month of real classes would do${active ? ` against version ${active.version}` : ""}. Nothing changes until an admin publishes.`}
      />
      <ScoringWorkbench mode="whatif" versions={configs} versionsError={error} months={months} defaultMonth={defaultMonth} />
    </div>
  );
}
