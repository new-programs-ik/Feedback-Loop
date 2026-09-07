import type { Metadata } from "next";
import { hrefIn, listCourses } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { SegmentedTabs } from "@/components/ui/tabs";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { Leaderboard } from "@/components/analytics/leaderboard";
import { GalaxyToggle } from "@/components/analytics/galaxy-toggle";
import { Section } from "@/components/analytics/ui";
import { applyScope, byInstructor, fetchScored, one, prettyDate, previousWindow, readScope, scopeQuery, scoreSummary, type SearchParams } from "@/lib/analytics";

export const metadata: Metadata = { title: "Instructors" };

type Sort = "best" | "worst" | "classes" | "recent";

export default async function TeamInstructorsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const scope = readScope(sp);
  const courseId = one(sp, "course") || undefined;
  const sortRaw = one(sp, "sort");
  const sort: Sort = sortRaw === "worst" || sortRaw === "classes" || sortRaw === "recent" ? sortRaw : "best";
  const prev = previousWindow(scope.from, scope.to);
  const [courses, rowsAll, prevAll] = await Promise.all([
    listCourses(),
    fetchScored({ from: scope.from, to: scope.to, courseId }),
    fetchScored({ from: prev.from, to: prev.to, courseId }),
  ]);
  const rows = applyScope(rowsAll, scope);
  const prevRows = applyScope(prevAll, scope);
  const cur = scoreSummary(rows);
  const items = byInstructor(rows).sort((a, b) =>
    sort === "worst"
      ? (a.avgScore ?? 101) - (b.avgScore ?? 101)
      : sort === "classes"
        ? b.n - a.n
        : sort === "recent"
          ? b.lastClassDate.localeCompare(a.lastClassDate)
          : (b.avgScore ?? -1) - (a.avgScore ?? -1),
  );
  const prevScores = new Map(byInstructor(prevRows).map((i) => [i.key, i.avgScore]));
  const base = "/team/instructors";
  const q = (extra?: Record<string, string | undefined>) => scopeQuery(scope, "90d", { course: courseId, ...extra });
  const hrefFor = (key: string) => `${base}/${encodeURIComponent(key)}${q()}`;
  const galaxy = items
    .filter((i) => i.n >= 3)
    .map((i) => ({ name: i.name, n: i.n, avgRating: i.avgRating, approval: i.approval, avgParticipation: i.reach, bad: i.counts.bad, href: hrefFor(i.key) }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="Instructors"
        description={`${items.length} ${items.length === 1 ? "instructor" : "instructors"} across every course · ${cur.n} rated classes · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`}
        actions={
          <SegmentedTabs
            ariaLabel="Sort"
            items={[
              { label: "Best first", href: base + q({ sort: undefined }), active: sort === "best" },
              { label: "Worst first", href: base + q({ sort: "worst" }), active: sort === "worst" },
              { label: "Most classes", href: base + q({ sort: "classes" }), active: sort === "classes" },
              { label: "Recent", href: base + q({ sort: "recent" }), active: sort === "recent" },
            ]}
          />
        }
      />
      <ScopeBar
        basePath={base}
        scope={scope}
        courses={courses.map((c) => ({ id: c.id, name: c.name }))}
        courseId={courseId}
        show={{ cohort: false, kind: true, band: true, instructor: false }}
        extra={{ sort: sort === "best" ? undefined : sort }}
      />
      {galaxy.length > 0 && <GalaxyToggle points={galaxy} query={q().replace(/^\?/, "")} />}
      <Section title="Directory" subtitle="Instructors with at least 3 classes · courses they taught · Δ against the previous equal period · bullet vs the team average" flush>
        <Leaderboard items={items} reference={cur.avgScore} previous={prevScores} hrefFor={hrefFor} showCourses courseHref={(slug) => (slug ? hrefIn(slug, "/instructors") : null)} />
      </Section>
    </div>
  );
}
