import "server-only";
import { createClient } from "@supabase/supabase-js";

/** Service-role client — bypasses RLS. SERVER ONLY (never import into client code).
 *  Used for admin operations (user provisioning, role assignment). */
export function createAdminClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );
}
