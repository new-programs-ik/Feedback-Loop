import * as React from "react";
import Link from "next/link";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { AvgScorePill, BandStripOf, CompareBullet } from "@/components/analytics/score";
import { DataTable, Delta, Empty } from "@/components/analytics/ui";
import { fmtPct, prettyDate, type InstructorAgg } from "@/lib/analytics";

/** The instructor leaderboard (overview + instructors page): score first, band mix, approval,
 *  reach, Δ vs the previous period, a bullet against the course average, last class. Rows link
 *  to the portfolio. */
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
}) {
  const rows = items.filter((i) => i.n >= minClasses).slice(0, limit);
  if (rows.length === 0) return <Empty>{emptyText}</Empty>;
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Instructor</TableHead>
          {showCourses && <TableHead>Courses</TableHead>}
          <TableHead className="text-right">Classes</TableHead>
          <TableHead>Avg score</TableHead>
          <TableHead>Band mix</TableHead>
          <TableHead className="text-right">Approval</TableHead>
          <TableHead className="text-right">Reach</TableHead>
          <TableHead className="text-right">Δ</TableHead>
          <TableHead>vs {showCourses ? "team" : "course"}</TableHead>
          <TableHead className="text-right">Last class</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((i) => {
          const prev = previous?.get(i.key) ?? null;
          return (
            <TableRow key={i.key} className="relative">
              <TableCell className="max-w-56">
                <Link href={hrefFor(i.key)} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={i.name}>
                  {i.name}
                </Link>
                {i.aliases.length > 0 && <span className="text-muted-foreground block truncate text-[10.5px]">also {i.aliases.join(", ")}</span>}
              </TableCell>
              {showCourses && (
                <TableCell>
                  <span className="flex flex-wrap gap-1">
                    {i.courses.slice(0, 3).map((c) => {
                      const href = courseHref?.(c.slug);
                      const chip = (
                        <span key={c.name} className="text-muted-foreground inline-flex max-w-32 truncate rounded border px-1.5 py-px text-[10.5px]" title={c.name}>
                          {c.name}
                        </span>
                      );
                      return href ? (
                        <Link key={c.name} href={href} className="relative z-[1]">
                          {chip}
                        </Link>
                      ) : (
                        chip
                      );
                    })}
                    {i.courses.length > 3 && <span className="text-muted-foreground text-[10.5px]">+{i.courses.length - 3}</span>}
                  </span>
                </TableCell>
              )}
              <TableNum className="text-muted-foreground">{i.n}</TableNum>
              <TableCell>
                <AvgScorePill score={i.avgScore} />
              </TableCell>
              <TableCell>
                <BandStripOf counts={i.counts} className="w-20" />
              </TableCell>
              <TableNum className={i.approval != null && i.approval < 80 ? "text-destructive font-semibold" : ""}>{fmtPct(i.approval)}</TableNum>
              <TableNum className="text-muted-foreground">{fmtPct(i.reach)}</TableNum>
              <TableNum>
                <Delta value={prev == null || i.avgScore == null ? null : i.avgScore - prev} />
              </TableNum>
              <TableCell>
                <CompareBullet value={i.avgScore} reference={reference} referenceLabel={showCourses ? "team avg" : "course avg"} />
              </TableCell>
              <TableNum className="text-muted-foreground">{prettyDate(i.lastClassDate)}</TableNum>
            </TableRow>
          );
        })}
      </TableBody>
    </DataTable>
  );
}
