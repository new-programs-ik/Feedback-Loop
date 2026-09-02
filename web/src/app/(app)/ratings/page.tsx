import Link from "next/link";
import { Clapperboard, Eye, FileText, ListChecks, RefreshCw, TriangleAlert } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { byCourse, fetchRatings, lastSyncRun, type ClassRating } from "@/lib/ratings";
import { GOOD, MIN_VOICES } from "@/lib/decision";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { confirmRating, dismissRating, escalateRating, mapCourseLabel, syncNow } from "./actions";
import { cn } from "@/lib/utils";

export const metadata = { title: "Needs analysis" };

const pretty = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

function DecisionChip({ d }: { d: ClassRating["decision"] }) {
  if (d === "video")
    return (
      <Badge variant="destructive" className="gap-1">
        <Clapperboard className="size-3" aria-hidden /> Video
      </Badge>
    );
  if (d === "transcript")
    return (
      <Badge variant="warning" className="gap-1">
        <FileText className="size-3" aria-hidden /> Transcript
      </Badge>
    );
  return (
    <Badge variant="secondary" className="gap-1">
      <Eye className="size-3" aria-hidden /> Watch
    </Badge>
  );
}

function StatusBadge({ s }: { s: ClassRating["review_status"] }) {
  const map: Record<string, { label: string; variant: "secondary" | "outline" | "success" }> = {
    new: { label: "new", variant: "secondary" },
    notified: { label: "handler pinged", variant: "outline" },
    confirmed: { label: "confirmed", variant: "success" },
  };
  const m = map[s];
  return m ? <Badge variant={m.variant}>{m.label}</Badge> : null;
}

/** Pill link for the course summary row — the active one wears the primary fill. */
function CourseChip({
  href,
  active,
  name,
  count,
}: {
  href: string;
  active: boolean;
  name: string;
  count: number;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "border-transparent bg-primary text-primary-foreground"
          : "bg-card text-muted-foreground hover:text-foreground",
      )}
    >
      <span className="max-w-44 truncate">{name}</span>
      <span data-numeric className={active ? "text-primary-foreground/70" : "text-muted-foreground/70"}>
        {count}
      </span>
    </Link>
  );
}

export default async function RatingsQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ focus?: string; course?: string }>;
}) {
  const user = await requireUser();
  const sp = await searchParams;

  // The queue looks back 45 days — old flags age out of view but stay in the data.
  const to = new Date().toISOString().slice(0, 10);
  const from = new Date(Date.now() - 45 * 86400000).toISOString().slice(0, 10);
  const supabase = await createClient();
  const [rows, run, coursesRes] = await Promise.all([
    fetchRatings({ from, to }),
    lastSyncRun(),
    supabase.from("courses").select("id, name").order("name"),
  ]);

  const actionableAll = rows.filter(
    (r) => ["video", "transcript"].includes(r.decision) && ["new", "notified", "confirmed"].includes(r.review_status),
  );
  const watchAll = rows.filter((r) => r.decision === "watch" && r.review_status !== "dismissed");

  // Course scoping (?course=<uuid>). Chips are computed over the FULL actionable set so the
  // counts stay put while you click between courses; unmapped rows have no uuid to link to,
  // so they appear only under "All" (map them in the hygiene section below).
  const courseChips = byCourse(actionableAll)
    .filter((c) => c.courseId != null)
    .sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
  const courseId = sp.course || undefined;
  const actionable = courseId ? actionableAll.filter((r) => r.course_id === courseId) : actionableAll;
  const watch = courseId ? watchAll.filter((r) => r.course_id === courseId) : watchAll;
  const selectedCourseName = courseId
    ? (coursesRes.data ?? []).find((c) => c.id === courseId)?.name
    : undefined;

  // Keep ?focus= alive when switching course scope.
  const courseHref = (id?: string | null) => {
    const params = new URLSearchParams();
    if (id) params.set("course", id);
    if (sp.focus) params.set("focus", sp.focus);
    const qs = params.toString();
    return qs ? `/ratings?${qs}` : "/ratings";
  };

  const MAX_ROWS = 40;
  const shown = actionable.slice(0, MAX_ROWS);
  const overflow = actionable.length - shown.length;
  const unmappedLabels = [...new Set(rows.filter((r) => !r.course_id).map((r) => r.course_label))];
  const started = rows.filter((r) => r.review_status === "analysis_started").length;

  const syncedAgo = run?.finished_at
    ? Math.round((Date.now() - +new Date(run.finished_at)) / 60000)
    : null;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Needs analysis"
        description={`Classes from the last 45 days that the team rule flags — below ${GOOD} with enough voices behind the score.`}
        actions={
          <form action={syncNow}>
            <Button variant="outline" type="submit">
              <RefreshCw className="size-4" aria-hidden /> Sync now
            </Button>
          </form>
        }
      />

      {/* sync banner */}
      <div
        className={cn(
          "mb-5 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border px-4 py-2.5 text-sm",
          run?.status === "failed"
            ? "border-destructive/40 bg-destructive/5 text-destructive"
            : "bg-card text-muted-foreground",
        )}
      >
        {run ? (
          run.status === "failed" ? (
            <>
              <TriangleAlert className="size-4" aria-hidden />
              <span className="font-medium">Last sync failed:</span>
              <span className="min-w-0 truncate">{run.error}</span>
            </>
          ) : (
            <>
              <span>
                Last synced{" "}
                <span className="text-foreground font-medium">
                  {syncedAgo == null ? "…" : syncedAgo < 1 ? "just now" : syncedAgo < 60 ? `${syncedAgo} min ago` : `${Math.round(syncedAgo / 60)}h ago`}
                </span>{" "}
                ({run.trigger})
              </span>
              <span data-numeric>{run.rows_upserted ?? 0} rows</span>
              <span data-numeric>{run.rows_flagged ?? 0} flagged</span>
              {started > 0 && <span data-numeric>{started} already in analysis</span>}
            </>
          )
        ) : (
          <span>No sync has run yet — the hourly schedule starts at deploy; use Sync now to pull manually.</span>
        )}
      </div>

      {/* course summary chips */}
      {courseChips.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5" data-print-hide>
          <CourseChip href={courseHref()} active={!courseId} name="All" count={actionableAll.length} />
          {courseChips.map((c) => (
            <CourseChip
              key={c.key}
              href={courseHref(c.courseId)}
              active={courseId === c.courseId}
              name={c.name}
              count={c.n}
            />
          ))}
        </div>
      )}

      {actionable.length === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          {actionableAll.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="Nothing needs analysis"
              description={`Every recent class with a trustworthy score is at ${GOOD} or above. That's the good kind of empty.`}
            />
          ) : (
            <EmptyState
              icon={ListChecks}
              title="Nothing for this course"
              description={`${selectedCourseName ?? "This course"} has no classes needing analysis in the last 45 days.`}
              action={
                <Button asChild variant="outline" size="sm">
                  <Link href={courseHref()}>Show all courses</Link>
                </Button>
              }
            />
          )}
        </div>
      ) : (
        <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Rating</TableHead>
                <TableHead>Rated</TableHead>
                <TableHead>Class</TableHead>
                <TableHead>Course</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Rule says</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((r) => (
                <TableRow
                  key={r.id}
                  className={cn(sp.focus === r.id && "bg-accent/60 hover:bg-accent/60")}
                >
                  <TableCell className="text-destructive font-semibold" data-numeric>
                    {r.rating.toFixed(2)}
                  </TableCell>
                  <TableNum className="text-muted-foreground">
                    {r.num_ratings != null && r.attended != null
                      ? `${r.num_ratings}/${r.attended} · ${Math.round(Number(r.participation_pct ?? 0))}%`
                      : "—"}
                  </TableNum>
                  <TableCell className="max-w-56">
                    <div className="truncate font-medium">{r.topic || r.session_kind}</div>
                    <div className="text-muted-foreground truncate text-xs">
                      {r.session_kind}
                      {r.instructor ? ` · ${r.instructor}` : ""}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-40 truncate">{r.course_name ?? r.course_label}</TableCell>
                  <TableCell className="whitespace-nowrap">{pretty(r.class_date)}</TableCell>
                  <TableCell><DecisionChip d={r.decision} /></TableCell>
                  <TableCell><StatusBadge s={r.review_status} /></TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1.5">
                      <Button asChild size="sm">
                        <Link href={`/feedback/new?prefill=${r.id}`}>Analyze</Link>
                      </Button>
                      {r.review_status !== "confirmed" && (
                        <form action={confirmRating}>
                          <input type="hidden" name="id" value={r.id} />
                          <Button variant="outline" size="sm" type="submit">Confirm</Button>
                        </form>
                      )}
                      <form action={dismissRating}>
                        <input type="hidden" name="id" value={r.id} />
                        <Button variant="ghost" size="sm" type="submit">Dismiss</Button>
                      </form>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {overflow > 0 && (
            <div className="text-muted-foreground border-t px-4 py-2.5 text-xs">
              …and <span data-numeric>{overflow}</span> more — narrow by course above to see them.
            </div>
          )}
        </div>
      )}

      {/* watch list */}
      {watch.length > 0 && (
        <details className="bg-card shadow-soft mt-4 rounded-xl border">
          <summary className="cursor-pointer px-4 py-3 text-sm font-semibold select-none sm:px-5">
            Watch list <span className="text-muted-foreground font-normal">— {watch.length} low-rated {watch.length === 1 ? "class" : "classes"} with fewer than {MIN_VOICES} voices (not worth an analysis yet; escalate if you know something&apos;s wrong)</span>
          </summary>
          <Table>
            <TableBody>
              {watch.slice(0, 20).map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-semibold" data-numeric>{r.rating.toFixed(2)}</TableCell>
                  <TableNum className="text-muted-foreground">
                    {r.num_ratings != null && r.attended != null ? `${r.num_ratings}/${r.attended}` : "—"}
                  </TableNum>
                  <TableCell className="max-w-56">
                    <div className="truncate">{r.topic || r.session_kind}</div>
                  </TableCell>
                  <TableCell className="max-w-40 truncate">{r.course_name ?? r.course_label}</TableCell>
                  <TableCell className="whitespace-nowrap">{pretty(r.class_date)}</TableCell>
                  <TableCell className="text-right">
                    <form action={escalateRating}>
                      <input type="hidden" name="id" value={r.id} />
                      <Button variant="outline" size="sm" type="submit">Escalate → video</Button>
                    </form>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      )}

      {/* unmapped labels (admin hygiene) */}
      {unmappedLabels.length > 0 && user.role !== "learner" && (
        <div className="bg-card shadow-soft mt-4 rounded-xl border p-4 sm:p-5">
          <h3 className="text-sm font-semibold">Unmapped course labels</h3>
          <p className="text-muted-foreground mt-0.5 text-xs">
            These sheet labels aren&apos;t linked to a course yet, so their classes are missing from course
            analytics. Map each one once — it sticks for every future sync.
          </p>
          <div className="mt-3 space-y-2">
            {unmappedLabels.map((label) => (
              <form key={label} action={mapCourseLabel} className="flex flex-wrap items-center gap-2">
                <input type="hidden" name="alias" value={label} />
                <Badge variant="outline">{label}</Badge>
                <span className="text-muted-foreground text-sm">→</span>
                <Select name="course_id" defaultValue="" className="w-56" aria-label={`Course for ${label}`}>
                  <option value="" disabled>Pick the course…</option>
                  {(coursesRes.data ?? []).map((c) => (
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
