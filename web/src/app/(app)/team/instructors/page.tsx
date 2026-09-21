import type { Metadata } from "next";
import { hrefIn, listCourses } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { Leaderboard } from "@/components/analytics/leaderboard";
import { Section } from "@/components/analytics/ui";
import { applyScope, byInstructor, fetchScored, one, prettyDate, previousWindow, readScope, scopeQuery, scoreSummary, type SearchParams } from "@/lib/analytics";

export const metadata: Metadata = { title: "Instructors" };

export default async function TeamInstructorsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const scope = readScope(sp);
  const courseId = one(sp, "course") || undefined;
  const prev = previousWindow(scope.from, scope.to);
  const [courses, rowsAll, prevAll] = await Promise.all([
    listCourses(),
    fetchScored({ from: scope.from, to: scope.to, courseId }),
    fetchScored({ from: prev.from, to: prev.to, courseId }),
  ]);
  const rows = applyScope(rowsAll, scope);
  const prevRows = applyScope(prevAll, scope);
  const cur = scoreSummary(rows);
  // The directory opens best score first and re-sorts on any heading; this order only breaks ties.
  const items = byInstructor(rows).sort((a, b) => (b.avgScore ?? -1) - (a.avgScore ?? -1) || b.n - a.n || a.name.localeCompare(b.name));
  const prevScores = new Map(byInstructor(prevRows).map((i) => [i.key, i.avgScore]));
  const base = "/team/instructors";
  const q = scopeQuery(scope, "90d", { course: courseId });
  const hrefFor = (key: string) => `${base}/${encodeURIComponent(key)}${q}`;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Instructors"
        description={`${items.length} ${items.length === 1 ? "instructor" : "instructors"} across every course · ${cur.n} rated classes · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`}
      />
      <ScopeBar
        basePath={base}
        scope={scope}
        courses={courses.map((c) => ({ id: c.id, name: c.name }))}
        courseId={courseId}
        show={{ cohort: false, kind: true, band: true, instructor: false }}
      />
      <Section
        title="Directory"
        subtitle="Instructors with at least 3 classes · courses they taught · Δ against the previous equal period · bullet vs the team average · click a heading to sort"
        flush
      >
        <Leaderboard items={items} reference={cur.avgScore} previous={prevScores} hrefFor={hrefFor} showCourses courseHref={(slug) => (slug ? hrefIn(slug, "/instructors") : null)} />
      </Section>
    </div>
  );
}
