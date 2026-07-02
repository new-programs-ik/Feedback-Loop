import Link from "next/link";
import { requireUser } from "@/lib/session";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MessageSquareText, ArrowRight } from "lucide-react";

export default async function DashboardPage() {
  const user = await requireUser();
  const stats = [
    { label: "Classes analyzed", value: "—", note: "this cohort" },
    { label: "Awaiting review", value: "—", note: "drafts ready" },
    { label: "Approved this week", value: "—", note: "feedback sent" },
    { label: "Avg. class rating", value: "—", note: "flag below 4.5" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {user.name.split(" ").slice(-1)[0]}</h1>
        <p className="text-muted-foreground mt-1">
          New Programs operations console. The <strong>Feedback</strong> module is live; analytics
          modules are rolling out.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="pb-2">
              <CardDescription>{s.label}</CardDescription>
              <CardTitle className="text-3xl">{s.value}</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-muted-foreground text-xs">{s.note}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      {user.role !== "learner" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquareText className="size-5" /> Instructor feedback
            </CardTitle>
            <CardDescription>
              Turn a low-rated class recording into reviewed, ready-to-send instructor feedback.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/feedback">
                Open Feedback <ArrowRight className="size-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-sm">Rolling out next:</span>
        {["Learner Health", "Instructor Analytics", "Course Analytics", "Cohort Analytics"].map((m) => (
          <Badge key={m} variant="secondary">
            {m}
          </Badge>
        ))}
      </div>
    </div>
  );
}
