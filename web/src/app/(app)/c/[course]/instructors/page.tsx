import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { SegmentedTabs } from "@/components/ui/tabs";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { Leaderboard } from "@/components/analytics/leaderboard";
import { Section } from "@/components/analytics/ui";
import {
  applyScope,
  byCohort,
  byInstructor,
  fetchScored,
  loadCohorts,
  one,
  prettyDate,
  previousWindow,
  readScope,
  scopeQuery,
  scoreSummary,
  type SearchParams,
} from "@/lib/analytics";

export const metadata: Metadata = { title: "Instructors" };

type Sort = "best" | "worst" | "classes" | "recent";

export default async function InstructorsPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const sortRaw = one(sp, "sort");
  const sort: Sort = sortRaw === "worst" || sortRaw === "classes" || sortRaw === "recent" ? sortRaw : "best";
  const prev = previousWindow(scope.from, scope.to);
  const [rowsAll, prevAll, cohortNames] = await Promise.all([
    fetchScored({ from: scope.from, to: scope.to, courseId: ws.courseId }),
    fetchScored({ from: prev.from, to: prev.to, courseId: ws.courseId }),
    loadCohorts(ws.courseId),
  ]);
  const rows = applyScope(rowsAll, scope, cohortNames);
  const prevRows = applyScope(prevAll, scope, cohortNames);
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
  const thin = items.filter((i) => i.n < 3);
  const base = hrefIn(ws.slug, "/instructors");
  const q = (extra?: Record<string, string | undefined>) => scopeQuery(scope, "90d", extra);
  const cohortOptions = byCohort(rowsAll, cohortNames).map((c) => ({ key: c.ref.key, name: c.ref.name }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="Instructors"
        description={`${items.length} ${items.length === 1 ? "instructor" : "instructors"} taught ${cur.n} rated ${cur.n === 1 ? "class" : "classes"} · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`}
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
      <ScopeBar basePath={base} scope={scope} cohorts={cohortOptions} show={{ cohort: true, kind: true, band: true, instructor: false }} extra={{ sort: sort === "best" ? undefined : sort }} />
      <Section title="Leaderboard" subtitle="Instructors with at least 3 classes · Δ against the previous equal period · bullet vs the course average" flush>
        <Leaderboard items={items} reference={cur.avgScore} previous={prevScores} hrefFor={(key) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q()} />
      </Section>
      {thin.length > 0 && (
        <Section title="Fewer than 3 classes" subtitle="Not ranked yet — the portfolio still opens">
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]">
            {thin.map((i) => (
              <li key={i.key}>
                <Link href={hrefIn(ws.slug, `/instructors/${encodeURIComponent(i.key)}`) + q()} className="hover:text-primary">
                  {i.name}
                </Link>
                <span className="text-muted-foreground" data-numeric>
                  {" "}· {i.n}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
