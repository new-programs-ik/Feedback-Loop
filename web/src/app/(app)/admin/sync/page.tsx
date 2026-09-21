import Link from "next/link";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { getCourses, listPendingSuggestions, listSyncRuns,
  listUnspentTriggers, listUnmappedLabels, listUnresolvedNames } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { AdminNav } from "@/components/admin/admin-nav";
import { BandMix } from "@/components/admin/scoring/band-mix";
import { MapLabels, SyncNowButton } from "@/components/admin/sync/sync-controls";

export const metadata = { title: "Sync" };

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("en-US", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const duration = (r: { duration_ms?: number | null; started_at: string; finished_at: string | null }) => {
  const ms = r.duration_ms ?? (r.finished_at ? +new Date(r.finished_at) - +new Date(r.started_at) : null);
  if (ms == null) return "—";
  return ms < 1000 ? `${ms} ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms / 60000)} min`;
};
const n = (v: number | null | undefined) => (v == null ? "—" : String(v));

/** /admin/sync — every run of the hourly sync, what it could not map or resolve, and the
 *  manual trigger. */
export default async function SyncPage() {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  const [runs, labels, courses, unresolved, suggestions, unspent] = await Promise.all([
    listSyncRuns(25),
    listUnmappedLabels(),
    getCourses(),
    listUnresolvedNames(),
    listPendingSuggestions(),
    listUnspentTriggers(),
  ]);
  const last = runs.rows[0];
  const lastLine = last
    ? [`${last.rows_fetched ?? 0} read`, `${last.rows_upserted ?? 0} written`,
       last.rows_unchanged != null ? `${last.rows_unchanged} unchanged` : null].filter(Boolean).join(" · ")
    : "";

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Sync"
        description={
          last
            ? `Last run ${when(last.finished_at ?? last.started_at)} (${last.trigger}) · ${last.status} · ${lastLine}`
            : "No sync has run yet — it runs at 10:00, 12:00 and 14:00 India time; use Sync now to pull manually."
        }
        actions={<SyncNowButton />}
      />
      <AdminNav />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Stat label="Unmapped course labels" value={labels.length} href={undefined} note="map them below" tone={labels.length ? "warn" : "ok"} />
        <Stat label="Unresolved instructor names" value={unresolved.rows.length} href="/admin/identity" note="link or create on Identity" tone={unresolved.rows.length ? "warn" : "ok"} />
        <Stat label="Suggestions waiting" value={suggestions.rows.length} href="/admin/identity" note="review on Identity" tone={suggestions.rows.length ? "warn" : "ok"} />
        <Stat label="Scheduled runs not picked up" value={unspent.length} href={undefined} note={unspent.length ? `last ${when(unspent[0].created_at)} — the worker did not answer; check Render` : "the worker answered every scheduled run in the last 2 days"} tone={unspent.length ? "warn" : "ok"} />
      </div>

      <section className="bg-card shadow-soft mb-5 overflow-hidden rounded-xl border" aria-labelledby="runs-title">
        <div className="px-4 pt-4 pb-2">
          <h2 id="runs-title" className="text-[14px] font-semibold tracking-[-0.01em]">Last runs</h2>
        </div>
        {runs.error && <p className="text-destructive border-t px-4 py-3 text-[12.5px]">{runs.error}</p>}
        {runs.rows.length === 0 && !runs.error ? (
          <p className="text-muted-foreground border-t px-4 py-6 text-center text-[13px]">Nothing yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead className="text-right">Took</TableHead>
                <TableHead className="text-right">Fetched</TableHead>
                <TableHead className="text-right">Upserted</TableHead>
                <TableHead className="text-right">Scored</TableHead>
                <TableHead className="min-w-32">Bands</TableHead>
                <TableHead className="text-right">Unparsed cohorts</TableHead>
                <TableHead className="text-right">Unresolved</TableHead>
                <TableHead className="text-right">Suggestions</TableHead>
                <TableHead>Error</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Badge variant={r.status === "ok" ? "success" : r.status === "failed" ? "destructive" : "secondary"}>{r.status}</Badge>
                    <span className="text-muted-foreground ml-1.5 text-[11px]">{r.trigger}</span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{when(r.started_at)}</TableCell>
                  <TableNum>{duration(r)}</TableNum>
                  <TableNum>{n(r.rows_fetched)}</TableNum>
                  <TableNum>{n(r.rows_upserted)}</TableNum>
                  <TableNum>
                    {n(r.rows_scored)}
                    {r.scoring_config_version != null && <span className="text-muted-foreground text-[10.5px]"> · v{r.scoring_config_version}</span>}
                  </TableNum>
                  <TableCell>{r.band_counts ? <BandMix counts={r.band_counts} compact /> : <span className="text-muted-foreground">—</span>}</TableCell>
                  <TableNum>{n(r.cohorts_unparsed)}</TableNum>
                  <TableNum>{n(r.instructors_unresolved)}</TableNum>
                  <TableNum>{n(r.suggestions_created)}</TableNum>
                  <TableCell className="text-destructive max-w-64 truncate text-[12px]" title={r.error ?? undefined}>
                    {r.error ?? ""}
                    {!r.error && r.unmapped_labels?.length ? <span className="text-muted-foreground">{r.unmapped_labels.length} unmapped label{r.unmapped_labels.length === 1 ? "" : "s"}</span> : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      <section className="bg-card shadow-soft rounded-xl border p-4 sm:p-5" aria-labelledby="labels-title">
        <h2 id="labels-title" className="text-[14px] font-semibold tracking-[-0.01em]">Unmapped course labels</h2>
        <p className="text-muted-foreground mt-0.5 mb-3 text-[11.5px]">
          Sheet labels not linked to a course — their classes are missing from course pages until mapped. Unresolved instructor names are handled on{" "}
          <Link href="/admin/identity" className="text-primary hover:underline">Identity</Link>.
        </p>
        <MapLabels labels={labels} courses={courses} />
      </section>
    </div>
  );
}

function Stat({ label, value, note, href, tone }: { label: string; value: number; note: string; href?: string; tone: "ok" | "warn" }) {
  const body = (
    <div className="bg-card shadow-soft rounded-xl border p-3.5">
      <p className="text-muted-foreground text-[11px] font-medium">{label}</p>
      <p data-numeric className={`mt-1 text-[24px] leading-none font-semibold tracking-[-0.02em] ${tone === "warn" && value > 0 ? "text-warning" : ""}`}>{value}</p>
      <p className="text-muted-foreground mt-1.5 text-[11px]">{value > 0 ? note : "nothing waiting"}</p>
    </div>
  );
  return href && value > 0 ? <Link href={href} className="block hover:opacity-90">{body}</Link> : body;
}
