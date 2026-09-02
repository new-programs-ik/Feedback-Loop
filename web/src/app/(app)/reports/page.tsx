import Link from "next/link";
import { ArrowRight, FileBarChart2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { AutoSubmit } from "@/components/auto-submit";
import { SegmentedTabs } from "@/components/ui/tabs";
import { Select } from "@/components/ui/select";
import { StatTile } from "@/components/ui/stat-tile";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { SectionHeader } from "@/components/ui/callout";
import { BandDot, Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { Histogram } from "@/components/charts/histogram";
import { fetchRatings, byCourse, bands, liveVsReview, worstClasses, summarize } from "@/lib/ratings";
import { GOOD } from "@/lib/decision";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { PrintButton } from "./print-button";

export const metadata = { title: "Reports" };

const iso = (d: Date) => d.toISOString().slice(0, 10);
const fmtAvg = (v: number | null) => (v == null ? "—" : v.toFixed(2));
const fmtPct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);
const pretty = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });

function periodFor(rangeKind: string, fromQ?: string, toQ?: string) {
  const today = new Date();
  if (rangeKind === "monthly") {
    return { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(today), label: "This month" };
  }
  if (rangeKind === "custom" && fromQ && toQ) {
    return { from: fromQ, to: toQ, label: "Custom range" };
  }
  const start = new Date(today);
  start.setDate(start.getDate() - 6);
  return { from: iso(start), to: iso(today), label: "This week" };
}

export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<{ range?: string; from?: string; to?: string; course?: string }>;
}) {
  await requireUser();
  const sp = await searchParams;
  const kind = ["weekly", "monthly", "custom"].includes(sp.range ?? "") ? sp.range! : "weekly";
  const { from, to, label } = periodFor(kind, sp.from, sp.to);
  const courseId = sp.course || undefined;

  const supabase = await createClient();
  const [rows, coursesRes] = await Promise.all([
    fetchRatings({ from, to, courseId }),
    supabase.from("courses").select("id, name").order("name"),
  ]);
  const courseList = coursesRes.data ?? [];
  const courseName = courseId
    ? (courseList.find((c) => c.id === courseId)?.name ?? "Selected course")
    : null;

  const total = summarize(rows);
  const split = liveVsReview(rows);
  const courseRows = byCourse(rows).sort((a, b) => b.bad - a.bad || b.n - a.n);
  const worst = worstClasses(rows, 10);

  const tab = (r: string) => {
    const p = new URLSearchParams({ range: r });
    if (courseId) p.set("course", courseId);
    return `/reports?${p.toString()}`;
  };
  const courseHref = (id: string) => {
    const p = new URLSearchParams({ range: kind });
    if (kind === "custom") {
      p.set("from", from);
      p.set("to", to);
    }
    p.set("course", id);
    return `/reports?${p.toString()}`;
  };

  return (
    <div className="animate-in-up">
      <PageHeader
        title={courseName ? `Reports · ${courseName}` : "Reports"}
        description={
          courseName
            ? `${label} · ${pretty(from)} – ${pretty(to)} · only ${courseName} classes`
            : `${label} · ${pretty(from)} – ${pretty(to)} · generated live from the synced ratings`
        }
        actions={<PrintButton />}
      />
      <div className="mb-5 flex flex-wrap items-center gap-3" data-print-hide>
        <SegmentedTabs
          ariaLabel="Report period"
          items={[
            { label: "Weekly", href: tab("weekly"), active: kind === "weekly" },
            { label: "Monthly", href: tab("monthly"), active: kind === "monthly" },
            { label: "Custom", href: tab("custom"), active: kind === "custom" },
          ]}
        />
        <form method="get" action="/reports" className="flex items-center gap-2">
          <input type="hidden" name="range" value={kind} />
          {kind === "custom" && (
            <>
              <input type="hidden" name="from" value={from} />
              <input type="hidden" name="to" value={to} />
            </>
          )}
          <AutoSubmit>
            <Select name="course" defaultValue={courseId ?? ""} aria-label="Course" className="w-56">
              <option value="">All courses</option>
              {courseList.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </AutoSubmit>
        </form>
        {kind === "custom" && (
          <form method="get" action="/reports" className="flex items-center gap-2">
            <input type="hidden" name="range" value="custom" />
            {courseId && <input type="hidden" name="course" value={courseId} />}
            <input type="date" name="from" defaultValue={from} aria-label="From date"
                   className="border-input bg-card h-9 rounded-md border px-2.5 text-sm" />
            <span className="text-muted-foreground text-sm">to</span>
            <input type="date" name="to" defaultValue={to} aria-label="To date"
                   className="border-input bg-card h-9 rounded-md border px-2.5 text-sm" />
            <button type="submit" className="bg-primary text-primary-foreground h-9 cursor-pointer rounded-md px-3 text-sm font-medium">
              Apply
            </button>
          </form>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          <EmptyState
            icon={FileBarChart2}
            title={courseId ? "No rated classes for this course in this period" : "No rated classes in this period"}
            description={
              courseId
                ? "Try Monthly, a custom range, or switch back to All courses."
                : "The sheet may not have rows here yet — try Monthly or a custom range."
            }
          />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-stagger>
            <StatTile label="Classes rated" value={total.n} />
            <StatTile label="Average rating" value={fmtAvg(total.avgRating)} />
            <StatTile
              label={`Below ${GOOD}`}
              value={total.bad}
              tone={total.bad > 0 ? "destructive" : "success"}
              note={total.badShare != null ? `${Math.round(total.badShare * 100)}% of classes` : undefined}
            />
            <StatTile label="Avg participation" value={fmtPct(total.avgParticipation)} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div className="bg-card shadow-soft rounded-xl border p-4 sm:p-5">
              <h3 className="mb-3 text-sm font-semibold">Live classes vs test reviews</h3>
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Category</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                    <TableHead className="text-right">Avg rating</TableHead>
                    <TableHead className="text-right">Below {GOOD}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {split.map((s) => (
                    <TableRow key={s.kind}>
                      <TableCell className="font-medium">{s.kind}</TableCell>
                      <TableNum>{s.n}</TableNum>
                      <TableNum>{fmtAvg(s.avgRating)}</TableNum>
                      <TableNum className={s.bad ? "text-destructive font-semibold" : ""}>{s.bad}</TableNum>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <ChartCard
              title="How the ratings spread"
              subtitle={`Ordered bands, worst → best; the ${GOOD} line separates the middle`}
              table={{
                headers: ["Band", "Classes"],
                rows: bands(rows).map((b) => [b.label.replace("|", " — "), b.count]),
              }}
            >
              <Histogram bands={bands(rows)} />
            </ChartCard>
          </div>

          {!courseId && (
            <div className="bg-card shadow-soft mt-4 overflow-hidden rounded-xl border">
              <div className="px-4 pt-4 sm:px-5">
                <h3 className="text-sm font-semibold">By course</h3>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Course</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                    <TableHead className="text-right">Avg rating</TableHead>
                    <TableHead className="text-right">Below {GOOD}</TableHead>
                    <TableHead className="text-right">Participation</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {courseRows.map((c) => (
                    <TableRow key={c.key}>
                      <TableCell className="font-medium">{c.name}</TableCell>
                      <TableNum>{c.n}</TableNum>
                      <TableNum>{fmtAvg(c.avgRating)}</TableNum>
                      <TableNum className={c.bad ? "text-destructive font-semibold" : ""}>{c.bad}</TableNum>
                      <TableNum>{fmtPct(c.avgParticipation)}</TableNum>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {worst.length > 0 && (
            <div className="bg-card shadow-soft mt-4 overflow-hidden rounded-xl border">
              <div className="px-4 pt-4 sm:px-5">
                <h3 className="text-sm font-semibold">Lowest-rated classes this period</h3>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Rating</TableHead>
                    <TableHead>Rated</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Course</TableHead>
                    <TableHead>Instructor</TableHead>
                    <TableHead>Rule says</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {worst.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="text-destructive font-semibold" data-numeric>
                        {r.rating.toFixed(2)}
                      </TableCell>
                      <TableCell data-numeric>
                        {r.num_ratings != null && r.attended != null
                          ? `${r.num_ratings} of ${r.attended}`
                          : "—"}
                      </TableCell>
                      <TableCell>{pretty(r.class_date)}</TableCell>
                      <TableCell>{r.session_kind}</TableCell>
                      <TableCell>{r.course_name ?? r.course_label}</TableCell>
                      <TableCell>{r.instructor || "—"}</TableCell>
                      <TableCell>
                        <Badge
                          variant={r.decision === "video" ? "destructive" : r.decision === "transcript" ? "warning" : "secondary"}
                          className="capitalize"
                        >
                          {r.decision}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {!courseId && courseRows.length > 0 && (
            <>
              <SectionHeader title="Course report cards" />
              <p className="text-muted-foreground -mt-2 mb-3 text-[13px]">
                Every course separated out — the same numbers, per course. Open a full report to scope
                the whole page to one course.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                {courseRows.map((c) => {
                  const [live, review] = liveVsReview(c.rows);
                  const worstOf = [...c.rows].sort((a, b) => a.rating - b.rating)[0];
                  const share = Math.round((c.badShare ?? 0) * 100);
                  return (
                    <div key={c.key} className="bg-card shadow-soft break-inside-avoid rounded-xl border p-4 sm:p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold" title={c.name}>{c.name}</h3>
                          <p className="text-muted-foreground mt-0.5 text-xs" data-numeric>
                            {c.n} {c.n === 1 ? "class" : "classes"} rated
                          </p>
                        </div>
                        {c.bad > 0 ? (
                          <span
                            className="bg-destructive/8 text-destructive inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold"
                            data-numeric
                          >
                            {c.bad} below {GOOD}
                            <span className="font-medium opacity-70">· {share}%</span>
                          </span>
                        ) : (
                          <span
                            className="bg-success/10 text-success inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                            data-numeric
                          >
                            0 below {GOOD}
                          </span>
                        )}
                      </div>
                      <div className="mt-3 flex items-baseline gap-1.5">
                        <span data-numeric className="text-[22px] leading-none font-semibold tracking-[-0.02em]">
                          <BandDot
                            tone={
                              c.avgRating != null && c.avgRating < GOOD
                                ? "bad"
                                : c.avgRating != null && c.avgRating < 4.7
                                  ? "warn"
                                  : "good"
                            }
                          />
                          {fmtAvg(c.avgRating)}
                        </span>
                        <span className="text-muted-foreground text-xs">avg rating</span>
                      </div>
                      <div className="text-muted-foreground mt-3 space-y-1 text-[13px] leading-relaxed">
                        <p>
                          {live.n > 0 ? (
                            <>
                              Live classes average{" "}
                              <span className="text-foreground font-semibold" data-numeric>{fmtAvg(live.avgRating)}</span>{" "}
                              across {live.n}
                            </>
                          ) : (
                            <>No live classes</>
                          )}
                          {" · "}
                          {review.n > 0 ? (
                            <>
                              test reviews{" "}
                              <span className="text-foreground font-semibold" data-numeric>{fmtAvg(review.avgRating)}</span>{" "}
                              across {review.n}
                            </>
                          ) : (
                            <>no test reviews</>
                          )}
                        </p>
                        {worstOf && (
                          <p>
                            Worst class{" "}
                            <span
                              className={worstOf.rating < GOOD ? "text-destructive font-semibold" : "text-foreground font-semibold"}
                              data-numeric
                            >
                              {worstOf.rating.toFixed(2)}
                            </span>{" "}
                            · {worstOf.topic || worstOf.session_kind}
                          </p>
                        )}
                      </div>
                      {c.courseId && (
                        <div className="mt-3.5 border-t pt-3" data-print-hide>
                          <Link
                            href={courseHref(c.courseId)}
                            className="text-primary inline-flex items-center gap-1 text-[13px] font-medium hover:underline"
                          >
                            Full report <ArrowRight className="size-3.5" aria-hidden />
                          </Link>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
