import Link from "next/link";
import { ListChecks, TriangleAlert } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { TableCell } from "@/components/ui/table";
import { FilterBar, parseRange, rangeToDates, type FilterDef } from "@/components/filter-bar";
import { BandChip, ScorePill } from "@/components/score/score-pill";
import { RawStat } from "@/components/analytics/raw-stat";
import { CourseChips, type CourseChipItem } from "@/components/queue/course-chips";
import { QueueRow, WatchRow } from "@/components/queue/queue-row";
import { QueueRows, QueueSort, QueueSortControl, type QueueSortRow } from "@/components/queue/sortable-queue";
import { SyncNowButton } from "@/components/queue/sync-now-button";
import { fetchQueue, instructorName, lastSyncRun, type ClassRating, type ReviewStatus } from "@/lib/ratings";
import { byUrgency, coursePriors, courseKey, queueCost, scoreRow, type Scored } from "@/lib/class-score";
import { getActiveConfig } from "@/lib/scoring";
import { BAND_META, type Band } from "@/lib/sentiment";
import { requireUser } from "@/lib/session";
import { TEAM_SLUG, hrefIn, listCourses } from "@/lib/workspace";
import { mapCourseLabel } from "@/app/(app)/c/[course]/queue/actions";
import { cn } from "@/lib/utils";

export type QueueSearchParams = {
  focus?: string;
  range?: string;
  from?: string;
  to?: string;
  cohort?: string;
  kind?: string;
  instructor?: string;
  status?: string;
  course?: string;
};

type Entry = { row: ClassRating; scored: Scored };

const pretty = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });
/** The first cohort of a list, trimmed — the meta line has one slot for it. */
const cohortShort = (t: string | null) => (t ? t.split(/[,;]/)[0].trim().slice(0, 48) : null);
/** What a section sorts a row on; the row itself is rendered right here, on the server. */
const sortValues = (row: ClassRating, scored: Scored) => ({
  id: row.id,
  score: scored.score,
  date: row.class_date,
  rating: row.rating,
  reach: row.participation_pct ?? (row.num_ratings != null && row.attended ? Math.min(100, (row.num_ratings / row.attended) * 100) : null),
  instructor: instructorName(row),
});

const OPEN = new Set<ReviewStatus>(["new", "notified", "confirmed"]);
const isOpenStatus = (s: ReviewStatus) => OPEN.has(s);
const STATUS_OPTIONS = [
  { value: "new", label: "New" },
  { value: "notified", label: "Handler pinged" },
  { value: "confirmed", label: "Confirmed" },
  { value: "analysis_started", label: "In analysis" },
  { value: "dismissed", label: "Dismissed" },
  { value: "all", label: "Everything" },
];

/** One queue for both levels: a course (`courseId`) or the whole team (`null`). Three sections —
 *  Bad → watch the recording, Average → read the transcript, Watch (too few responses) — each row with its score, the
 *  plain reason under it, and the actions. Rows come from the `queue_rows` RPC when it exists,
 *  else the plain fetch over the period. */
export async function QueuePage({ courseId, slug, sp }: { courseId: string | null; slug: string; sp: QueueSearchParams }) {
  const user = await requireUser();
  const isTeam = courseId == null;
  const basePath = hrefIn(slug, "/queue");
  const range = parseRange(sp.range, "45d");
  const { from, to } = rangeToDates(range, sp.from, sp.to);
  const now = new Date();
  const nowMs = now.getTime();

  const [{ rows: fetched, viaRpc }, run, active, courses] = await Promise.all([
    fetchQueue(courseId, from),
    lastSyncRun(),
    getActiveConfig(),
    listCourses(),
  ]);
  const cfg = active.config;
  const inWindow = fetched.filter((r) => r.class_date <= to);
  const priors = coursePriors(inWindow);
  const all: Entry[] = inWindow.map((row) => ({ row, scored: scoreRow(row, cfg, priors.get(courseKey(row))) }));

  // ── filters (URL state) ──
  const courseQ = isTeam ? sp.course || undefined : undefined;
  const cohortQ = sp.cohort?.trim() || undefined;
  const kindQ = sp.kind || undefined;
  const instrQ = sp.instructor || undefined;
  const statusQ = sp.status || "open";
  const statusOk = (s: ReviewStatus) => (statusQ === "all" ? true : statusQ === "open" ? isOpenStatus(s) : s === statusQ);
  const matches = (e: Entry) =>
    (!courseQ || e.row.course_id === courseQ) &&
    (!cohortQ || e.row.cohort_id === cohortQ || e.row.cohort_ids.includes(cohortQ) || (e.row.cohort_text ?? "").toLowerCase().includes(cohortQ.toLowerCase())) &&
    (!kindQ || e.row.session_kind === kindQ) &&
    (!instrQ || instructorName(e.row) === instrQ || e.row.instructor === instrQ || e.row.instructor_id === instrQ);

  const scoped = all.filter(matches);
  const video = scoped.filter((e) => e.scored.action === "video" && statusOk(e.row.review_status)).sort(byUrgency);
  const transcript = scoped.filter((e) => e.scored.action === "transcript" && statusOk(e.row.review_status)).sort(byUrgency);
  const watch = scoped
    .filter((e) => e.scored.action === "watch" && e.row.review_status !== "dismissed" && (statusQ === "open" || statusQ === "all" || e.row.review_status === statusQ))
    .sort(byUrgency);
  const cost = queueCost(video.length, transcript.length);

  // Course chips (team level only) count the OPEN actionable rows per course, unfiltered by
  // course so the numbers stay put while you click between them.
  const actionableAll = all.filter((e) => (e.scored.action === "video" || e.scored.action === "transcript") && isOpenStatus(e.row.review_status));
  const chipCounts = new Map<string, number>();
  for (const e of actionableAll) if (e.row.course_id) chipCounts.set(e.row.course_id, (chipCounts.get(e.row.course_id) ?? 0) + 1);
  const chipHref = (id?: string | null) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(sp)) if (v && k !== "course") q.set(k, v);
    if (id) q.set("course", id);
    const qs = q.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };
  const chipItems: CourseChipItem[] = isTeam
    ? [
        { id: null, href: chipHref(), name: "All", count: actionableAll.length },
        ...courses
          .filter((c) => chipCounts.has(c.id))
          .sort((a, b) => (chipCounts.get(b.id) ?? 0) - (chipCounts.get(a.id) ?? 0) || a.name.localeCompare(b.name))
          .map((c) => ({ id: c.id, href: chipHref(c.id), name: c.name, count: chipCounts.get(c.id) ?? 0 })),
      ]
    : [];

  // Filter options come from the rows in the window, so the lists are never empty promises.
  const distinct = (xs: (string | null)[]) => [...new Set(xs.filter((x): x is string => !!x))].sort((a, b) => a.localeCompare(b));
  const filters: FilterDef[] = [
    { name: "cohort", label: "Cohort", value: cohortQ, options: distinct(all.map((e) => cohortShort(e.row.cohort_text))).map((v) => ({ value: v, label: v })), className: "w-52" },
    { name: "kind", label: "Kind", value: kindQ, options: distinct(all.map((e) => e.row.session_kind)).map((v) => ({ value: v, label: v })), all: "Live + review", className: "w-40" },
    { name: "instructor", label: "Instructor", value: instrQ, options: distinct(all.map((e) => instructorName(e.row))).map((v) => ({ value: v, label: v })), className: "w-48" },
    { name: "status", label: "Status", value: statusQ === "open" ? "" : statusQ, options: STATUS_OPTIONS, all: "Open (new · pinged · confirmed)", className: "w-56" },
  ];

  const focusId = sp.focus;
  const unmappedLabels = isTeam ? [...new Set(inWindow.filter((r) => !r.course_id).map((r) => r.course_label))] : [];
  const started = inWindow.filter((r) => r.review_status === "analysis_started").length;
  const syncedAgo = run?.finished_at ? Math.round((nowMs - +new Date(run.finished_at)) / 60000) : null;
  const total = video.length + transcript.length + watch.length;
  const filtered = !!(cohortQ || kindQ || instrQ || (statusQ !== "open") || courseQ || range !== "45d");
  const canAnalyze = user.role === "admin" || user.role === "pm";   // the button, not only the server, says no

  return (
    <div className="with-filter-bar">
      <PageHeader
        title="Needs analysis"
        description={`Classes whose Class Sentiment band calls for an analysis — Bad → watch the recording, Average → read the transcript; fewer than ${cfg.min_votes.action || 6} responses → too few to judge.`}
        actions={<SyncNowButton />}
      />

      <FilterBar basePath={basePath} range={range} from={from} to={to} presets={["7d", "30d", "45d", "90d", "month", "custom"]} defaultRange="45d" filters={filters} extra={{ ...(courseQ ? { course: courseQ } : {}), ...(focusId ? { focus: focusId } : {}) }}>
        <span className="text-muted-foreground hidden text-[11px] lg:inline">
          Scoring: {active.name}
          {active.version != null ? ` · v${active.version}` : ""}
          {!active.fromDatabase && " (preview)"}
        </span>
      </FilterBar>

      {/* the week's cost + the sync line */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm">
        <p data-numeric>
          <span className="font-medium">This queue:</span> <span className="text-muted-foreground">{cost.label}</span>
        </p>
        <p
          className={cn("flex items-center gap-2 text-xs", run?.status === "failed" ? "text-destructive" : "text-muted-foreground")}
          data-numeric
        >
          {run ? (
            run.status === "failed" ? (
              <>
                <TriangleAlert className="size-3.5" aria-hidden /> Last sync failed: <span className="max-w-64 truncate">{run.error}</span>
              </>
            ) : (
              <>
                Last synced{" "}
                {syncedAgo == null ? "…" : syncedAgo < 1 ? "just now" : syncedAgo < 60 ? `${syncedAgo} min ago` : `${Math.round(syncedAgo / 60)}h ago`}
                {" · "}{run.rows_fetched ?? run.rows_upserted ?? 0} classes read · {run.rows_flagged ?? 0} flagged
                {started > 0 && ` · ${started} in analysis`}
              </>
            )
          ) : (
            "No sync has run yet — use Sync now."
          )}
        </p>
      </div>

      {isTeam && chipItems.length > 1 && (
        <div className="mb-4" data-print-hide>
          <CourseChips items={chipItems} activeId={courseQ ?? null} />
        </div>
      )}

      {total === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          <EmptyState
            icon={ListChecks}
            title={filtered ? "Nothing matches these filters." : "Nothing needs analysis right now."}
            description={filtered ? undefined : "Every class in the window is Good or Excellent, or already handled."}
            action={
              filtered ? (
                <Button asChild variant="outline" size="sm">
                  <Link href={basePath}>Clear filters</Link>
                </Button>
              ) : (
                <SyncNowButton />
              )
            }
          />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Each section sorts on its own: the control in the header, the rows in the body. */}
          <QueueSort>
            <Section
              band="bad"
              title="Bad → video"
              count={video.length}
              note="Both lines missed, the score under 60, or escalated by a PM."
              actions={video.length > 0 && <QueueSortControl />}
            >
              {video.length === 0 ? (
                <Quiet>No class needs a video analysis.</Quiet>
              ) : (
                <QueueTable canAnalyze={canAnalyze} entries={video} slug={slug} isTeam={isTeam} focusId={focusId} version={active.version} />
              )}
            </Section>
          </QueueSort>
          <QueueSort>
            <Section
              band="average"
              title="Average → transcript"
              count={transcript.length}
              note="One line missed — a transcript read is enough."
              actions={transcript.length > 0 && <QueueSortControl />}
            >
              {transcript.length === 0 ? (
                <Quiet>No class needs a transcript analysis.</Quiet>
              ) : (
                <QueueTable canAnalyze={canAnalyze} entries={transcript} slug={slug} isTeam={isTeam} focusId={focusId} version={active.version} />
              )}
            </Section>
          </QueueSort>
          {watch.length > 0 && (
            <QueueSort>
              <details className="bg-card shadow-soft overflow-hidden rounded-xl border" open={watch.some((e) => e.row.id === focusId) || undefined}>
                <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3 text-sm select-none sm:px-5">
                  <span className="inline-block size-2 rounded-full" style={{ background: "var(--band-none)" }} aria-hidden />
                  <span className="font-semibold">Watch</span>
                  <Badge variant="secondary" data-numeric>{watch.length}</Badge>
                  <span className="text-muted-foreground text-xs">
                    fewer than {cfg.min_votes.action || 6} responses — too few to judge yet; escalate if you know something is wrong
                  </span>
                </summary>
                <div className="flex items-center justify-end border-t px-4 py-1.5 sm:px-5" data-print-hide>
                  <QueueSortControl />
                </div>
                <QueueRows
                  header={false}
                  rows={watch.slice(0, 40).map(({ row, scored }) => ({
                    ...sortValues(row, scored),
                    row: (
                      <WatchRow id={row.id} focus={row.id === focusId}>
                        <TableCell className="w-24 py-2">
                          <ScorePill score={scored.score} band={scored.band} provisional={scored.provisional} variant="sm" emptyText="too few responses" breakdown={{ rows: scored.rows, version: active.version, reason: scored.reason }} action={scored.action} />
                        </TableCell>
                        <ClassCell row={row} scored={scored} slug={slug} isTeam={isTeam} />
                      </WatchRow>
                    ),
                  }))}
                />
                {watch.length > 40 && (
                  <div className="text-muted-foreground border-t px-4 py-2 text-xs">…and {watch.length - 40} more — narrow the filters to see them.</div>
                )}
              </details>
            </QueueSort>
          )}
        </div>
      )}

      {/* unmapped labels (admin hygiene, team level) */}
      {unmappedLabels.length > 0 && user.role !== "learner" && (
        <div className="bg-card shadow-soft mt-4 rounded-xl border p-4 sm:p-5">
          <h3 className="text-sm font-semibold">Unmapped course labels</h3>
          <p className="text-muted-foreground mt-0.5 text-xs">
            These sheet labels are not linked to a course yet, so their classes appear only here. Map each one once — it sticks for every future sync.
          </p>
          <div className="mt-3 space-y-2">
            {unmappedLabels.map((label) => (
              <form key={label} action={mapCourseLabel} className="flex flex-wrap items-center gap-2">
                <input type="hidden" name="alias" value={label} />
                <Badge variant="outline">{label}</Badge>
                <span className="text-muted-foreground text-sm">→</span>
                <Select name="course_id" defaultValue="" className="w-56" aria-label={`Course for ${label}`}>
                  <option value="" disabled>Pick the course…</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </Select>
                <Button variant="outline" size="sm" type="submit">Map</Button>
              </form>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({
  band,
  title,
  count,
  note,
  actions,
  children,
}: {
  band: Band;
  title: string;
  count: number;
  note: string;
  /** Right end of the header — the section's sort control. */
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-card shadow-soft overflow-hidden rounded-xl border" aria-label={title}>
      <header className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-5">
        <span className="inline-block size-2 rounded-full" style={{ background: BAND_META[band].color }} aria-hidden />
        <h2 className="text-sm font-semibold">{title}</h2>
        <Badge variant="secondary" data-numeric>{count}</Badge>
        <span className="text-muted-foreground text-xs">{note}</span>
        {actions ? (
          <span className="ml-auto" data-print-hide>
            {actions}
          </span>
        ) : null}
      </header>
      {children}
    </section>
  );
}

function Quiet({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground border-t px-4 py-3 text-sm sm:px-5">{children}</p>;
}

/** The first 60 rows of a section, rendered here and handed to `QueueRows` with the values the
 *  section sorts on — worst first until the PM picks another order. */
function QueueTable({ entries, slug, isTeam, focusId, version, canAnalyze }: { entries: Entry[]; slug: string; isTeam: boolean; focusId?: string; version: number | null; canAnalyze: boolean }) {
  const MAX = 60;
  const rows: QueueSortRow[] = entries.slice(0, MAX).map(({ row, scored }) => ({
    ...sortValues(row, scored),
    row: (
      <QueueRow
        id={row.id}
        status={row.review_status === "notified" || row.review_status === "confirmed" ? row.review_status : "new"}
        focus={row.id === focusId}
        escalated={row.escalated}
        analyzeHref={canAnalyze ? `/feedback/new?prefill=${row.id}` : null}
      >
        <TableCell className="w-24 py-2">
          <ScorePill score={scored.score} band={scored.band} provisional={scored.provisional} variant="sm" breakdown={{ rows: scored.rows, version, reason: scored.reason }} action={scored.action} />
        </TableCell>
        <ClassCell row={row} scored={scored} slug={slug} isTeam={isTeam} />
      </QueueRow>
    ),
  }));
  return (
    <>
      <QueueRows rows={rows} />
      {entries.length > MAX && (
        <div className="text-muted-foreground border-t px-4 py-2 text-xs">…and {entries.length - MAX} more — narrow the filters to see them.</div>
      )}
    </>
  );
}

/** Class name, then "cohort · instructor · date · kind" (and the course at the team level), then
 *  the raw numbers — rating, rated / attended — beside the plain reason. The name opens the class
 *  drawer in its course. */
function ClassCell({ row, scored, slug, isTeam }: { row: ClassRating; scored: Scored; slug: string; isTeam: boolean }) {
  const courseSlug = isTeam ? row.course_slug : slug;
  const href = courseSlug && courseSlug !== TEAM_SLUG ? `${hrefIn(courseSlug, "/classes")}?class=${row.id}` : null;
  const name = row.topic || row.session_kind;
  const meta = [cohortShort(row.cohort_text), instructorName(row), pretty(row.class_date), row.session_kind, isTeam ? (row.course_name ?? row.course_label) : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <TableCell className="max-w-xl py-2">
      {href ? (
        <Link href={href} className="hover:text-primary block truncate font-medium transition-colors">{name}</Link>
      ) : (
        <div className="truncate font-medium">{name}</div>
      )}
      <div className="text-muted-foreground truncate text-xs">{meta}</div>
      <div className="text-muted-foreground/90 mt-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
        <RawStat rating={row.rating} rated={row.num_ratings} attended={row.attended} />
        <span>
          {scored.reason}
          {row.escalated && <Badge variant="destructive" className="ml-1.5 align-middle">Escalated</Badge>}
        </span>
      </div>
    </TableCell>
  );
}
