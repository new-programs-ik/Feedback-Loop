import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { saveAssignments } from "../feedback/actions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Download } from "lucide-react";

const field =
  "border-input h-8 w-full rounded-md border bg-transparent px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default async function AssignmentsPage({
  searchParams,
}: {
  searchParams: Promise<{ cohort?: string; saved?: string }>;
}) {
  const user = await requireUser();
  if (user.role === "learner") redirect("/dashboard");
  const sp = await searchParams;
  const cohortId = sp.cohort ?? "";

  const supabase = await createClient();
  const [{ data: cohorts }, { data: instructors }] = await Promise.all([
    supabase.from("cohorts").select("id, name, courses(name)").order("name"),
    supabase.from("instructors").select("name").order("name"),
  ]);

  let classes: Array<Record<string, unknown>> = [];
  if (cohortId) {
    const { data } = await supabase
      .from("cohort_classes")
      .select("id, week_no, class_date, topic, instructor:instructor_id(name)")
      .eq("cohort_id", cohortId)
      .order("class_date");
    classes = (data ?? []) as Array<Record<string, unknown>>;
  }
  const instructorNames = ((instructors ?? []) as Array<{ name: string }>).map((i) => i.name);
  const unassigned = classes.filter((c) => !(c.instructor as { name?: string } | null)?.name).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Instructor assignments</h1>
        <p className="text-muted-foreground mt-1">
          Pick a cohort, assign instructors to its classes, and save. Download the updated schedule anytime.
        </p>
      </div>

      {/* Cohort picker */}
      <form method="get" className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <label htmlFor="cohort" className="text-sm font-medium">Cohort</label>
          <select id="cohort" name="cohort" defaultValue={cohortId}
                  className="border-input h-9 min-w-64 rounded-md border bg-transparent px-3 text-sm">
            <option value="">Select a cohort…</option>
            {((cohorts ?? []) as Array<Record<string, unknown>>).map((c) => (
              <option key={String(c.id)} value={String(c.id)}>
                {(c.courses as { name?: string } | null)?.name} · {String(c.name)}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" variant="outline">Load</Button>
      </form>

      {sp.saved && (
        <p className="text-sm text-emerald-600">Saved {sp.saved} class{sp.saved === "1" ? "" : "es"}. ✓</p>
      )}

      {cohortId && (
        classes.length === 0 ? (
          <Card><CardContent className="text-muted-foreground py-10 text-center text-sm">
            No classes found for this cohort.
          </CardContent></Card>
        ) : (
          <form action={saveAssignments} className="space-y-4">
            <input type="hidden" name="cohort_id" value={cohortId} />
            <div className="flex items-center justify-between">
              <div className="text-muted-foreground text-sm">
                {classes.length} classes · <span className={unassigned ? "text-amber-600 font-medium" : ""}>{unassigned} unassigned</span>
              </div>
              <a href={`/assignments/export?cohort=${encodeURIComponent(cohortId)}`}
                 className="text-primary inline-flex items-center gap-1.5 text-sm hover:underline">
                <Download className="size-4" /> Download sheet (CSV)
              </a>
            </div>
            <div className="overflow-hidden rounded-xl border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">Date</th>
                    <th className="px-3 py-2 font-medium">Topic</th>
                    <th className="px-3 py-2 font-medium">Instructor</th>
                  </tr>
                </thead>
                <tbody>
                  {classes.map((c) => {
                    const current = (c.instructor as { name?: string } | null)?.name ?? "";
                    return (
                      <tr key={String(c.id)} className={"border-t " + (current ? "" : "bg-amber-50/50")}>
                        <td className="text-muted-foreground px-3 py-2">{(c.week_no as number) ?? "—"}</td>
                        <td className="text-muted-foreground whitespace-nowrap px-3 py-2">{String(c.class_date ?? "")}</td>
                        <td className="px-3 py-2">{String(c.topic)}</td>
                        <td className="px-3 py-2">
                          <input name={`inst_${String(c.id)}`} defaultValue={current} list="instructor-options"
                                 className={field} placeholder="Assign…" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <datalist id="instructor-options">
              {instructorNames.map((n) => <option key={n} value={n} />)}
            </datalist>
            <Button type="submit">Save assignments</Button>
          </form>
        )
      )}
    </div>
  );
}
