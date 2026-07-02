import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Google (and other OAuth) redirect here with a ?code. We exchange it for a session,
// then enforce the @interviewkickstart.com domain before letting the user in.
const ALLOWED_DOMAIN = "interviewkickstart.com";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/dashboard";

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=oauth`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(`${origin}/login?error=oauth`);
  }

  const { data: { user } } = await supabase.auth.getUser();
  const email = user?.email ?? "";
  if (!email.toLowerCase().endsWith(`@${ALLOWED_DOMAIN}`)) {
    await supabase.auth.signOut();
    return NextResponse.redirect(`${origin}/login?error=domain`);
  }

  return NextResponse.redirect(`${origin}${next}`);
}
