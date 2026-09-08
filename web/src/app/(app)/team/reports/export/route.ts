import type { NextRequest } from "next/server";
import { GET as courseExport } from "@/app/(app)/c/[course]/reports/export/route";

/** CSV of every scored class across every course for the report's period. */
export async function GET(req: NextRequest) {
  return courseExport(req, { params: Promise.resolve({ course: "team" }) });
}
