import Link from "next/link";
import { Table2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { FilterBar, parseRange, rangeToDates, type FilterDef } from "@/components/filter-bar";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Pagination, SortHead, Table, TableBody, TableCell, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ScorePill } from "@/components/score/score-pill";
import { ClickRow } from "@/components/score/click-row";
import { ClassDrawer } from "@/components/score/class-drawer";
import { ClassDetail, loadClassDetail } from "@/components/score/class-detail";
import { fetchClassesPage, instructorName, type ClassSortKey, fetchBandCounts } from "@/lib/ratings";
import { coursePriors, courseKey, scoreRow } from "@/lib/class-score";
import { getActiveConfig } from "@/lib/scoring";
import { ACTION_LABEL } from "@/lib/sentiment";
import { voteLabel } from "@/lib/decision";
import { BandChips, readBands, bandsToParam } from "@/components/analytics/band-chips";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/utils";

export const metadata = { title: "Classes" };

type SP = {
  range?: string; from?: string; to?: string; cohort?: string; kind?: string; instructor?: string; band?: string; status?: string;
  sort?: string; dir?: string; page?: string; class?: string; density?: string;
};

const SORTS: ClassSortKey[] = ["score", "class", "cohort", "instructor", "date", "kind", "rating", "vote", "reach", "action"];
const DEFAULT_DIR: Record<ClassSortKey, "asc" | "desc"> = {
  score: "asc", class: "asc", cohort: "asc", instructor: "asc", date: "desc", kind: "asc", rating: "asc", vote: "asc", reach: "desc", action: "asc",
};
const KINDS = ["Live Class", "Test Review", "Other"];
const pretty = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });
const cohortShort = (t: string | null) => (t ? t.split(/[,;]/)[0].trim() : "—");

export default async function ClassesPage({
  params,
  searchParams,
}: {
  params: Promise<{ course: string }>;
  searchParams: Promise<SP>;
}) {
  const { course } = await params;
  const sp = await searchParams;
  const [ws] = await Promise.all([resolveWorkspace(course), requireUser()]);
  const basePath = hrefIn(ws.slug, "/classes");

  const range = parseRange(sp.range, "30d");
  const { from, to } = rangeToDates(range, sp.from, sp.to);
  const sort: ClassSortKey = (SORTS as string[]).includes(sp.sort ?? "") ? (sp.sort as ClassSortKey) : "date";
  const dir = sp.dir === "asc" || sp.dir === "desc" ? sp.dir : DEFAULT_DIR[sort];
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);
  const density = sp.density === "compact" ? "compact" : "normal";

  const supabase = await createClient();
  const [result, active, cohortsRes, instructorsRes, detail, bandCounts] = await Promise.all([
    fetchClassesPage({
      courseId: ws.courseId, from, to, sort, dir, page, pageSize: 50,
      cohort: sp.cohort, kind: sp.kind, instructor: sp.instructor, band: sp.band, status: sp.status,
    }),
    getActiveConfig(),
    ws.courseId ? supabase.from("cohorts").select("id, name").eq("course_id", ws.courseId).order("name") : Promise.resolve({ data: null }),
    supabase.from("instructors").select("id, name").order("name"),
    sp.class ? loadClassDetail(sp.class) : Promise.resolve(null),
    fetchBandCounts({ from, to, courseId: ws.courseId, cohort: sp.cohort, kind: sp.kind, instructor: sp.instructor }),
  ]);
  const cfg = active.config;
  const priors = coursePriors(result.rows);
  const entries = result.rows.map((row) => ({ row, scored: scoreRow(row, cfg, priors.get(courseKey(row))) }));
  const cohorts = ((cohortsRes.data ?? []) as Array<{ id: string; name: string }>).map((c) => ({ value: c.name, label: c.name }));
  const instructors = ((instructorsRes.data ?? []) as Array<{ id: string; name: string }>).map((i) => ({ value: i.name, label: i.name }));

  /** The current URL with some parameters changed; the drawer parameter is dropped unless kept. */
  const href = (changes: Record<string, string | undefined>, keepClass = false) => {
    const q = new URLSearchParams();
    const merged: Record<string, string | undefined> = { ...sp, ...changes };
    for (const [k, v] of Object.entries(merged)) {
      if (!v) continue;
      if (k === "class" && !keepClass) continue;
      q.set(k, v);
    }
    const qs = q.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };
  const sortHref = (key: ClassSortKey) =>
    href({ sort: key, dir: key === sort ? (dir === "asc" ? "desc" : "asc") : DEFAULT_DIR[key], page: undefined });
  const openHref = (id: string) => href({ class: id }, true);
  const closeHref = href({ class: undefined });

  const filters: FilterDef[] = [
    { name: "cohort", label: "Cohort", value: sp.cohort, options: cohorts, className: "w-52" },
    { name: "kind", label: "Kind", value: sp.kind, options: KINDS.map((k) => ({ value: k, label: k })), all: "Live + review", className: "w-40" },
    { name: "instructor", label: "Instructor", value: sp.instructor, options: instructors, className: "w-48" },
  ];
  const filtered = !!(sp.cohort || sp.kind || sp.instructor || sp.band || sp.status || range !== "30d");

  return (
    <div className="with-filter-bar">
      <PageHeader
        title="Classes"
        description="Every class in the period, scored. Click a row for the full picture."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={href({ density: density === "compact" ? undefined : "compact" })}>{density === "compact" ? "Comfortable" : "Compact"}</Link>
          </Button>
        }
      />

      <FilterBar basePath={basePath} range={range} from={from} to={to} filters={filters} extra={{ ...(sp.sort ? { sort: sp.sort } : {}), ...(sp.dir ? { dir: sp.dir } : {}), ...(sp.density ? { density: sp.density } : {}) }}>
        <span className="text-muted-foreground text-[11px]" data-numeric>
          {result.total} {result.total === 1 ? "class" : "classes"}
        </span>
      </FilterBar>

      <BandChips
        selected={readBands(sp.band)}
        counts={bandCounts}
        hrefFor={(bands) => href({ band: bandsToParam(bands), page: undefined })}
      />

      {result.degraded && sp.band && (
        <p className="text-muted-foreground mb-3 text-xs">The band filter needs the scoring migration — showing every band until it lands.</p>
      )}

      {entries.length === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          <EmptyState
            icon={Table2}
            title={filtered ? "Nothing matches these filters." : "No classes in this period."}
            action={
              filtered ? (
                <Button asChild variant="outline" size="sm">
                  <Link href={basePath}>Clear filters</Link>
                </Button>
              ) : (
                <Button asChild variant="outline" size="sm">
                  <Link href={href({ range: "90d" })}>Show the last 90 days</Link>
                </Button>
              )
            }
          />
        </div>
      ) : (
        <div className="bg-card shadow-soft rounded-xl border">
          <Table sticky density={density}>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <SortHead href={sortHref("score")} active={sort === "score"} dir={dir} className="w-24">Score</SortHead>
                <SortHead href={sortHref("class")} active={sort === "class"} dir={dir}>Class</SortHead>
                <SortHead href={sortHref("cohort")} active={sort === "cohort"} dir={dir} className="hidden lg:table-cell">Cohort</SortHead>
                <SortHead href={sortHref("instructor")} active={sort === "instructor"} dir={dir}>Instructor</SortHead>
                <SortHead href={sortHref("date")} active={sort === "date"} dir={dir}>Date</SortHead>
                <SortHead href={sortHref("kind")} active={sort === "kind"} dir={dir} className="hidden md:table-cell">Kind</SortHead>
                <SortHead href={sortHref("rating")} active={sort === "rating"} dir={dir} align="right">Rating</SortHead>
                <SortHead href={sortHref("vote")} active={sort === "vote"} dir={dir} align="right" className="hidden md:table-cell">Approval</SortHead>
                <SortHead href={sortHref("reach")} active={sort === "reach"} dir={dir} align="right" className="hidden xl:table-cell">Rated / attended</SortHead>
                <SortHead href={sortHref("action")} active={sort === "action"} dir={dir}>Action</SortHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map(({ row, scored }) => {
                const vote = voteLabel(row.yes_votes, row.no_votes);
                const reach = row.num_ratings != null && row.attended ? Math.min(100, Math.round((row.num_ratings / row.attended) * 100)) : null;
                return (
                  <ClickRow key={row.id} href={openHref(row.id)} active={sp.class === row.id}>
                    <TableCell className="py-1.5">
                      <ScorePill variant="sm" score={scored.score} band={scored.band} provisional={scored.provisional} action={scored.action} breakdown={{ rows: scored.rows, version: active.version, reason: scored.reason }} />
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <Link href={openHref(row.id)} className="block truncate font-medium" scroll={false}>
                        {row.topic || row.session_kind}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden max-w-40 truncate lg:table-cell">{cohortShort(row.cohort_text)}</TableCell>
                    <TableCell className="max-w-40 truncate">{instructorName(row)}</TableCell>
                    <TableCell className="text-muted-foreground whitespace-nowrap" data-numeric>{pretty(row.class_date)}</TableCell>
                    <TableCell className="text-muted-foreground hidden whitespace-nowrap md:table-cell">{row.session_kind}</TableCell>
                    <TableNum className={cn("font-medium", row.rating < cfg.rating.line && "text-band-bad-text")}>{row.rating.toFixed(2)}</TableNum>
                    <TableNum className="text-muted-foreground hidden md:table-cell">{vote ?? "—"}</TableNum>
                    <TableNum className="text-muted-foreground hidden xl:table-cell">{reach != null ? `${row.num_ratings}/${row.attended} · ${reach}%` : "—"}</TableNum>
                    <TableCell className="whitespace-nowrap">
                      <span className={cn(scored.action === "video" && "text-band-bad-text font-medium", scored.action === "transcript" && "text-band-average-text font-medium", scored.action === "none" && "text-muted-foreground")}>
                        {scored.action === "none" ? "—" : ACTION_LABEL[scored.action].replace(" analysis", "")}
                      </span>
                      {row.review_status !== "new" && (
                        <span className="text-muted-foreground ml-1.5 text-[11px]">· {row.review_status.replace("_", " ")}</span>
                      )}
                    </TableCell>
                  </ClickRow>
                );
              })}
            </TableBody>
          </Table>
          <Pagination page={result.page} pageSize={result.pageSize} total={result.total} hrefFor={(p) => href({ page: p > 1 ? String(p) : undefined })} />
        </div>
      )}

      {detail && (
        <ClassDrawer closeHref={closeHref} title={detail.row.topic || detail.row.session_kind}>
          <ClassDetail data={detail} cfg={cfg} version={active.version} priors={priors.get(courseKey(detail.row))} slug={ws.slug} />
        </ClassDrawer>
      )}
      {sp.class && !detail && (
        <p className="text-muted-foreground mt-3 text-xs">That class was not found — it may have been removed from the sheet.</p>
      )}
    </div>
  );
}
