import { createClient } from "@/lib/supabase/server";

function csv(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function GET(request: Request) {
  const cohortId = new URL(request.url).searchParams.get("cohort");
  if (!cohortId) return new Response("missing cohort", { status: 400 });

  const supabase = await createClient();
  const { data: cohort } = await supabase.from("cohorts").select("name").eq("id", cohortId).maybeSingle();
  const { data: rows } = await supabase
    .from("cohort_classes")
    .select("week_no, class_date, topic, instructor:instructor_id(name), review:review_instructor_id(name), coaching:coaching_instructor_id(name)")
    .eq("cohort_id", cohortId)
    .order("class_date");

  const header = ["Week", "Live Class Date", "Topic", "Instructor", "Thursday Review", "Wednesday Coaching"];
  const lines = [header.join(",")];
  for (const r of (rows ?? []) as Array<Record<string, unknown>>) {
    lines.push([
      csv(r.week_no),
      csv(r.class_date),
      csv(r.topic),
      csv((r.instructor as { name?: string } | null)?.name),
      csv((r.review as { name?: string } | null)?.name),
      csv((r.coaching as { name?: string } | null)?.name),
    ].join(","));
  }
  const body = lines.join("\r\n");
  const name = (cohort?.name ?? "cohort").replace(/[^a-z0-9]+/gi, "_");

  return new Response(body, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${name}_schedule.csv"`,
    },
  });
}
