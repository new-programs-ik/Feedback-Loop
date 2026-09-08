import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { instructorHistory, listInstructors, listPendingSuggestions, listRecentMerges, listUnresolvedNames } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { AdminNav } from "@/components/admin/admin-nav";
import { SuggestionsPanel, type SuggestionCard } from "@/components/admin/identity/suggestions-panel";
import { UnresolvedPanel } from "@/components/admin/identity/unresolved-panel";
import { InstructorsPanel } from "@/components/admin/identity/instructors-panel";

export const metadata = { title: "Identity" };

/** /admin/identity — one instructor, one name. Three panels: what the matcher suspects, what it
 *  could not resolve at all, and the directory with merge + undo. */
export default async function IdentityPage() {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");

  const [suggestions, unresolved, instructors, merges] = await Promise.all([
    listPendingSuggestions(),
    listUnresolvedNames(),
    listInstructors(),
    listRecentMerges(),
  ]);
  const history = await instructorHistory(
    suggestions.rows.map((s) => s.raw_name),
    suggestions.rows.map((s) => s.candidate_instructor_id),
  );
  const empty = { classes: 0, first: null, last: null, avg_score: null, avg_rating: null, top_modules: [] };
  const cards: SuggestionCard[] = suggestions.rows.map((s) => ({
    ...s,
    raw: history.byName.get(s.raw_name) ?? empty,
    candidate: history.byId.get(s.candidate_instructor_id) ?? empty,
  }));
  const problems = [suggestions.error, unresolved.error, instructors.error, merges.error].filter((e): e is string => !!e);

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Instructor identity"
        description={`${cards.length} suspected duplicate${cards.length === 1 ? "" : "s"} · ${unresolved.rows.length} unresolved name${unresolved.rows.length === 1 ? "" : "s"} · ${instructors.rows.length} instructors`}
      />
      <AdminNav />
      {problems.length > 0 && (
        <div className="border-warning/40 bg-warning/5 mb-4 rounded-md border px-3 py-2 text-[12.5px]">
          Some identity tables are not available yet: {[...new Set(problems)].join(" · ")}
        </div>
      )}
      <div className="space-y-5">
        <SuggestionsPanel suggestions={cards} />
        <UnresolvedPanel names={unresolved.rows} instructors={instructors.rows} />
        <InstructorsPanel instructors={instructors.rows} merges={merges.rows} />
      </div>
    </div>
  );
}
