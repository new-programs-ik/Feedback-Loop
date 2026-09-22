import { AlertTriangle } from "lucide-react";
import { createClient } from "@/lib/supabase/server";

/** What a class says when the AI provider refused for want of credit (the worker writes the same
 *  words; this copy covers rows written before the worker learned them). */
export const NO_CREDIT_MSG =
  "The Claude API fund is empty, so the analysis could not run. This is not a fault in the system. Please recharge the Claude API credit first (console.anthropic.com › Plans & Billing), then press Retry.";

const NO_CREDIT_FILTER =
  "detail->>kind.eq.no_credit,detail->>message.ilike.*credit balance is too low*,detail->>technical.ilike.*credit balance is too low*";

/** A notice at the top of every page for staff while the last analysis failed for want of Claude
 *  API credit and none has completed since. Without it, a failed analysis reads as a fault in
 *  the system. It goes away on its own the moment an analysis completes. */
export async function ServiceNotice() {
  const supabase = await createClient();
  const { data: failed } = await supabase
    .from("audit_log")
    .select("created_at")
    .eq("action", "error")
    .or(NO_CREDIT_FILTER)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!failed?.created_at) return null;
  const { data: since } = await supabase
    .from("audit_log")
    .select("id")
    .eq("action", "analyzed")
    .gt("created_at", failed.created_at)
    .limit(1)
    .maybeSingle();
  if (since) return null;
  const when = new Date(failed.created_at).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
  return (
    <div
      role="status"
      className="border-warning/40 bg-warning/10 text-foreground mx-4 mt-4 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm md:mx-8"
    >
      <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <div className="font-semibold">The Claude API fund is empty. Analyses will not run until it is recharged.</div>
        <div className="text-muted-foreground mt-0.5">
          This is not a fault in the system. The last analysis was refused on {when} (India time). Recharge the
          credit at console.anthropic.com › Plans &amp; Billing, then press <b>Retry</b> on the failed class. This
          notice goes away on its own when an analysis completes.
        </div>
      </div>
    </div>
  );
}
