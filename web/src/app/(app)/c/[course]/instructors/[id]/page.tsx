import type { Metadata } from "next";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { ScopeBar } from "@/components/analytics/scope-bar";
import { InstructorPortfolio } from "@/components/analytics/instructor-portfolio";
import {
  addDays,
  applyScope,
  fetchScored,
  instructorName,
  loadAliases,
  loadLoop,
  parseInstructorId,
  readScope,
  rowsForInstructor,
  scopeQuery,
  type SearchParams,
} from "@/lib/analytics";

type Props = { params: Promise<{ course: string; id: string }>; searchParams: Promise<SearchParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const parsed = parseInstructorId(id);
  return { title: parsed.name ?? "Instructor" };
}

export default async function InstructorPage({ params, searchParams }: Props) {
  const [{ course: slug, id }, sp] = await Promise.all([params, searchParams]);
  const ws = await resolveWorkspace(slug);
  const scope = readScope(sp);
  const parsed = parseInstructorId(id);
  const historyFrom = addDays(scope.from, -180);
  const [rowsAll, historyAll, loop, aliases] = await Promise.all([
    fetchScored({ from: scope.from, to: scope.to, courseId: ws.courseId }),
    fetchScored({ from: historyFrom, to: scope.to, courseId: ws.courseId }),
    loadLoop(ws.courseId),
    loadAliases(parsed.instructorId),
  ]);
  const scoped = applyScope(rowsAll, { ...scope, instructor: undefined });
  const own = rowsForInstructor(scoped, parsed);
  const history = rowsForInstructor(historyAll, parsed);
  const name = own[0] ? instructorName(own[0]) : history[0] ? instructorName(history[0]) : parsed.name;
  const base = hrefIn(ws.slug, `/instructors/${encodeURIComponent(id)}`);
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
        scopeLabel={ws.courseName}
        backHref={hrefIn(ws.slug, "/instructors") + q}
        modulesHrefFor={(key) => hrefIn(ws.slug, `/modules/${encodeURIComponent(key)}`) + q}
      />
    </div>
  );
}
