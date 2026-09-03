import { redirect } from "next/navigation";
import { UserCog } from "lucide-react";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { MergeForm } from "./merge-form";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Meter, Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";

export const metadata = { title: "Instructors" };

export default async function InstructorsPage() {
  const user = await requireUser();
  if (user.role !== "admin") redirect("/dashboard");
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
  const maxUses = Math.max(1, ...list.map((i) => uses.get(i.id) ?? 0));

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Instructors"
        description="The sheet has some name variants (e.g. Ahmed / Ahmed Elbagoury). Merge duplicates so analytics stay clean — everything on one name moves to the other."
      />

      <Card className="mb-5">
        <CardHeader className="pb-3">
          <CardTitle className="text-[15px]">Merge duplicates</CardTitle>
          <CardDescription>Pick the duplicate to remove and the correct name to keep.</CardDescription>
        </CardHeader>
        <CardContent>
          <MergeForm instructors={list} />
        </CardContent>
      </Card>

      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        {list.length === 0 ? (
          <EmptyState
            icon={UserCog}
            title="No instructors yet"
            description="Names arrive with the ratings sheet sync and with each new analysis."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Instructor</TableHead>
                <TableHead>Share of references</TableHead>
                <TableHead className="text-right">Used by (classes)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-stagger>
              {list.map((i) => {
                const n = uses.get(i.id) ?? 0;
                return (
                  <TableRow key={i.id}>
                    <TableCell className="font-medium">{i.name}</TableCell>
                    <TableCell>
                      <Meter value={(n / maxUses) * 100} className="[&>span:last-child]:hidden" />
                    </TableCell>
                    <TableNum className={n === 0 ? "text-muted-foreground" : ""}>{n}</TableNum>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
