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
  searchParams: Promise<{ course?: string }>;
}) {
  const user = await requireUser();
  const sp = await searchParams;
  const supabase = await createClient();

  const { data: courses } = await supabase.from("courses").select("id, name").order("name");
  let q = supabase
    .from("classes")
    .select("id, topic, class_date, rating, status, session_type, course_id, courses(name), instructors(name), analyses(reclass), feedback(status)")
    .order("created_at", { ascending: false });
  if (sp.course) q = q.eq("course_id", sp.course);
  const { data: rows } = await q;
  const classes = (rows ?? []) as Array<Record<string, unknown>>;

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

      {/* Course filter */}
      <form method="get" className="flex items-end gap-2">
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
        <Button type="submit" variant="outline" size="sm">Filter</Button>
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
                <th className="px-4 py-2.5 font-medium">Instructor</th>
                <th className="px-4 py-2.5 font-medium">Type</th>
                <th className="px-4 py-2.5 font-medium">Rating</th>
                <th className="px-4 py-2.5 font-medium">Re-class</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => {
                const course = (c.courses as { name?: string } | null)?.name ?? "—";
                const instructor = (c.instructors as { name?: string } | null)?.name ?? "—";
                const reclass = (c.analyses as Array<{ reclass?: string }> | null)?.[0]?.reclass;
                const rating = c.rating as number | null;
                const status = String(c.status);
                const type = c.session_type === "ars" ? "ARS" : "Live";
                return (
                  <tr key={String(c.id)} className="border-t">
                    <td className="px-4 py-3 font-medium">{String(c.topic)}</td>
                    <td className="text-muted-foreground px-4 py-3">{course}</td>
                    <td className="text-muted-foreground px-4 py-3">{instructor}</td>
                    <td className="px-4 py-3"><Badge variant="outline">{type}</Badge></td>
                    <td className="px-4 py-3">
                      <span className={rating != null && rating < 4.5 ? "text-destructive font-medium" : ""}>
                        {rating != null ? Number(rating).toFixed(2) : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {reclass ? <Badge variant={reclassVariant(reclass)} className="uppercase">{reclass}</Badge>
                               : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3"><Badge variant={statusVariant(status)}>{status.replace("_", " ")}</Badge></td>
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
