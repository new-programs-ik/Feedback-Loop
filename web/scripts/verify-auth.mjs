/**
 * verify-auth.mjs — prove the auth + role + RLS path end-to-end without a browser:
 * sign in with the publishable key, read own role (RLS), read reference + gated tables.
 *
 *   node scripts/verify-auth.mjs <email> <password>
 */
import { createClient } from "@supabase/supabase-js";
import { readFileSync } from "node:fs";

const txt = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
const env = {};
for (const line of txt.split(/\r?\n/)) {
  const t = line.trim();
  if (t && !t.startsWith("#") && t.includes("=")) {
    const i = t.indexOf("=");
    env[t.slice(0, i).trim()] = t.slice(i + 1).trim();
  }
}

const [, , email, password] = process.argv;
const supa = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_ANON_KEY);

const { data: signin, error } = await supa.auth.signInWithPassword({ email, password });
if (error) {
  console.error("sign-in FAILED:", error.message);
  process.exit(1);
}
console.log("signed in as:", signin.user.email, "(id", signin.user.id + ")");

const { data: roleRow } = await supa.from("user_roles").select("role").eq("user_id", signin.user.id).maybeSingle();
console.log("role (via RLS read):", roleRow?.role);

const { data: courses } = await supa.from("courses").select("name").order("name");
console.log("courses visible:", (courses ?? []).map((c) => c.name).join(", "));

const { data: classes, error: cErr } = await supa.from("classes").select("id");
console.log("classes visible:", classes?.length ?? 0, cErr ? `(err: ${cErr.message})` : "");

await supa.auth.signOut();
console.log("signed out. ✅ auth + RLS OK");
