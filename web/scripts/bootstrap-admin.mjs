/**
 * bootstrap-admin.mjs — create (or update) a user with a confirmed password and a role.
 * Uses the service-role (secret) key, so it bypasses RLS. Run once to make the first admin.
 *
 *   node scripts/bootstrap-admin.mjs <email> <password> [admin|pm|learner]
 */
import { createClient } from "@supabase/supabase-js";
import { readFileSync } from "node:fs";

function loadEnv() {
  const txt = readFileSync(new URL("../.env.local", import.meta.url), "utf8");
  const env = {};
  for (const line of txt.split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    env[t.slice(0, i).trim()] = t.slice(i + 1).trim();
  }
  return env;
}

const env = loadEnv();
const [, , email, password, role = "admin"] = process.argv;
if (!email || !password) {
  console.error("usage: node scripts/bootstrap-admin.mjs <email> <password> [admin|pm|learner]");
  process.exit(1);
}

const admin = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

let userId;
const { data: created, error } = await admin.auth.admin.createUser({
  email,
  password,
  email_confirm: true,
});
if (error) {
  if (String(error.message).toLowerCase().includes("already")) {
    // user exists → find + reset password
    const { data: list } = await admin.auth.admin.listUsers();
    userId = list.users.find((u) => u.email === email)?.id;
    if (!userId) {
      console.error("user exists but could not be found in listUsers");
      process.exit(1);
    }
    await admin.auth.admin.updateUserById(userId, { password, email_confirm: true });
    console.log("updated existing user", email);
  } else {
    console.error("createUser failed:", error.message);
    process.exit(1);
  }
} else {
  userId = created.user.id;
  console.log("created user", email);
}

// The signup trigger seeds profile + a 'learner' role; upsert the requested role + profile.
const { error: pErr } = await admin
  .from("profiles")
  .upsert({ user_id: userId, email, full_name: email.split("@")[0] }, { onConflict: "user_id" });
const { error: rErr } = await admin
  .from("user_roles")
  .upsert({ user_id: userId, role }, { onConflict: "user_id" });
if (pErr || rErr) {
  console.error("profile/role upsert error:", (pErr || rErr).message);
  process.exit(1);
}
console.log(`OK — ${email} is now '${role}' (id ${userId})`);
