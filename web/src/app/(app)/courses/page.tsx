import { redirect } from "next/navigation";
import { Library } from "lucide-react";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { AddCourseForm } from "./add-course-form";
import { DeleteCourseButton } from "./delete-course-button";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Table, TableActions, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow,
} from "@/components/ui/table";

export const metadata = { title: "Courses" };

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

  const list = (courses ?? []) as Array<{ id: string; name: string }>;

  return (
    <div className="animate-in-up">
      <PageHeader
        title="Courses"
        description="Add your team's courses (B2B, DSA, System Design…). They appear right away when creating a new analysis."
      />

      <Card className="mb-5">
        <CardHeader className="pb-3">
          <CardTitle className="text-[15px]">Add a course</CardTitle>
          <CardDescription>Any staff member can add one; it&apos;s shared across the whole team.</CardDescription>
        </CardHeader>
        <CardContent><AddCourseForm /></CardContent>
      </Card>

      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        {list.length === 0 ? (
          <EmptyState
            icon={Library}
            title="No courses yet"
            description="Add the first one above — it will be available in New analysis immediately."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Course</TableHead>
                <TableHead className="text-right">Cohorts</TableHead>
                <TableHead className="text-right">Analyses</TableHead>
                <TableHead className="text-right"><span className="sr-only">Actions</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-stagger>
              {list.map((c) => {
                const nCohorts = cohortCount.get(c.id) ?? 0;
                const nClasses = classCount.get(c.id) ?? 0;
                const empty = nCohorts === 0 && nClasses === 0;
                return (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableNum className="text-muted-foreground">{nCohorts}</TableNum>
                    <TableNum className="text-muted-foreground">{nClasses}</TableNum>
                    <TableActions>
                      {user.role === "admin" && empty ? (
                        <DeleteCourseButton courseId={c.id} name={c.name} />
                      ) : (
                        !empty && <Badge variant="outline">in use</Badge>
                      )}
                    </TableActions>
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
