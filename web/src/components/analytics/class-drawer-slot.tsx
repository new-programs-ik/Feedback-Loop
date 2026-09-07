import { ClassDrawer } from "@/components/score/class-drawer";
import { ClassDetail, loadClassDetail } from "@/components/score/class-detail";
import { getActiveConfig } from "@/lib/scoring";
import { coursePriors, courseKey } from "@/lib/class-score";
import type { ScoredRating } from "@/lib/analytics";

/** The class drawer on an analytics page: whenever the URL carries `?class=<id>` the page
 *  awaits this and renders the result, so a cell of the curriculum map or a row of a class table
 *  opens the same drawer the classes page has — in place, as a shareable link. `rows` are the
 *  course's rows in hand (for the small-sample guard's priors). */
export async function classDrawerFor({ id, closeHref, slug, rows }: { id: string; closeHref: string; slug: string; rows: ScoredRating[] }) {
  const [detail, active] = await Promise.all([loadClassDetail(id), getActiveConfig()]);
  if (!detail) return <p className="text-muted-foreground mt-3 text-xs">That class was not found — it may have been removed from the sheet.</p>;
  const priors = coursePriors(rows);
  return (
    <ClassDrawer closeHref={closeHref} title={detail.row.topic || detail.row.session_kind}>
      <ClassDetail data={detail} cfg={active.config} version={active.version} priors={priors.get(courseKey(detail.row))} slug={slug} />
    </ClassDrawer>
  );
}

/** `base?…&class=<id>` — the URL that opens a class on the page at `base` (its query kept). */
export function classHrefPrefix(base: string, query: string): string {
  return `${base}${query ? `${query}&` : "?"}class=`;
}
