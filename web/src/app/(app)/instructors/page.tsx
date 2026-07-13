import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { MergeForm } from "./merge-form";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default async function InstructorsPage({
  searchParams,
}: {
  searchParams: Promise<{ merged?: string }>;
}) {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/dashboard");
  const sp = await searchParams;
  const supabase = await createClient();

  const [{ data: instructors }, { data: cc }, { data: cls }] = await Promise.all([
    supabase.from("instructors").select("id, name").order("name"),
    supabase.from("cohort_classes").select("instructor_id, review_instructor_id, coaching_instructor_id"),
    supabase.from("classes").select("instructor_id"),
  ]);

  const uses = new Map<string, number>();
  const bump = (id: unknown) => { if (id) uses.set(String(id), (uses.get(String(id)) ?? 0) + 1); };
  for (const r of (cc ?? []) as Array<Record<string, unknown>>) {
    bump(r.instructor_id); bump(r.review_instructor_id); bump(r.coaching_instructor_id);
  }
  for (const r of (cls ?? []) as Array<{ instructor_id?: string }>) bump(r.instructor_id);

  const list = (instructors ?? []) as Array<{ id: string; name: string }>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Instructors</h1>
        <p className="text-muted-foreground mt-1">
          The sheet has some name variants (e.g. Ahmed / Ahmed Elbagoury). Merge duplicates so
          analytics stay clean — everything on one name moves to the other.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Merge duplicates</CardTitle>
          <CardDescription>Pick the duplicate to remove and the correct name to keep.</CardDescription>
        </CardHeader>
        <CardContent>
          <MergeForm instructors={list} />
          {sp.merged && <p className="mt-3 text-sm text-emerald-600">Merged ✓</p>}
        </CardContent>
      </Card>

      <div className="overflow-hidden rounded-xl border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-left">
            <tr>
              <th className="px-4 py-2.5 font-medium">Instructor</th>
              <th className="px-4 py-2.5 font-medium">Used by (classes)</th>
            </tr>
          </thead>
          <tbody>
            {list.map((i) => (
              <tr key={i.id} className="border-t">
                <td className="px-4 py-3 font-medium">{i.name}</td>
                <td className="text-muted-foreground px-4 py-3">{uses.get(i.id) ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
