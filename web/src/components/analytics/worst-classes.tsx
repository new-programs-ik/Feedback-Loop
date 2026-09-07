import * as React from "react";
import Link from "next/link";
import { TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { ClassScorePill } from "@/components/analytics/score";
import { DataTable, Empty, KindChip } from "@/components/analytics/ui";
import { classReason, drawerHref, instructorName, prettyDate, type ScoredRating } from "@/lib/analytics";

export type Outcome = { analysed: boolean; approved: boolean; sent: boolean; classId: string | null };

/** The worst classes of a period: score pill, the class (opens the drawer), instructor, date,
 *  the reason in plain words and — on reports — what happened to it. */
export function WorstClasses({
  rows,
  classesHref = drawerHref,
  limit = 8,
  showCourse = false,
  outcomes,
  emptyText = "No scored classes in this range.",
}: {
  rows: ScoredRating[];
  /** The drawer link per row — defaults to the row's own course classes page + `?class=`. */
  classesHref?: (r: ScoredRating) => string;
  limit?: number;
  showCourse?: boolean;
  outcomes?: Map<string, Outcome>;
  emptyText?: string;
}) {
  const worst = rows
    .filter((r) => r.score != null && r.band != null)
    .sort((a, b) => a.score! - b.score! || a.rating - b.rating)
    .slice(0, limit);
  if (worst.length === 0) return <Empty>{emptyText}</Empty>;
  return (
    <DataTable>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Score</TableHead>
          <TableHead>Class</TableHead>
          {showCourse && <TableHead>Course</TableHead>}
          <TableHead>Instructor</TableHead>
          <TableHead className="text-right">Date</TableHead>
          <TableHead>Why</TableHead>
          {outcomes && <TableHead>Outcome</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {worst.map((r) => {
          const o = outcomes?.get(r.id);
          return (
            <TableRow key={r.id} className="relative">
              <TableCell>
                <ClassScorePill row={r} />
              </TableCell>
              <TableCell className="max-w-64">
                <Link href={classesHref(r)} className="hover:text-primary block truncate font-medium after:absolute after:inset-0" title={r.topic}>
                  {r.topic || r.session_kind}
                </Link>
                <span className="text-muted-foreground flex items-center gap-1.5 text-[10.5px]">
                  <KindChip kind={r.session_kind} />
                  {r.num_ratings != null && r.attended != null ? `${r.num_ratings} of ${r.attended} rated` : null}
                </span>
              </TableCell>
              {showCourse && <TableCell className="text-muted-foreground max-w-40 truncate">{r.course_name ?? r.course_label}</TableCell>}
              <TableCell className="max-w-40 truncate">{instructorName(r)}</TableCell>
              <TableNum className="text-muted-foreground">{prettyDate(r.class_date)}</TableNum>
              <TableCell className="text-muted-foreground max-w-md min-w-56 text-[12px] leading-snug whitespace-normal">{classReason(r)}</TableCell>
              {outcomes && (
                <TableCell className="text-[12px] whitespace-nowrap">
                  {o?.sent ? (
                    <span className="text-success font-medium">sent</span>
                  ) : o?.approved ? (
                    <span className="text-success font-medium">approved</span>
                  ) : o?.analysed ? (
                    <span className="font-medium">analysed</span>
                  ) : r.review_status === "dismissed" ? (
                    <span className="text-muted-foreground">dismissed</span>
                  ) : r.review_status === "confirmed" || r.review_status === "analysis_started" ? (
                    <span className="text-muted-foreground">confirmed</span>
                  ) : (
                    <span className="text-muted-foreground">open</span>
                  )}
                  {o?.classId && (
                    <>
                      {" "}
                      <Link href={`/feedback/${o.classId}`} className="text-primary relative z-[1] hover:underline">
                        view
                      </Link>
                    </>
                  )}
                </TableCell>
              )}
            </TableRow>
          );
        })}
      </TableBody>
    </DataTable>
  );
}
