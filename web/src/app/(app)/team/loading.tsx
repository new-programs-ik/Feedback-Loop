import { Skeleton } from "@/components/ui/skeleton";
import { ChartSkeleton, TableSkeleton } from "@/components/analytics/skeletons";

export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-busy="true" aria-label="Loading">
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-3 w-72 max-w-[70vw]" />
      </div>
      <Skeleton className="h-3 w-96 max-w-full" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="bg-card shadow-soft rounded-xl border p-3.5">
            <div className="flex items-center gap-2.5">
              <Skeleton className="size-7 rounded-md" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3 w-32" />
                <Skeleton className="h-2.5 w-24" />
              </div>
              <Skeleton className="h-7 w-16" />
            </div>
            <Skeleton className="mt-3 h-2 w-full" />
            <Skeleton className="mt-2.5 h-2.5 w-40" />
          </div>
        ))}
      </div>
      <ChartSkeleton height={160} />
      <TableSkeleton rows={6} />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
