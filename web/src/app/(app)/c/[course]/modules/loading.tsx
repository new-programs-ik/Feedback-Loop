import { Skeleton } from "@/components/ui/skeleton";
import { TableSkeleton } from "@/components/analytics/skeletons";

/** The modules page's shape: header, filter row, the insights strip, the module table, the
 *  module × instructor grid. */
export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-busy="true" aria-label="Loading modules">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-3 w-80 max-w-[70vw]" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-36" />
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-9 w-32" />
      </div>
      <div className="bg-card shadow-soft rounded-xl border p-4">
        <Skeleton className="h-3 w-32" />
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="surface-inset rounded-lg border p-3">
              <Skeleton className="h-2.5 w-20" />
              <Skeleton className="mt-2.5 h-3 w-full" />
              <Skeleton className="mt-1.5 h-3 w-4/5" />
              <Skeleton className="mt-2 h-2.5 w-24" />
            </div>
          ))}
        </div>
      </div>
      <TableSkeleton rows={12} cols={8} />
      <TableSkeleton rows={8} cols={6} />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
