import "server-only";
import { createClient } from "@/lib/supabase/server";

/** How the outside services are doing (migration 0032): the UpLevel connection and the Claude API
 *  credit. Staff can read this row; the UpLevel session itself lives in a table nobody signed in
 *  can read. The worker keeps both rows current. */
export type IntegrationName = "uplevel" | "claude_credit";
export type IntegrationState = "ok" | "expired" | "empty" | "error" | "not_set" | "unknown";
export type IntegrationStatus = {
  name: IntegrationName;
  state: IntegrationState;
  detail: string | null;
  last_ok_at: string | null;
  last_error_at: string | null;
  checked_at: string | null;
  set_at: string | null;
  set_by_label: string | null;
};

/** The row, or null when it cannot be read (then callers stay quiet rather than guess). */
export async function getIntegrationStatus(name: IntegrationName): Promise<IntegrationStatus | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("integration_status")
    .select("name, state, detail, last_ok_at, last_error_at, checked_at, set_at, set_by_label")
    .eq("name", name)
    .maybeSingle();
  if (error || !data) return null;
  return data as IntegrationStatus;
}
