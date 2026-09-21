import Link from "next/link";
import { Inbox, Plus } from "lucide-react";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";
import { DeleteButton } from "./delete-button";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Table, TableActions, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow,
} from "@/components/ui/table";

export const metadata = { title: "Feedback" };

function statusVariant(s: string): "default" | "secondary" | "success" | "warning" | "outline" | "destructive" {
  return s === "approved" || s === "sent" ? "success"
    : s === "draft_ready" ? "warning"
    : s === "analyzing" || s === "scheduled" ? "secondary"
    : s === "failed" ? "destructive"
    : "outline";
}
function reclassVariant(r?: string): "destructive" | "warning" | "secondary" {
  return r === "yes" ? "destructive" : r === "maybe" ? "warning" : "secondary";
}

/** This course's AI analyses: review the draft, tweak it, approve it. The engine itself
 *  (`/feedback/new`, `/feedback/[id]`) is unchanged and lives at the root. */
export default async function FeedbackPage({
  params,
  searchParams,
}: {
  params: Promise<{ course: string }>;
  searchParams: Promise<{ month?: string }>;
}) {
  const { course } = await params;
  const [ws, user, sp] = await Promise.all([resolveWorkspace(course), requireUser(), searchParams]);
  const supabase = await createClient();
  const basePath = hrefIn(ws.slug, "/feedback");
  const newHref = ws.courseId ? `/feedback/new?course=${ws.courseId}` : "/feedback/new";

  let q = supabase
    .from("classes")
    .select("id, topic, class_date, rating, status, session_type, course_id, created_by, courses(name), analyses(reclass, tokens_in, tokens_out, cost_usd, video_used:result->video->>video_used)")
    .order("class_date", { ascending: false });
  if (ws.courseId) q = q.eq("course_id", ws.courseId);
  if (sp.month && /^\d{4}-\d{2}$/.test(sp.month)) {
    const [y, m] = sp.month.split("-").map(Number);
    const start = `${sp.month}-01`;
    const end = m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
    q = q.gte("class_date", start).lt("class_date", end);
  }
  const { data: rows } = await q;
  const classes = (rows ?? []) as Array<Record<string, unknown>>;

  // Totals for whatever is in view (respects the filters).
  let totalTokens = 0;
  let totalCost = 0;
  for (const c of classes) {
    const a = (c.analyses as Array<{ tokens_in?: number; tokens_out?: number; cost_usd?: number }> | null)?.[0];
    totalTokens += (a?.tokens_in ?? 0) + (a?.tokens_out ?? 0);
    totalCost += Number(a?.cost_usd ?? 0);
  }

  // Resolve "created by" names.
  const creatorIds = [...new Set(classes.map((c) => c.created_by).filter(Boolean) as string[])];
  const creatorName = new Map<string, string>();
  if (creatorIds.length) {
    const { data: profs } = await supabase.from("profiles").select("user_id, full_name, email").in("user_id", creatorIds);
    for (const p of (profs ?? []) as Array<{ user_id: string; full_name?: string; email?: string }>) {
      creatorName.set(p.user_id, p.full_name || (p.email ?? "").split("@")[0] || "—");
    }
  }

  const filtered = !!sp.month;

  return (
    <div>
      <PageHeader
        title="Feedback"
        description={`Every analysed class in ${ws.courseName} — review the draft, tweak it, approve it.`}
        actions={
          user.role !== "learner" && (
            <Button asChild>
              <Link href={newHref}><Plus aria-hidden /> New analysis</Link>
            </Button>
          )
        }
      />

      {/* Filters + in-view totals */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <form method="get" action={basePath} className="flex flex-wrap items-center gap-2">
          <Input id="month" name="month" type="month" defaultValue={sp.month ?? ""} aria-label="Month" className="w-44" />
          <Button type="submit" variant="outline">Filter</Button>
          {filtered && (
            <Button asChild variant="ghost"><Link href={basePath}>Clear</Link></Button>
          )}
        </form>
        {classes.length > 0 && (
          <p className="text-muted-foreground text-[13px]" data-numeric>
            {classes.length} {classes.length === 1 ? "class" : "classes"}
            {filtered ? " (filtered)" : ""} · {(totalTokens / 1000).toFixed(1)}k tokens ·{" "}
            <span className="text-foreground font-semibold">${totalCost.toFixed(2)}</span>
          </p>
        )}
      </div>

      {classes.length === 0 ? (
        <div className="bg-card shadow-soft rounded-xl border">
          <EmptyState
            icon={Inbox}
            title={filtered ? "Nothing in that month." : "No analyses for this course yet."}
            action={
              filtered ? (
                <Button asChild variant="outline" size="sm"><Link href={basePath}>Clear the month</Link></Button>
              ) : user.role !== "learner" ? (
                <Button asChild size="sm">
                  <Link href={newHref}><Plus aria-hidden /> New analysis</Link>
                </Button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Class</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Rating</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead>Re-class</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>By</TableHead>
                <TableHead><span className="sr-only">Actions</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {classes.map((c) => {
                const a = (c.analyses as Array<{ reclass?: string; cost_usd?: number; video_used?: string }> | null)?.[0];
                const reclass = a?.reclass;
                const cost = Number(a?.cost_usd ?? 0);
                const videoUsed = a?.video_used === "true";
                const rating = c.rating as number | null;
                const status = String(c.status);
                const id = String(c.id);
                return (
                  <TableRow key={id}>
                    <TableCell className="max-w-72">
                      <Link href={`/feedback/${id}`} className="hover:text-primary block truncate font-medium transition-colors">
                        {String(c.topic)}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground whitespace-nowrap" data-numeric>{String(c.class_date ?? "—")}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1.5">
                        <Badge variant="outline">{c.session_type === "ars" ? "ARS" : "Live"}</Badge>
                        {videoUsed && <span title="Video verified — the recording was analyzed">🎬</span>}
                      </span>
                    </TableCell>
                    <TableNum>
                      <span className={rating != null && rating < 4.55 ? "text-band-bad-text font-semibold" : "font-medium"}>
                        {rating != null ? Number(rating).toFixed(2) : "—"}
                      </span>
                    </TableNum>
                    <TableNum className="text-muted-foreground">{cost > 0 ? `$${cost.toFixed(2)}` : "—"}</TableNum>
                    <TableCell>
                      {reclass ? <Badge variant={reclassVariant(reclass)} className="uppercase">{reclass}</Badge>
                               : <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell><Badge variant={statusVariant(status)}>{status.replace("_", " ")}</Badge></TableCell>
                    <TableCell className="text-muted-foreground text-xs">{creatorName.get(String(c.created_by)) ?? "—"}</TableCell>
                    <TableActions>
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/feedback/${id}`}>Open</Link>
                      </Button>
                      <DeleteButton classId={id} />
                    </TableActions>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
