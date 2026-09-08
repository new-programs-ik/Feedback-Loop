"use client";

import Link from "next/link";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import { AvgScorePill, BandStripOf, CompareBullet } from "@/components/analytics/score";
import { DataTable, Delta } from "@/components/analytics/ui";
import { ApprovalNum, AttendedNum, RatingNum, ReachNum, prettyDate } from "@/components/analytics/table-cells";
import type { InstructorRowVM } from "@/components/analytics/table-rows";

type Key = "name" | "n" | "score" | "mix" | "rating" | "attended" | "approval" | "reach" | "delta" | "last";

/** How each column compares: numbers open with the big ones first, names A → Z. */
const SPEC: SortSpec<InstructorRowVM, Key> = {
  name: { value: (r) => r.name, first: "asc" },
  n: { value: (r) => r.n, first: "desc" },
  score: { value: (r) => r.avgScore, first: "desc" },
  mix: { value: (r) => r.badShare, first: "desc" },
  rating: { value: (r) => r.avgRating, first: "desc" },
  attended: { value: (r) => r.avgAttended, first: "desc" },
  approval: { value: (r) => r.approval, first: "desc" },
  reach: { value: (r) => r.reach, first: "desc" },
  delta: { value: (r) => r.delta, first: "desc" },
  last: { value: (r) => r.lastClassDate, first: "desc" },
};

/** The client half of the leaderboard: sorts the slim rows locally (best score first until a
 *  heading is clicked) and draws them. Rows link to the portfolio. */
export function LeaderboardTable({
  rows,
  reference,
  showCourses = false,
  maxHeight,
}: {
  rows: InstructorRowVM[];
  /** The course (or team) average score — the bullet's tick. */
  reference: number | null;
  showCourses?: boolean;
  maxHeight?: string;
}) {
  const { sorted, state, toggle } = useSortable(rows, SPEC, { key: "score", dir: "desc" });
  const th = { state, onToggle: toggle };
  const referenceLabel = showCourses ? "team avg" : "course avg";
  return (
    <DataTable maxHeight={maxHeight}>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortButton sortKey="name" {...th}>Instructor</SortButton>
          {showCourses && <TableHead>Courses</TableHead>}
          <SortButton sortKey="n" {...th} align="right">Classes</SortButton>
          <SortButton sortKey="score" {...th}>Avg score</SortButton>
          <SortButton sortKey="mix" {...th} title="Sort by the share of Bad classes">Band mix</SortButton>
          <SortButton sortKey="rating" {...th} align="right">Avg rating</SortButton>
          <SortButton sortKey="attended" {...th} align="right">Avg attended</SortButton>
          <SortButton sortKey="approval" {...th} align="right">Approval</SortButton>
          <SortButton sortKey="reach" {...th} align="right">Rated / attended</SortButton>
          <SortButton sortKey="delta" {...th} align="right" title="Sort by the change since the previous period">Δ</SortButton>
          <TableHead>vs {showCourses ? "team" : "course"}</TableHead>
          <SortButton sortKey="last" {...th} align="right">Last class</SortButton>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((i) => (
          <TableRow key={i.key} className="relative">
            <TableCell className="max-w-56">
              <Link href={i.href} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={i.name}>
                {i.name}
              </Link>
              {i.aliases.length > 0 && <span className="text-muted-foreground block truncate text-[10.5px]">also {i.aliases.join(", ")}</span>}
            </TableCell>
            {showCourses && (
              <TableCell>
                <span className="flex flex-wrap gap-1">
                  {i.courses.slice(0, 3).map((c) => {
                    const chip = (
                      <span className="text-muted-foreground inline-flex max-w-32 truncate rounded border px-1.5 py-px text-[10.5px]" title={c.name}>
                        {c.name}
                      </span>
                    );
                    return c.href ? (
                      <Link key={c.name} href={c.href} className="relative z-[1]">
                        {chip}
                      </Link>
                    ) : (
                      <span key={c.name}>{chip}</span>
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
            <RatingNum value={i.avgRating} />
            <AttendedNum value={i.avgAttended} />
            <ApprovalNum value={i.approval} />
            <ReachNum value={i.reach} />
            <TableNum>
              <Delta value={i.delta} />
            </TableNum>
            <TableCell>
              <CompareBullet value={i.avgScore} reference={reference} referenceLabel={referenceLabel} />
            </TableCell>
            <TableNum className="text-muted-foreground">{prettyDate(i.lastClassDate)}</TableNum>
          </TableRow>
        ))}
      </TableBody>
    </DataTable>
  );
}
