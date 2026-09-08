"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Check, Copy, Link2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CourseRow, SharePeriod, ShareRow } from "@/lib/admin";
import { createShareLink, revokeShareLink } from "@/app/(app)/admin/actions";
import { ConfirmDialog } from "./confirm-dialog";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const when = (s: string | null) => (s ? new Date(s).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—");
const pretty = (s: string) => new Date(s + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
/** live / expired / revoked — time-dependent by nature, so it lives outside render. */
const shareStatus = (s: ShareRow): "live" | "expired" | "revoked" =>
  s.revoked_at ? "revoked" : s.expires_at && +new Date(s.expires_at) < Date.now() ? "expired" : "live";

/** Read-only report links: create (period + expiry), copy, revoke. `courseId` scopes the list
 *  and the new link to one course; with `courses` given and no courseId, the form offers a
 *  course picker (or "All courses"). */
export function ShareLinks({
  shares,
  courseId,
  courses,
  canCreate,
}: {
  shares: ShareRow[];
  courseId: string | null;
  courses?: CourseRow[];
  canCreate: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [kind, setKind] = React.useState<SharePeriod["kind"]>("weekly");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [days, setDays] = React.useState("30");
  const [pickCourse, setPickCourse] = React.useState(courseId ?? "");
  const [created, setCreated] = React.useState<string | null>(null);
  const [revokeId, setRevokeId] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState<string | null>(null);

  const periodNow = (): SharePeriod => {
    const today = new Date();
    if (kind === "monthly") return { kind, from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(today), label: "This month" };
    if (kind === "custom") return { kind, from, to, label: "Custom range" };
    const start = new Date(today);
    start.setDate(start.getDate() - 6);
    return { kind: "weekly", from: iso(start), to: iso(today), label: "This week" };
  };

  const create = () =>
    startTransition(async () => {
      const p = periodNow();
      const r = await createShareLink({ courseId: courseId ?? (pickCourse || null), period: p, expiresInDays: Number(days) });
      if (!r.ok) {
        toast.error("Could not create the link", { description: r.error });
        return;
      }
      const url = `${window.location.origin}${r.data.path}`;
      setCreated(url);
      toast.success("Share link created", { description: `Expires ${when(r.data.expires_at)}.` });
      router.refresh();
    });

  const copy = async (url: string, id: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(id);
      window.setTimeout(() => setCopied((c) => (c === id ? null : c)), 1600);
    } catch {
      toast("Copy blocked by the browser", { description: url });
    }
  };

  const revoke = () =>
    startTransition(async () => {
      if (!revokeId) return;
      const r = await revokeShareLink({ id: revokeId });
      setRevokeId(null);
      if (!r.ok) {
        toast.error("Could not revoke", { description: r.error });
        return;
      }
      toast.success("Link revoked", { description: "Anyone opening it now sees that it was withdrawn." });
      router.refresh();
    });

  const courseName = (id: string | null) => (id ? (courses?.find((c) => c.id === id)?.name ?? "Course") : "All courses");
  const customOk = kind !== "custom" || (/^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) && from <= to);

  return (
    <div className="space-y-4" data-slot="share-links">
      {canCreate && (
        <div className="bg-card shadow-soft rounded-xl border p-4">
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">New read-only link</h3>
          <p className="text-muted-foreground text-[11.5px]">For leadership: the report for a period, no actions, no drawer. Needs an IK sign-in to open; revocable any time.</p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            {!courseId && courses && (
              <label className="block space-y-1">
                <span className="text-muted-foreground block text-[11px] font-medium">Course</span>
                <Select value={pickCourse} onChange={(e) => setPickCourse(e.target.value)} className="w-52" aria-label="Course">
                  <option value="">All courses</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </Select>
              </label>
            )}
            <label className="block space-y-1">
              <span className="text-muted-foreground block text-[11px] font-medium">Period</span>
              <Select value={kind} onChange={(e) => setKind(e.target.value as SharePeriod["kind"])} className="w-40" aria-label="Period">
                <option value="weekly">This week</option>
                <option value="monthly">This month</option>
                <option value="custom">Custom range</option>
              </Select>
            </label>
            {kind === "custom" && (
              <>
                <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" className="w-[9.75rem]" />
                <span className="text-muted-foreground pb-2 text-sm">to</span>
                <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" className="w-[9.75rem]" />
              </>
            )}
            <label className="block space-y-1">
              <span className="text-muted-foreground block text-[11px] font-medium">Expires in</span>
              <Select value={days} onChange={(e) => setDays(e.target.value)} className="w-28" aria-label="Expiry">
                <option value="7">7 days</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
              </Select>
            </label>
            <Button type="button" onClick={create} disabled={pending || !customOk}>
              <Link2 aria-hidden /> Create link
            </Button>
          </div>
          {created && (
            <div className="surface-inset mt-3 flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-[12px]">
              <code className="min-w-0 flex-1 truncate font-mono">{created}</code>
              <Button type="button" size="sm" variant="outline" onClick={() => copy(created, "new")}>
                {copied === "new" ? <Check aria-hidden /> : <Copy aria-hidden />} {copied === "new" ? "Copied" : "Copy"}
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        {shares.length === 0 ? (
          <p className="text-muted-foreground px-4 py-6 text-center text-[13px]">No share links yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {!courseId && <TableHead>Course</TableHead>}
                <TableHead>Period</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shares.map((s) => {
                const status = shareStatus(s);
                return (
                  <TableRow key={s.id} className={status !== "live" ? "opacity-60" : undefined}>
                    {!courseId && <TableCell>{courseName(s.course_id)}</TableCell>}
                    <TableCell className="whitespace-nowrap">
                      {s.period?.label ?? s.period?.kind} · {pretty(s.period.from)} – {pretty(s.period.to)}
                    </TableCell>
                    <TableCell className="text-[12px] whitespace-nowrap">
                      {s.created_by_name ?? "—"} · {when(s.created_at)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{when(s.expires_at)}</TableCell>
                    <TableCell>
                      <span className={status === "live" ? "text-success text-[12px] font-medium" : "text-muted-foreground text-[12px]"}>{status}</span>
                    </TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1">
                        {status === "live" && (
                          <Button type="button" size="sm" variant="ghost" onClick={() => copy(`${window.location.origin}/share/${s.token}`, s.id)}>
                            {copied === s.id ? <Check aria-hidden /> : <Copy aria-hidden />} {copied === s.id ? "Copied" : "Copy"}
                          </Button>
                        )}
                        {status === "live" && canCreate && (
                          <Button type="button" size="sm" variant="ghost" className="text-destructive" onClick={() => setRevokeId(s.id)} disabled={pending}>
                            <Trash2 aria-hidden /> Revoke
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
      <ConfirmDialog
        open={!!revokeId}
        title="Revoke this link?"
        description="Anyone who has it will see that it was withdrawn. This cannot be undone — create a new link instead."
        confirmLabel="Revoke"
        destructive
        busy={pending}
        onConfirm={revoke}
        onClose={() => setRevokeId(null)}
      />
    </div>
  );
}
