import { Skeleton } from "@/components/ui/skeleton";
import { ChartSkeleton, TableSkeleton } from "@/components/analytics/skeletons";

/** The overview's shape: header, filter row, seven KPI tiles, the "right now" strip, then the
 *  first pair of charts and the worst-classes table. */
export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-busy="true" aria-label="Loading">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-64 max-w-[70vw]" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-36" />
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-9 w-32" />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="bg-card shadow-soft rounded-xl border px-4 py-3">
            <Skeleton className="h-2.5 w-20" />
            <Skeleton className="mt-3 h-6 w-16" />
            <Skeleton className="mt-2.5 h-2.5 w-24" />
          </div>
        ))}
      </div>
      <div className="bg-card shadow-soft rounded-xl border p-4">
        <Skeleton className="h-3 w-40" />
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="surface-inset rounded-lg border p-3">
              <Skeleton className="h-2.5 w-20" />
              <Skeleton className="mt-2.5 h-3 w-full" />
              <Skeleton className="mt-1.5 h-3 w-4/5" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartSkeleton height={220} />
        <ChartSkeleton height={220} />
      </div>
      <TableSkeleton rows={8} />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
