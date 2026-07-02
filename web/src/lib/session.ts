import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export type Role = "admin" | "pm" | "learner";

export type SessionUser = {
  id: string;
  name: string;
  email: string;
  role: Role;
};

/** The signed-in user + role (read from user_roles via RLS), or null if signed out. */
export async function getCurrentUser(): Promise<SessionUser | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const [{ data: roleRow }, { data: profile }] = await Promise.all([
    supabase.from("user_roles").select("role").eq("user_id", user.id).maybeSingle(),
    supabase.from("profiles").select("full_name, email").eq("user_id", user.id).maybeSingle(),
  ]);

  const role = ((roleRow?.role as Role) ?? "learner");
  return {
    id: user.id,
    name: profile?.full_name ?? user.email ?? "User",
    email: user.email ?? profile?.email ?? "",
    role,
  };
}

/** Use in protected pages/layouts: returns the user or redirects to /login. */
export async function requireUser(): Promise<SessionUser> {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return user;
}
