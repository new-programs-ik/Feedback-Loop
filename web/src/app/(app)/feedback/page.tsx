import Link from "next/link";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { DeleteButton } from "./delete-button";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Inbox, Plus } from "lucide-react";

function statusVariant(s: string): "default" | "secondary" | "success" | "warning" | "outline" {
  return s === "approved" || s === "sent" ? "success"
    : s === "draft_ready" ? "warning"
    : s === "analyzing" ? "secondary"
    : "outline";
}
function reclassVariant(r?: string): "destructive" | "warning" | "secondary" {
  return r === "yes" ? "destructive" : r === "maybe" ? "warning" : "secondary";
}

export default async function FeedbackPage({
  searchParams,
}: {
  searchParams: Promise<{ course?: string; month?: string }>;
}) {
  const user = await requireUser();
  const sp = await searchParams;
  const supabase = await createClient();

  const { data: courses } = await supabase.from("courses").select("id, name").order("name");
  let q = supabase
    .from("classes")
    .select("id, topic, class_date, rating, status, session_type, course_id, created_by, courses(name), instructors(name), analyses(reclass, tokens_in, tokens_out), feedback(status)")
    .order("class_date", { ascending: false });
  if (sp.course) q = q.eq("course_id", sp.course);
  if (sp.month && /^\d{4}-\d{2}$/.test(sp.month)) {
    const [y, m] = sp.month.split("-").map(Number);
    const start = `${sp.month}-01`;
    const end = m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
    q = q.gte("class_date", start).lt("class_date", end);
  }
  const { data: rows } = await q;
  const classes = (rows ?? []) as Array<Record<string, unknown>>;

  // resolve "created by" names
  const creatorIds = [...new Set(classes.map((c) => c.created_by).filter(Boolean) as string[])];
  const creatorName = new Map<string, string>();
  if (creatorIds.length) {
    const { data: profs } = await supabase.from("profiles").select("user_id, full_name, email").in("user_id", creatorIds);
    for (const p of (profs ?? []) as Array<{ user_id: string; full_name?: string; email?: string }>) {
      creatorName.set(p.user_id, p.full_name || (p.email ?? "").split("@")[0] || "—");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Feedback</h1>
          <p className="text-muted-foreground mt-1">
            Analyze a low-rated class and review the instructor feedback before it&apos;s stored.
          </p>
        </div>
        {user.role !== "learner" && (
          <Button asChild>
            <Link href="/feedback/new"><Plus className="size-4" /> New analysis</Link>
          </Button>
        )}
      </div>

      {/* Filters */}
      <form method="get" className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <label htmlFor="course" className="text-muted-foreground text-xs font-medium">Course</label>
          <select id="course" name="course" defaultValue={sp.course ?? ""}
                  className="border-input h-9 min-w-56 rounded-md border bg-transparent px-3 text-sm">
            <option value="">All courses</option>
            {((courses ?? []) as Array<{ id: string; name: string }>).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="month" className="text-muted-foreground text-xs font-medium">Month</label>
          <input id="month" name="month" type="month" defaultValue={sp.month ?? ""}
                 className="border-input h-9 rounded-md border bg-transparent px-3 text-sm" />
        </div>
        <Button type="submit" variant="outline" size="sm">Filter</Button>
        {(sp.course || sp.month) && (
          <Button asChild variant="ghost" size="sm"><Link href="/feedback">Clear</Link></Button>
        )}
      </form>

      {classes.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <div className="bg-muted flex size-12 items-center justify-center rounded-full">
              <Inbox className="text-muted-foreground size-6" />
            </div>
            <div className="font-medium">No analyses yet</div>
            <p className="text-muted-foreground max-w-sm text-sm">
              Click <strong>New analysis</strong> to turn a class recording into a reviewed instructor feedback draft.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground text-left">
              <tr>
                <th className="px-4 py-2.5 font-medium">Class</th>
                <th className="px-4 py-2.5 font-medium">Course</th>
                <th className="px-4 py-2.5 font-medium">Date</th>
                <th className="px-4 py-2.5 font-medium">Type</th>
                <th className="px-4 py-2.5 font-medium">Rating</th>
                <th className="px-4 py-2.5 font-medium">Tokens</th>
                <th className="px-4 py-2.5 font-medium">Re-class</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">By</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => {
                const course = (c.courses as { name?: string } | null)?.name ?? "—";
                const a = (c.analyses as Array<{ reclass?: string; tokens_in?: number; tokens_out?: number }> | null)?.[0];
                const reclass = a?.reclass;
                const tokens = (a?.tokens_in ?? 0) + (a?.tokens_out ?? 0);
                const rating = c.rating as number | null;
                const status = String(c.status);
                const type = c.session_type === "ars" ? "ARS" : "Live";
                return (
                  <tr key={String(c.id)} className="border-t">
                    <td className="px-4 py-3 font-medium">{String(c.topic)}</td>
                    <td className="text-muted-foreground px-4 py-3">{course}</td>
                    <td className="text-muted-foreground whitespace-nowrap px-4 py-3">{String(c.class_date ?? "—")}</td>
                    <td className="px-4 py-3"><Badge variant="outline">{type}</Badge></td>
                    <td className="px-4 py-3">
                      <span className={rating != null && rating < 4.5 ? "text-destructive font-medium" : ""}>
                        {rating != null ? Number(rating).toFixed(2) : "—"}
                      </span>
                    </td>
                    <td className="text-muted-foreground px-4 py-3">{tokens > 0 ? `${(tokens / 1000).toFixed(1)}k` : "—"}</td>
                    <td className="px-4 py-3">
                      {reclass ? <Badge variant={reclassVariant(reclass)} className="uppercase">{reclass}</Badge>
                               : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3"><Badge variant={statusVariant(status)}>{status.replace("_", " ")}</Badge></td>
                    <td className="text-muted-foreground px-4 py-3">{creatorName.get(String(c.created_by)) ?? "—"}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button asChild variant="outline" size="sm">
                          <Link href={`/feedback/${String(c.id)}`}>Open</Link>
                        </Button>
                        <DeleteButton classId={String(c.id)} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
