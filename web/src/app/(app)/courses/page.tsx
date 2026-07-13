import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { deleteCourse } from "./actions";
import { AddCourseForm } from "./add-course-form";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Trash2 } from "lucide-react";

export default async function CoursesPage() {
  const user = await requireUser();
  if (user.role === "learner") redirect("/dashboard");
  const supabase = await createClient();

  const [{ data: courses }, { data: cohorts }, { data: classes }] = await Promise.all([
    supabase.from("courses").select("id, name").order("name"),
    supabase.from("cohorts").select("course_id"),
    supabase.from("classes").select("course_id"),
  ]);
  const cohortCount = new Map<string, number>();
  for (const c of (cohorts ?? []) as Array<{ course_id: string }>) cohortCount.set(c.course_id, (cohortCount.get(c.course_id) ?? 0) + 1);
  const classCount = new Map<string, number>();
  for (const c of (classes ?? []) as Array<{ course_id: string }>) classCount.set(c.course_id, (classCount.get(c.course_id) ?? 0) + 1);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Courses</h1>
        <p className="text-muted-foreground mt-1">
          Add your team&apos;s courses (B2B, DSA, System Design…). They appear right away when creating a new analysis.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Add a course</CardTitle>
          <CardDescription>Any staff member can add one; it&apos;s shared across the whole team.</CardDescription>
        </CardHeader>
        <CardContent><AddCourseForm /></CardContent>
      </Card>

      <div className="overflow-hidden rounded-xl border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-left">
            <tr>
              <th className="px-4 py-2.5 font-medium">Course</th>
              <th className="px-4 py-2.5 font-medium">Cohorts</th>
              <th className="px-4 py-2.5 font-medium">Analyses</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {((courses ?? []) as Array<{ id: string; name: string }>).map((c) => {
              const nCohorts = cohortCount.get(c.id) ?? 0;
              const nClasses = classCount.get(c.id) ?? 0;
              const empty = nCohorts === 0 && nClasses === 0;
              return (
                <tr key={c.id} className="border-t">
                  <td className="px-4 py-3 font-medium">{c.name}</td>
                  <td className="text-muted-foreground px-4 py-3">{nCohorts}</td>
                  <td className="text-muted-foreground px-4 py-3">{nClasses}</td>
                  <td className="px-4 py-3 text-right">
                    {user.role === "admin" && empty ? (
                      <form action={deleteCourse}>
                        <input type="hidden" name="course_id" value={c.id} />
                        <Button type="submit" variant="ghost" size="icon" title="Delete (empty course)"
                                className="text-muted-foreground hover:text-destructive">
                          <Trash2 className="size-4" />
                        </Button>
                      </form>
                    ) : (
                      !empty && <Badge variant="secondary">in use</Badge>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
