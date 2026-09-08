import { Empty } from "@/components/analytics/ui";
import { LeaderboardTable } from "@/components/analytics/leaderboard-table";
import { instructorRow } from "@/components/analytics/table-rows";
import type { InstructorAgg } from "@/lib/analytics";

/** The instructor leaderboard (overview · instructors · reports): score first, band mix, the raw
 *  rating and room size, approval, reach, Δ vs the previous period, a bullet against the course
 *  average, last class. Any heading sorts; best score first until one is clicked. This server
 *  half trims each aggregate to the slim row the table needs — the aggregates carry every rating
 *  row and must not cross to the client — and `LeaderboardTable` sorts and draws. */
export function Leaderboard({
  items,
  reference,
  hrefFor,
  previous,
  showCourses = false,
  courseHref,
  limit,
  minClasses = 3,
  emptyText = "No instructor has enough scored classes in this range.",
  maxHeight,
}: {
  items: InstructorAgg[];
  /** The course (or team) average score — the bullet's tick. */
  reference: number | null;
  hrefFor: (key: string) => string;
  /** Previous-period average score per instructor key (for Δ). */
  previous?: Map<string, number | null>;
  showCourses?: boolean;
  courseHref?: (slug: string | null) => string | null;
  limit?: number;
  minClasses?: number;
  emptyText?: string;
  /** The table's height cap (default 70vh); "none" on reports, so print shows every row. */
  maxHeight?: string;
}) {
  const rows = items
    .filter((i) => i.n >= minClasses)
    .slice(0, limit)
    .map((i) => instructorRow(i, { href: hrefFor(i.key), previous: previous?.get(i.key), courseHref }));
  if (rows.length === 0) return <Empty>{emptyText}</Empty>;
  return <LeaderboardTable rows={rows} reference={reference} showCourses={showCourses} maxHeight={maxHeight} />;
}
