import { timingSafeEqual } from "node:crypto";
import { revalidatePath } from "next/cache";

/** POST /api/revalidate — the worker pings this after a sync (or a re-score) so every page picks
 *  up fresh rows on its next visit. Bearer-authenticated with the shared WORKER_API_KEY; without
 *  the key configured the endpoint refuses everything rather than being open.
 *
 *  Body (optional): { "paths": ["/c/applied-agentic-ai/queue", ...] } — extra literal paths on
 *  top of the whole-app purge (`revalidatePath('/', 'layout')`). */

function sameSecret(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export async function POST(request: Request) {
  const key = process.env.WORKER_API_KEY;
  if (!key) return Response.json({ revalidated: false, error: "WORKER_API_KEY is not configured on the web app." }, { status: 503 });

  const header = request.headers.get("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token || !sameSecret(token, key)) return Response.json({ revalidated: false, error: "Unauthorized." }, { status: 401 });

  let paths: string[] = [];
  try {
    const body = (await request.json()) as { paths?: unknown } | null;
    if (body && Array.isArray(body.paths)) paths = body.paths.filter((p): p is string => typeof p === "string" && p.startsWith("/") && p.length < 200).slice(0, 20);
  } catch {
    // no body, or not JSON — the whole-app purge below is the default
  }

  revalidatePath("/", "layout");
  for (const p of paths) revalidatePath(p);
  return Response.json({ revalidated: true, paths: ["/", ...paths], now: Date.now() });
}
