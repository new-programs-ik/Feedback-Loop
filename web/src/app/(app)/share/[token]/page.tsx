import { Link2Off } from "lucide-react";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { fetchShareRows, getCourses, getShareByToken, shareState, type ShareClassRow } from "@/lib/admin";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ScorePill } from "@/components/score/score-pill";
import { BandMix } from "@/components/admin/scoring/band-mix";
import { CourseSquare } from "@/components/admin/course-square";

export const metadata = { title: "Shared report" };

const pretty = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—");
const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const fmt2 = (v: number | null) => (v == null ? "—" : v.toFixed(2));

function pooledApproval(rows: ShareClassRow[]) {
  let yes = 0, votes = 0;
  for (const r of rows) {
    if (r.yes_votes == null || r.no_votes == null) continue;
    yes += r.yes_votes;
    votes += r.yes_votes + r.no_votes;
  }
  return votes ? (yes / votes) * 100 : null;
}

/** /share/[token] — the read-only report behind a share link: no filters, no actions, no
 *  drawer. Checks revocation and expiry; still needs an IK sign-in (the route group's layout). */
export default async function SharedReportPage({ params }: { params: Promise<{ token: string }> }) {
  const viewer = await requireUser();
  if (viewer.role !== "admin" && viewer.role !== "pm") redirect("/");   // course data is staff-only
  const { token } = await params;
  const share = await getShareByToken(token);
  const state = share ? shareState(share) : null;

  if (!share || state !== "live") {
    return (
      <div className="bg-card shadow-soft mx-auto mt-10 max-w-lg rounded-xl border">
        <EmptyState
          icon={Link2Off}
          title={!share ? "This link is not valid" : state === "revoked" ? "This link was withdrawn" : "This link has expired"}
          description={!share ? "Check the address, or ask for a new link." : "Ask the person who shared it for a fresh link."}
        />
      </div>
    );
  }

  const [rows, courses] = await Promise.all([fetchShareRows(share.period.from, share.period.to, share.course_id), getCourses()]);
  const course = share.course_id ? courses.find((c) => c.id === share.course_id) : null;
  const scored = rows.filter((r) => r.score != null);
  const bands = { excellent: 0, good: 0, average: 0, bad: 0, no_data: 0 };
  for (const r of rows) bands[r.band ?? "no_data"] += 1;
  const hasBands = scored.length > 0;
  const avgScore = avg(scored.map((r) => r.score!));
  const avgRating = avg(rows.map((r) => r.rating));
  const approval = pooledApproval(rows);
  const reach = avg(rows.filter((r) => r.num_ratings != null && r.attended).map((r) => (r.num_ratings! / r.attended!) * 100));
  const videos = rows.filter((r) => r.action === "video").length;
  const transcripts = rows.filter((r) => r.action === "transcript").length;
  const worst = [...rows].sort((a, b) => (a.score ?? a.rating * 20) - (b.score ?? b.rating * 20)).slice(0, 10);
  const byInstructor = new Map<string, ShareClassRow[]>();
  for (const r of rows) byInstructor.set(r.instructor || "(unknown)", [...(byInstructor.get(r.instructor || "(unknown)") ?? []), r]);
  const instructors = [...byInstructor.entries()]
    .map(([name, list]) => ({ name, n: list.length, score: avg(list.map((r) => r.score).filter((v): v is number => v != null)), rating: avg(list.map((r) => r.rating)), approval: pooledApproval(list) }))
    .sort((a, b) => (a.score ?? a.rating! * 20) - (b.score ?? b.rating! * 20));
  const kinds = ["Live Class", "Test Review"].map((k) => {
    const list = rows.filter((r) => r.session_kind === k);
    return { kind: k, n: list.length, score: avg(list.map((r) => r.score).filter((v): v is number => v != null)), rating: avg(list.map((r) => r.rating)), approval: pooledApproval(list) };
  });

  return (
    <article className="mx-auto max-w-5xl" data-slot="shared-report">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div className="flex items-center gap-3">
          {course && <CourseSquare name={course.name} slug={course.slug} color={course.color} initials={course.initials} size="lg" />}
          <div>
            <h1 className="text-lg font-semibold tracking-[-0.01em]">{course?.name ?? "All courses"} · {share.period.label ?? "Report"}</h1>
            <p className="text-muted-foreground text-[13px]">
              {pretty(share.period.from)} – {pretty(share.period.to)} · {rows.length} rated {rows.length === 1 ? "class" : "classes"} · read-only
            </p>
          </div>
        </div>
      </header>

      {rows.length === 0 ? (
        <p className="text-muted-foreground py-10 text-center text-[13px]">No rated classes in this period.</p>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Classes rated" value={String(rows.length)} />
            <Tile label={hasBands ? "Average sentiment score" : "Average rating"} value={hasBands ? String(Math.round(avgScore ?? 0)) : fmt2(avgRating)} note={hasBands ? `avg rating ${fmt2(avgRating)}` : undefined} />
            <Tile label="Would have the instructor back" value={approval == null ? "—" : `${Math.round(approval)}%`} note={reach == null ? undefined : `reach ${Math.round(reach)}% of attendees rated`} />
            <Tile label="Analyses this period" value={String(videos + transcripts)} note={`${videos} video · ${transcripts} transcript`} />
          </div>

          {hasBands && (
            <section className="bg-card shadow-soft rounded-xl border p-4">
              <h2 className="mb-2 text-[13px] font-semibold tracking-[-0.01em]">Band mix</h2>
              <BandMix counts={bands} />
            </section>
          )}

          <section className="bg-card shadow-soft overflow-hidden rounded-xl border">
            <h2 className="px-4 pt-4 pb-2 text-[13px] font-semibold tracking-[-0.01em]">Live classes vs test reviews</h2>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Kind</TableHead>
                  <TableHead className="text-right">Classes</TableHead>
                  <TableHead className="text-right">{hasBands ? "Avg score" : "Avg rating"}</TableHead>
                  <TableHead className="text-right">Approval</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {kinds.map((k) => (
                  <TableRow key={k.kind}>
                    <TableCell className="font-medium">{k.kind}</TableCell>
                    <TableNum>{k.n}</TableNum>
                    <TableNum>{hasBands ? (k.score == null ? "—" : Math.round(k.score)) : fmt2(k.rating)}</TableNum>
                    <TableNum>{k.approval == null ? "—" : `${Math.round(k.approval)}%`}</TableNum>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>

          <section className="bg-card shadow-soft overflow-hidden rounded-xl border">
            <h2 className="px-4 pt-4 pb-2 text-[13px] font-semibold tracking-[-0.01em]">Lowest classes this period</h2>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>{hasBands ? "Score" : "Rating"}</TableHead>
                  <TableHead>Class</TableHead>
                  <TableHead>Instructor</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Vote</TableHead>
                  <TableHead>Outcome</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {worst.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{hasBands ? <ScorePill variant="sm" score={r.score} band={r.band} /> : <span data-numeric className="font-semibold">{r.rating.toFixed(2)}</span>}</TableCell>
                    <TableCell className="max-w-64">
                      <div className="truncate">{r.topic || r.session_kind}</div>
                      <div className="text-muted-foreground text-[11px]">{r.course_name} · {r.session_kind}</div>
                    </TableCell>
                    <TableCell>{r.instructor || "—"}</TableCell>
                    <TableCell className="whitespace-nowrap">{pretty(r.class_date)}</TableCell>
                    <TableCell data-numeric>{r.yes_votes != null && r.no_votes != null && r.yes_votes + r.no_votes > 0 ? `${r.yes_votes} of ${r.yes_votes + r.no_votes}` : "—"}</TableCell>
                    <TableCell className="capitalize">{r.action ?? "—"}{r.review_status === "analysis_started" ? " · in analysis" : r.review_status === "dismissed" ? " · dismissed" : ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>

          <section className="bg-card shadow-soft overflow-hidden rounded-xl border">
            <h2 className="px-4 pt-4 pb-2 text-[13px] font-semibold tracking-[-0.01em]">Instructors</h2>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Instructor</TableHead>
                  <TableHead className="text-right">Classes</TableHead>
                  <TableHead className="text-right">{hasBands ? "Avg score" : "Avg rating"}</TableHead>
                  <TableHead className="text-right">Approval</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {instructors.slice(0, 40).map((i) => (
                  <TableRow key={i.name}>
                    <TableCell className="font-medium">{i.name}</TableCell>
                    <TableNum>{i.n}</TableNum>
                    <TableNum>{hasBands ? (i.score == null ? "—" : Math.round(i.score)) : fmt2(i.rating)}</TableNum>
                    <TableNum>{i.approval == null ? "—" : `${Math.round(i.approval)}%`}</TableNum>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </section>
        </div>
      )}

      <footer className="text-muted-foreground mt-8 border-t pt-3 text-[12px]">
        Shared by {share.created_by_name ?? "a member of the New Programs team"} · created {when(share.created_at)} · expires {when(share.expires_at)} · read-only view of Feedback Loop
      </footer>
    </article>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="bg-card shadow-soft rounded-xl border p-3.5">
      <p className="text-muted-foreground text-[11px] font-medium">{label}</p>
      <p data-numeric className="mt-1 text-[24px] leading-none font-semibold tracking-[-0.02em]">{value}</p>
      {note && <p className="text-muted-foreground mt-1.5 text-[11px]">{note}</p>}
    </div>
  );
}
