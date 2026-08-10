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

  let q = supabase
    .from("classes")
    .select("id, topic, class_date, rating, status, session_type, course_id, created_by, courses(name), analyses(reclass, tokens_in, tokens_out, cost_usd, video_used:result->video->>video_used)")
    .order("class_date", { ascending: false });
  if (sp.course) q = q.eq("course_id", sp.course);
  if (sp.month && /^\d{4}-\d{2}$/.test(sp.month)) {
    const [y, m] = sp.month.split("-").map(Number);
    const start = `${sp.month}-01`;
    const end = m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
    q = q.gte("class_date", start).lt("class_date", end);
  }

  const [{ data: courses }, { data: rows }] = await Promise.all([
    supabase.from("courses").select("id, name").order("name"),
    q,
  ]);
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

  return (
    <div className="animate-in-up space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Feedback</h1>
          <p className="text-muted-foreground mt-1">
            Every analyzed class — review the draft, tweak it, approve it.
          </p>
        </div>
        {user.role !== "learner" && (
          <Button asChild>
            <Link href="/feedback/new"><Plus className="size-4" /> New analysis</Link>
          </Button>
        )}
      </div>

      {/* Filters + in-view totals */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <form method="get" className="flex flex-wrap items-center gap-2">
          <select id="course" name="course" defaultValue={sp.course ?? ""} aria-label="Course"
                  className="border-input bg-card h-9 min-w-48 rounded-md border px-3 text-sm shadow-sm">
            <option value="">All courses</option>
            {((courses ?? []) as Array<{ id: string; name: string }>).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <input id="month" name="month" type="month" defaultValue={sp.month ?? ""} aria-label="Month"
                 className="border-input bg-card h-9 rounded-md border px-3 text-sm shadow-sm" />
          <Button type="submit" variant="outline" size="sm">Filter</Button>
          {(sp.course || sp.month) && (
            <Button asChild variant="ghost" size="sm"><Link href="/feedback">Clear</Link></Button>
          )}
        </form>
        {classes.length > 0 && (
          <p className="text-muted-foreground text-sm" data-numeric>
            {classes.length} {classes.length === 1 ? "class" : "classes"}
            {(sp.course || sp.month) ? " (filtered)" : ""} · {(totalTokens / 1000).toFixed(1)}k tokens ·{" "}
            <span className="text-foreground font-semibold">${totalCost.toFixed(2)}</span>
          </p>
        )}
      </div>

      {classes.length === 0 ? (
        <Card className="shadow-soft">
          <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <div className="bg-muted flex size-12 items-center justify-center rounded-full">
              <Inbox className="text-muted-foreground size-6" />
            </div>
            <div className="font-medium">No analyses yet</div>
            <p className="text-muted-foreground max-w-sm text-sm">
              Click <strong>New analysis</strong> to turn a class recording into a reviewed feedback draft.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="shadow-soft overflow-hidden rounded-xl border">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-muted-foreground text-left">
                <tr className="[&>th]:px-4 [&>th]:py-2.5 [&>th]:text-[12px] [&>th]:font-semibold [&>th]:tracking-wide [&>th]:uppercase">
                  <th>Class</th>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Rating</th>
                  <th>Cost</th>
                  <th>Re-class</th>
                  <th>Status</th>
                  <th>By</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {classes.map((c) => {
                  const course = (c.courses as { name?: string } | null)?.name ?? "—";
                  const a = (c.analyses as Array<{ reclass?: string; cost_usd?: number; video_used?: string }> | null)?.[0];
                  const reclass = a?.reclass;
                  const cost = Number(a?.cost_usd ?? 0);
                  const videoUsed = a?.video_used === "true";
                  const rating = c.rating as number | null;
                  const status = String(c.status);
                  return (
                    <tr key={String(c.id)} className="hover:bg-accent/30 border-t transition-colors">
                      <td className="max-w-72 px-4 py-3">
                        <Link href={`/feedback/${String(c.id)}`} className="hover:text-primary block truncate font-medium transition-colors">
                          {String(c.topic)}
                        </Link>
                        <span className="text-muted-foreground text-xs">{course}</span>
                      </td>
                      <td className="text-muted-foreground px-4 py-3 whitespace-nowrap">{String(c.class_date ?? "—")}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1">
                          <Badge variant="outline">{c.session_type === "ars" ? "ARS" : "Live"}</Badge>
                          {videoUsed && <span title="Video verified — the recording was analyzed">🎬</span>}
                        </span>
                      </td>
                      <td className="px-4 py-3" data-numeric>
                        <span className={rating != null && rating < 4.5 ? "text-destructive font-semibold" : "font-medium"}>
                          {rating != null ? Number(rating).toFixed(2) : "—"}
                        </span>
                      </td>
                      <td className="text-muted-foreground px-4 py-3" data-numeric>{cost > 0 ? `$${cost.toFixed(2)}` : "—"}</td>
                      <td className="px-4 py-3">
                        {reclass ? <Badge variant={reclassVariant(reclass)} className="uppercase">{reclass}</Badge>
                                 : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="px-4 py-3"><Badge variant={statusVariant(status)}>{status.replace("_", " ")}</Badge></td>
                      <td className="text-muted-foreground px-4 py-3 text-xs">{creatorName.get(String(c.created_by)) ?? "—"}</td>
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
        </div>
      )}
    </div>
  );
}
