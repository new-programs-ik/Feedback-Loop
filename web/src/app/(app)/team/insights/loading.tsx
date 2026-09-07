import { Skeleton } from "@/components/ui/skeleton";
import { ChartSkeleton, TableSkeleton } from "@/components/analytics/skeletons";

/** The study's geometry while it loads: the editorial header and its five tiles, the left rail
 *  (xl) or the pill row, then the five-number table, the risk bars and the vote chart — the
 *  first two screens, so nothing jumps when the data lands. */
export default function Loading() {
  return (
    <div
      className="mx-auto max-w-4xl xl:grid xl:max-w-6xl xl:grid-cols-[168px_minmax(0,56rem)] xl:justify-center xl:gap-x-10"
      role="status"
      aria-busy="true"
      aria-label="Loading the study"
    >
      <div className="xl:col-start-2">
        <Skeleton className="h-2.5 w-64" />
        <Skeleton className="mt-3 h-7 w-3/4 max-w-xl" />
        <Skeleton className="mt-3 h-3.5 w-full max-w-2xl" />
        <Skeleton className="mt-2 h-3.5 w-5/6 max-w-2xl" />
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-card shadow-soft rounded-xl border px-4 py-3">
              <Skeleton className="h-2.5 w-24" />
              <Skeleton className="mt-3 h-6 w-16" />
              <Skeleton className="mt-2.5 h-2.5 w-20" />
            </div>
          ))}
        </div>
      </div>

      <div className="hidden xl:col-start-1 xl:row-span-2 xl:row-start-1 xl:block">
        <div className="sticky top-24 space-y-2.5 pl-3 pt-1">
          <Skeleton className="h-2.5 w-16" />
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-3 w-28" />
          ))}
        </div>
      </div>

      <div className="min-w-0 xl:col-start-2">
        <div className="-mx-4 mt-6 flex gap-1 overflow-hidden border-b px-4 py-2 md:-mx-8 md:px-8 xl:hidden">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-24 shrink-0 rounded-full" />
          ))}
        </div>
        <div className="mt-9 border-t pt-5">
          <Skeleton className="h-4 w-72" />
          <Skeleton className="mt-3 h-3 w-full max-w-2xl" />
          <div className="mt-3">
            <TableSkeleton rows={5} cols={4} />
          </div>
          <Skeleton className="mt-3 h-3 w-4/5 max-w-2xl" />
        </div>
        <div className="mt-9 border-t pt-5">
          <Skeleton className="h-4 w-80" />
          <Skeleton className="mt-3 h-3 w-full max-w-2xl" />
          <div className="mt-3">
            <ChartSkeleton height={190} />
          </div>
        </div>
        <div className="mt-9 border-t pt-5">
          <Skeleton className="h-4 w-72" />
          <Skeleton className="mt-3 h-3 w-full max-w-2xl" />
          <div className="mt-3">
            <ChartSkeleton height={220} />
          </div>
        </div>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
