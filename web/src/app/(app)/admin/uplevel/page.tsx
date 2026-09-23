import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { getIntegrationStatus } from "@/lib/integrations";
import { PageHeader } from "@/components/page-header";
import { AdminNav } from "@/components/admin/admin-nav";
import { Badge } from "@/components/ui/badge";
import { UplevelConnect } from "@/components/admin/uplevel/uplevel-connect";

export const metadata = { title: "UpLevel" };
// The test asks the worker, which can take up to a minute to wake on the free plan.
export const maxDuration = 60;

const when = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : null;

const STATE: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "outline" }> = {
  ok: { label: "Connected", variant: "success" },
  unknown: { label: "Saved, not tested yet", variant: "outline" },
  expired: { label: "Expired", variant: "destructive" },
  not_set: { label: "Not connected", variant: "warning" },
  error: { label: "Error", variant: "destructive" },
};

/** /admin/uplevel — the connection that lets the New-analysis form find each class's recording
 *  (its Vimeo link) on UpLevel by itself. UpLevel has no service token yet, so an admin pastes a
 *  signed-in session here; it lasts about two weeks, or until its owner logs out of UpLevel. */
export default async function UplevelPage() {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  const status = await getIntegrationStatus("uplevel");
  const state = status?.state ?? "not_set";
  const s = STATE[state] ?? STATE.unknown;
  const connected = state === "ok" || state === "unknown" || state === "expired";

  return (
    <div className="animate-in-up max-w-3xl">
      <PageHeader
        title="UpLevel"
        description="Lets the New-analysis form find each class's recording link by itself: the class name, date, instructor and type are matched on UpLevel's Videos list."
      />
      <AdminNav />

      <section className="bg-card shadow-soft mb-5 rounded-xl border p-4" aria-labelledby="uplevel-status">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="uplevel-status" className="text-[14px] font-semibold">Connection</h2>
          <Badge variant={s.variant}>{s.label}</Badge>
        </div>
        <dl className="text-muted-foreground mt-3 grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
          {status?.set_at && (
            <div><dt className="inline">Connected </dt><dd className="text-foreground inline">{when(status.set_at)}{status.set_by_label && <> by {status.set_by_label}</>}</dd></div>
          )}
          {status?.last_ok_at && (
            <div><dt className="inline">Last worked </dt><dd className="text-foreground inline">{when(status.last_ok_at)}</dd></div>
          )}
          {status?.last_error_at && state !== "ok" && (
            <div><dt className="inline">Last refused </dt><dd className="text-foreground inline">{when(status.last_error_at)}</dd></div>
          )}
        </dl>
        {status?.detail && <p className="text-muted-foreground mt-2 text-[13px]">{status.detail}</p>}
        {state === "expired" && (
          <p className="text-destructive mt-2 text-[13px] font-medium">
            UpLevel no longer accepts the saved session. Paste a fresh one below: the form asks for links by hand until you do.
          </p>
        )}
      </section>

      <section className="bg-card shadow-soft mb-5 rounded-xl border p-4" aria-labelledby="uplevel-connect">
        <h2 id="uplevel-connect" className="mb-3 text-[14px] font-semibold">
          {connected ? "Paste a fresh session" : "Connect UpLevel"}
        </h2>
        <UplevelConnect connected={connected} />
      </section>

      <section className="text-muted-foreground rounded-xl border border-dashed p-4 text-[13px] leading-relaxed">
        <h2 className="text-foreground mb-1 text-[13.5px] font-semibold">How long it lasts, and the permanent fix</h2>
        A session lasts about two weeks, or until the person who copied it logs out of UpLevel. When it stops
        working, this page and the New-analysis form say so, and the form falls back to pasting the link by hand;
        nothing else breaks. The permanent fix is a service token from the UpLevel platform team (read-only access to
        the Videos list). When they provide one, it replaces this paste and nothing on this page is needed.
      </section>
    </div>
  );
}
