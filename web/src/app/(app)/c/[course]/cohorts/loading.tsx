import { Skeleton } from "@/components/ui/skeleton";
import { ChartSkeleton, TableSkeleton } from "@/components/analytics/skeletons";
import { CurriculumMapSkeleton } from "@/components/charts/curriculum-map";

/** The cohorts page's shape: header, filter row, the insights strip, the curriculum map, two
 *  journey charts side by side, the cohort table. */
export default function Loading() {
  return (
    <div className="space-y-4" role="status" aria-busy="true" aria-label="Loading cohorts">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-3 w-80 max-w-[70vw]" />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-36" />
        <Skeleton className="h-9 w-32" />
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
      <CurriculumMapSkeleton />
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartSkeleton height={260} />
        <ChartSkeleton height={260} />
      </div>
      <TableSkeleton rows={8} cols={7} />
      <span className="sr-only">Loading…</span>
    </div>
  );
}
