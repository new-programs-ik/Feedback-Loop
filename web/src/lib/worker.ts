import "server-only";

/** One way to ask the worker something small and wait for the answer. The worker sleeps when idle
 *  (Render's free tier), so the first call after a quiet spell can take up to a minute; callers
 *  pass a timeout that allows for that and treat `ok: false` as "could not ask", never as "no". */
export type WorkerReply<T> = { ok: true; data: T } | { ok: false; status: number | null; error: string };

export async function postToWorker<T>(path: string, body: unknown, timeoutMs: number): Promise<WorkerReply<T>> {
  const workerUrl = process.env.ANALYSIS_WORKER_URL || "http://localhost:8000";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.WORKER_API_KEY) headers.Authorization = `Bearer ${process.env.WORKER_API_KEY}`;
  try {
    const res = await fetch(`${workerUrl}${path}`, {
      method: "POST", headers, body: JSON.stringify(body ?? {}), signal: AbortSignal.timeout(timeoutMs), cache: "no-store",
    });
    if (!res.ok) return { ok: false, status: res.status, error: `the analysis service answered ${res.status}` };
    return { ok: true, data: (await res.json()) as T };
  } catch {
    return { ok: false, status: null, error: "the analysis service could not be reached (it may be waking up)" };
  }
}
