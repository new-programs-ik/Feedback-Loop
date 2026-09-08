import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Next.js 16: this file was formerly `middleware.ts`. It refreshes the Supabase
// session cookie on every request and gates access — signed-out users are sent to /login.
// (Authorization itself is enforced by Postgres RLS; this is the optimistic redirect.)
// It also remembers the workspace being visited (`fl_ws`), so `/` lands in the last one used.

// Route handlers under /api authenticate themselves (the worker's POST /api/revalidate carries
// a bearer key, not a session), so they must not be bounced to /login.
const PUBLIC_PREFIXES = ["/login", "/auth", "/share", "/api"];
const WS_COOKIE = "fl_ws";
const SLUG = /^[a-z0-9][a-z0-9-]{0,80}$/i;

function workspaceOf(path: string): string | null {
  if (path === "/team" || path.startsWith("/team/")) return "team";
  const m = path.match(/^\/c\/([^/]+)/);
  if (!m) return null;
  const slug = decodeURIComponent(m[1]);
  return SLUG.test(slug) ? slug : null;
}

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );

  const { data: { user } } = await supabase.auth.getUser();
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PREFIXES.some((p) => path === p || path.startsWith(p + "/"));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }
  if (user && path === "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  const ws = user ? workspaceOf(path) : null;
  if (ws && request.cookies.get(WS_COOKIE)?.value !== ws) {
    response.cookies.set(WS_COOKIE, ws, { path: "/", sameSite: "lax", httpOnly: true, maxAge: 60 * 60 * 24 * 365 });
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
