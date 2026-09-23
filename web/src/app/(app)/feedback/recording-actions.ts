"use server";

import { getCurrentUser } from "@/lib/session";
import { postToWorker } from "@/lib/worker";

/** One recording on UpLevel that could be the class, as the worker ranked it. */
export type RecordingMatch = {
  vimeo_link: string;
  vimeo_id: string;
  name: string;
  topic: string;
  category: "live_class" | "ars" | "coaching" | null;
  class_date: string | null;
  duration_min: number | null;
  score: number;
  reasons: string[];
};

export type FindRecordingResult = {
  /** ok: matches found · none: looked, found nothing · not_connected / expired: UpLevel login ·
   *  unreachable: could not look · invalid: the class details are not enough to search. */
  status: "ok" | "none" | "not_connected" | "expired" | "unreachable" | "invalid";
  message?: string;
  matches: RecordingMatch[];
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Find the class's recording on UpLevel: the same search a PM does by hand (class name, date,
 *  instructor, live class or assignment review), done by the worker, which holds the UpLevel
 *  login. The answer is always a status the form can say in a sentence. */
export async function findRecording(input: {
  topic: string;
  instructor: string;
  classDate: string;
  classType: "live_class" | "ars";
}): Promise<FindRecordingResult> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) {
    return { status: "invalid", message: "Please sign in with a staff account.", matches: [] };
  }
  const topic = String(input?.topic ?? "").trim().slice(0, 300);
  const instructor = String(input?.instructor ?? "").trim().slice(0, 200);
  const classDate = String(input?.classDate ?? "").trim();
  const classType = input?.classType === "ars" ? "ars" : "live_class";
  if (!topic) return { status: "invalid", message: "Fill in the class topic first.", matches: [] };
  if (classDate && !ISO_DATE.test(classDate)) return { status: "invalid", message: "The class date is not a date.", matches: [] };

  const reply = await postToWorker<FindRecordingResult>(
    "/uplevel/find",
    { topic, instructor, class_date: classDate || null, class_type: classType },
    55_000,
  );
  if (!reply.ok) {
    // Asleep (no answer) and broken (an error answer) are different problems; say which.
    const message = reply.status
      ? `The analysis service answered with an error (HTTP ${reply.status}), so the lookup could not run. Paste the link by hand; if it keeps happening, tell whoever maintains the tool.`
      : "The analysis service did not answer; it may be waking up, which takes up to a minute. Search again in a moment.";
    return { status: "unreachable", message, matches: [] };
  }
  const data = reply.data;
  const allowed = ["ok", "none", "not_connected", "expired", "unreachable"] as const;
  const status = (allowed as readonly string[]).includes(data?.status) ? data.status : "unreachable";
  return { status, message: data?.message, matches: Array.isArray(data?.matches) ? data.matches.slice(0, 6) : [] };
}

/** Is the Claude API credit still empty? Asked by the notice when someone opens an analysis page,
 *  so a recharged account stops being reported as empty within seconds. */
export async function recheckCredit(): Promise<"ok" | "empty" | "unknown"> {
  const user = await getCurrentUser();
  if (!user || (user.role !== "admin" && user.role !== "pm")) return "unknown";
  const reply = await postToWorker<{ credit?: string }>("/ai-credit/check", {}, 55_000);
  if (!reply.ok) return "unknown";
  const c = reply.data?.credit;
  return c === "ok" || c === "empty" ? c : "unknown";
}
