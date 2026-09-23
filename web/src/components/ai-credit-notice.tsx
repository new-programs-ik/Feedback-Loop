import { AlertTriangle } from "lucide-react";
import { getIntegrationStatus } from "@/lib/integrations";
import { CreditRecheck } from "@/components/credit-recheck";

/** What a class says when its run was refused for want of Claude API credit (older rows carry the
 *  provider's raw error; the worker writes these words now). */
export const NO_CREDIT_MSG =
  "The Claude API credit is empty, so this analysis could not run. This is not a fault in the system. Recharge the credit at console.anthropic.com › Plans & Billing, then press Retry.";
export const CREDIT_BACK_MSG =
  "This run was refused because the Claude API credit was empty at the time. The credit is available again, so press Retry.";
export const isCreditFailure = (reason: string) => /credit balance is too low|Claude API (fund|credit) is empty/i.test(reason);

/** Shown only where an analysis is started or read, and only while the credit is actually empty
 *  (migration 0032: the worker marks it 'empty' on a refusal and 'ok' on any success or re-check).
 *  When it shows, it asks the worker to re-check right away, so a recharged account stops being
 *  reported as empty within seconds instead of staying up until someone pays for an analysis. */
export async function AiCreditNotice({ className }: { className?: string }) {
  const status = await getIntegrationStatus("claude_credit");
  if (status?.state !== "empty") return null;
  const since = status.last_error_at
    ? new Date(status.last_error_at).toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      })
    : null;
  return (
    <div role="status" className={"border-warning/40 bg-warning/10 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm " + (className ?? "")}>
      <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">
        <div className="font-semibold">The Claude API credit is empty, so analyses cannot run right now.</div>
        <div className="text-muted-foreground mt-0.5">
          This is not a fault in the system. Recharge it at console.anthropic.com › Plans &amp; Billing
          {since && <> (the last refusal was at {since}, India time)</>}. This message disappears by itself once the credit is back.
        </div>
        <CreditRecheck />
      </div>
    </div>
  );
}
