"use server";

import { cookies } from "next/headers";
import { TEAM_SLUG, WS_COOKIE } from "@/lib/workspace-shared";

const SLUG = /^[a-z0-9][a-z0-9-]{0,80}$/i;

/** Remember the workspace the user picked (the switcher calls this before navigating; the proxy
 *  also refreshes the cookie on every `/c/<slug>` or `/team` visit). */
export async function setWorkspace(slug: string): Promise<void> {
  const value = slug === TEAM_SLUG || SLUG.test(slug) ? slug : TEAM_SLUG;
  const store = await cookies();
  store.set(WS_COOKIE, value, { path: "/", sameSite: "lax", httpOnly: true, maxAge: 60 * 60 * 24 * 365 });
}
