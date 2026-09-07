import type { Metadata } from "next";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { InstructorPortfolio } from "@/components/analytics/instructor-portfolio";
import {
  addDays,
  applyScope,
  fetchScored,
  instructorName,
  loadAliases,
  loadInstructorNames,
  loadLoop,
  parseInstructorId,
  readScope,
  rowsForInstructor,
  scopeQuery,
  type SearchParams,
} from "@/lib/analytics";
import { hrefIn } from "@/lib/workspace";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<SearchParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const parsed = parseInstructorId(id);
  if (parsed.name) return { title: parsed.name };
  const names = await loadInstructorNames();
  return { title: (parsed.instructorId && names.get(parsed.instructorId)) || "Instructor" };
}

export default async function TeamInstructorPage({ params, searchParams }: Props) {
  const [{ id }, sp] = await Promise.all([params, searchParams]);
  const scope = readScope(sp);
  const parsed = parseInstructorId(id);
  const historyFrom = addDays(scope.from, -180);
  const [rowsAll, historyAll, loop, aliases, names] = await Promise.all([
    fetchScored({ from: scope.from, to: scope.to }),
    fetchScored({ from: historyFrom, to: scope.to }),
    loadLoop(null),
    loadAliases(parsed.instructorId),
    loadInstructorNames(),
  ]);
  const scoped = applyScope(rowsAll, { ...scope, instructor: undefined });
  const own = rowsForInstructor(scoped, parsed);
  const history = rowsForInstructor(historyAll, parsed);
  const name = own[0] ? instructorName(own[0]) : history[0] ? instructorName(history[0]) : (parsed.instructorId && names.get(parsed.instructorId)) || parsed.name;
  const base = `/team/instructors/${encodeURIComponent(id)}`;
  const q = scopeQuery(scope);

  return (
    <div className="space-y-4">
      <ScopeBar basePath={base} scope={scope} show={{ cohort: false, instructor: false, kind: true, band: false }} />
      <InstructorPortfolio
        id={{ instructorId: parsed.instructorId, name: name ?? parsed.name }}
        own={own}
        all={scoped}
        history={history}
        loop={loop}
        aliases={aliases}
        from={scope.from}
        to={scope.to}
        scopeLabel="all courses"
        backHref={`/team/instructors${q}`}
        modulesHrefFor={(key) => {
          const sample = own.find((r) => (r.topic_id ?? `name:${r.topic.trim()}`) === key);
          return sample?.course_slug ? hrefIn(sample.course_slug, `/modules/${encodeURIComponent(key)}`) + q : `/team/instructors${q}`;
        }}
      />
    </div>
  );
}
