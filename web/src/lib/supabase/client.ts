import { createBrowserClient } from "@supabase/ssr";

/** Supabase client for Client Components (stores the session in cookies so the
 *  server can read it). */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
