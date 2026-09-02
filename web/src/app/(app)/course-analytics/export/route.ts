import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/session";
import { fetchRatings } from "@/lib/ratings";
import { rangeToDates, type RangePreset } from "@/components/filter-bar";

/** CSV export of the current Course Analytics view (same filters as the page). */
export async function GET(req: NextRequest) {
  const user = await getCurrentUser();
  if (!user || user.role === "learner") return new NextResponse("Unauthorized", { status: 401 });

  const sp = req.nextUrl.searchParams;
  const range = (["7d", "30d", "90d", "month", "custom"].includes(sp.get("range") ?? "")
    ? sp.get("range")
    : "90d") as RangePreset;
  const { from, to } = rangeToDates(range, sp.get("from") ?? undefined, sp.get("to") ?? undefined);
  const rows = await fetchRatings({ from, to, courseId: sp.get("course") || undefined });

  const esc = (v: unknown) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = "date,course,category,topic,instructor,rating,rated,attended,participation_pct,decision";
  const lines = rows.map((r) =>
    [
      r.class_date,
      esc(r.course_name ?? r.course_label),
      r.session_kind,
      esc(r.topic),
      esc(r.instructor),
      r.rating,
      r.num_ratings ?? "",
      r.attended ?? "",
      r.participation_pct ?? "",
      r.decision,
    ].join(","),
  );
  const csv = [header, ...lines].join("\n");
  return new NextResponse(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="ratings-${from}-to-${to}.csv"`,
    },
  });
}
