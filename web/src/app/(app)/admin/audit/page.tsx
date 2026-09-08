import Link from "next/link";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { listAudit } from "@/lib/admin";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AdminNav } from "@/components/admin/admin-nav";

export const metadata = { title: "Audit log" };

const PAGE_SIZE = 50;
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

const TONE: Record<string, "success" | "destructive" | "warning" | "secondary" | "outline"> = {
  scoring_published: "success",
  scoring_rolled_back: "warning",
  instructor_merged: "warning",
  instructor_merge_undone: "warning",
  course_handed_over: "warning",
  error: "destructive",
  deleted: "destructive",
  course_member_removed: "destructive",
  share_link_revoked: "destructive",
};

/** /admin/audit — every meaningful action, newest first: who, what, the detail JSON. */
export default async function AuditPage({ searchParams }: { searchParams: Promise<{ page?: string; action?: string }> }) {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/");
  const sp = await searchParams;
  const page = Math.max(0, parseInt(sp.page ?? "0", 10) || 0);
  const action = (sp.action ?? "").trim();
  const { rows, total, error } = await listAudit({ page, pageSize: PAGE_SIZE, action: action || undefined });
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const href = (p: number) => `/admin/audit?${new URLSearchParams({ ...(action ? { action } : {}), ...(p ? { page: String(p) } : {}) }).toString()}`;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Audit log"
        description={`${total.toLocaleString()} entries${action ? ` for “${action}”` : ""} · page ${page + 1} of ${pages}`}
        actions={
          <form method="get" action="/admin/audit" className="flex items-center gap-2">
            <Input name="action" defaultValue={action} placeholder="Filter by action, e.g. scoring_published" aria-label="Action filter" className="w-72" />
            <Button type="submit" variant="outline" size="sm">Filter</Button>
            {action && (
              <Button asChild variant="ghost" size="sm">
                <Link href="/admin/audit">Clear</Link>
              </Button>
            )}
          </form>
        }
      />
      <AdminNav />
      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        {error && <p className="text-destructive px-4 py-3 text-[12.5px]">{error}</p>}
        {rows.length === 0 && !error ? (
          <p className="text-muted-foreground px-4 py-8 text-center text-[13px]">Nothing recorded{action ? " for that action" : " yet"}.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>When</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => {
                const detail = r.detail ? JSON.stringify(r.detail) : "";
                return (
                  <TableRow key={r.id}>
                    <TableCell className="whitespace-nowrap">{when(r.created_at)}</TableCell>
                    <TableCell>
                      <div className="font-medium">{r.actor_name ?? r.actor_label ?? "system"}</div>
                      {r.actor_name && r.actor_label && r.actor_name !== r.actor_label && <div className="text-muted-foreground text-[11px]">{r.actor_label}</div>}
                    </TableCell>
                    <TableCell>
                      <Link href={`/admin/audit?action=${encodeURIComponent(r.action)}`} className="hover:opacity-80" title={`Only “${r.action}” entries`}>
                        <Badge variant={TONE[r.action] ?? "outline"} className="font-mono text-[11px]">{r.action}</Badge>
                      </Link>
                      {r.class_id && (
                        <Link href={`/feedback/${r.class_id}`} className="text-primary ml-2 text-[11px] hover:underline">
                          class
                        </Link>
                      )}
                    </TableCell>
                    <TableCell className="max-w-xl">
                      {detail.length > 110 ? (
                        <details>
                          <summary className="text-muted-foreground cursor-pointer truncate font-mono text-[11px] select-none">{detail.slice(0, 110)}…</summary>
                          <pre className="bg-muted mt-1 max-h-64 overflow-auto rounded-md p-2 font-mono text-[11px] whitespace-pre-wrap">{JSON.stringify(r.detail, null, 2)}</pre>
                        </details>
                      ) : (
                        <code className="text-muted-foreground font-mono text-[11px]">{detail || "—"}</code>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        <div className="flex items-center justify-between border-t px-4 py-2.5 text-[12px]">
          <span className="text-muted-foreground">Showing {rows.length ? page * PAGE_SIZE + 1 : 0}–{page * PAGE_SIZE + rows.length} of {total.toLocaleString()}</span>
          <div className="flex gap-1">
            <Button asChild variant="ghost" size="sm" disabled={page === 0}>
              <Link href={href(Math.max(0, page - 1))} aria-disabled={page === 0} className={page === 0 ? "pointer-events-none opacity-50" : undefined}>Newer</Link>
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link href={href(page + 1)} aria-disabled={page + 1 >= pages} className={page + 1 >= pages ? "pointer-events-none opacity-50" : undefined}>Older</Link>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
