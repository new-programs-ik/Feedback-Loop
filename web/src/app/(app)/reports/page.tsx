import { FileBarChart2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { SegmentedTabs } from "@/components/ui/tabs";
import { StatTile } from "@/components/ui/stat-tile";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ChartCard } from "@/components/charts/chart-card";
import { Histogram } from "@/components/charts/histogram";
import { fetchRatings, byCourse, bands, liveVsReview, worstClasses, summarize } from "@/lib/ratings";
import { GOOD } from "@/lib/decision";
import { requireUser } from "@/lib/session";
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
  searchParams: Promise<{ range?: string; from?: string; to?: string }>;
}) {
  await requireUser();
  const sp = await searchParams;
  const kind = ["weekly", "monthly", "custom"].includes(sp.range ?? "") ? sp.range! : "weekly";
  const { from, to, label } = periodFor(kind, sp.from, sp.to);
  const rows = await fetchRatings({ from, to });

  const total = summarize(rows);
  const split = liveVsReview(rows);
  const courseRows = byCourse(rows).sort((a, b) => b.bad - a.bad || b.n - a.n);
  const worst = worstClasses(rows, 10);

  const tab = (r: string) => `/reports?range=${r}`;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Reports"
        description={`${label} · ${pretty(from)} – ${pretty(to)} · generated live from the synced ratings`}
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
        {kind === "custom" && (
          <form method="get" action="/reports" className="flex items-center gap-2">
            <input type="hidden" name="range" value="custom" />
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
            title="No rated classes in this period"
            description="The sheet may not have rows here yet — try Monthly or a custom range."
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
        </>
      )}
    </div>
  );
}
