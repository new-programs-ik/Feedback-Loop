import type { Metadata } from "next";
import Link from "next/link";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { PageHeader } from "@/components/page-header";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { Leaderboard } from "@/components/analytics/leaderboard";
import { Section } from "@/components/analytics/ui";
import {
  applyScope,
  byCohort,
  byInstructor,
  fetchScored,
  loadCohorts,
  prettyDate,
  previousWindow,
  readScope,
  scopeQuery,
  scoreSummary,
  type SearchParams,
} from "@/lib/analytics";

export const metadata: Metadata = { title: "Instructors" };

export default async function InstructorsPage({ params, searchParams }: { params: Promise<{ course: string }>; searchParams: Promise<SearchParams> }) {
  const [{ course: slug }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const prev = previousWindow(scope.from, scope.to);
  const [rowsAll, prevAll, cohortNames] = await Promise.all([
    fetchScored({ from: scope.from, to: scope.to, courseId: ws.courseId }),
    fetchScored({ from: prev.from, to: prev.to, courseId: ws.courseId }),
    loadCohorts(ws.courseId),
  ]);
  const rows = applyScope(rowsAll, scope, cohortNames);
  const prevRows = applyScope(prevAll, scope, cohortNames);
  const cur = scoreSummary(rows);
  // The leaderboard opens best score first and re-sorts on any heading; this order only breaks ties.
  const items = byInstructor(rows).sort((a, b) => (b.avgScore ?? -1) - (a.avgScore ?? -1) || b.n - a.n || a.name.localeCompare(b.name));
  const prevScores = new Map(byInstructor(prevRows).map((i) => [i.key, i.avgScore]));
  const thin = items.filter((i) => i.n < 3).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
  const base = hrefIn(ws.slug, "/instructors");
  const q = scopeQuery(scope, "90d");
  const portfolio = (key: string) => hrefIn(ws.slug, `/instructors/${encodeURIComponent(key)}`) + q;
  const cohortOptions = byCohort(rowsAll, cohortNames).map((c) => ({ key: c.ref.key, name: c.ref.name }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="Instructors"
        description={`${items.length} ${items.length === 1 ? "instructor" : "instructors"} taught ${cur.n} rated ${cur.n === 1 ? "class" : "classes"} · ${prettyDate(scope.from)} – ${prettyDate(scope.to)}`}
      />
      <ScopeBar basePath={base} scope={scope} cohorts={cohortOptions} show={{ cohort: true, kind: true, band: true, instructor: false }} />
      <Section
        title="Leaderboard"
        subtitle="Instructors with at least 3 classes · Δ against the previous equal period · bullet vs the course average · click a heading to sort"
        flush
      >
        <Leaderboard items={items} reference={cur.avgScore} previous={prevScores} hrefFor={portfolio} />
      </Section>
      {thin.length > 0 && (
        <Section title="Fewer than 3 classes" subtitle="Not ranked yet — the portfolio still opens">
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]">
            {thin.map((i) => (
              <li key={i.key}>
                <Link href={portfolio(i.key)} className="hover:text-primary">
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
