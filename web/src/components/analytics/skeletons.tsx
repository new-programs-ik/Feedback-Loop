import { Skeleton } from "@/components/ui/skeleton";

/** Skeletons that match the real geometry: KPI tiles are 84px, table rows 36px, chart wells
 *  the chart's own height — so nothing reflows when the data lands. */

export function KpiRowSkeleton({ n = 6 }: { n?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="bg-card shadow-soft rounded-xl border px-4 py-3">
          <Skeleton className="h-2.5 w-20" />
          <Skeleton className="mt-3 h-6 w-16" />
          <Skeleton className="mt-2.5 h-2.5 w-24" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 240, title = true }: { height?: number; title?: boolean }) {
  return (
    <div className="bg-card shadow-soft rounded-xl border p-4">
      {title && <Skeleton className="mb-3 h-3 w-40" />}
      <div className="surface-inset rounded-lg border" style={{ height: height + 12 }} />
    </div>
  );
}

export function TableSkeleton({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
      <div className="px-4 pt-3.5 pb-2.5">
        <Skeleton className="h-3 w-32" />
      </div>
      <div className="surface-inset flex h-9 items-center gap-6 border-y px-4">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-2 w-16" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex h-9 items-center gap-6 border-b px-4 last:border-0">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} className={j === 0 ? "h-3 w-36 max-w-[40vw]" : "h-3 w-12"} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** The standard analytics page: header, filter row, KPI row, a wide chart, then a table. */
export function PageSkeleton({ kpis = 6, chart = 240, rows = 8, header = true }: { kpis?: number; chart?: number; rows?: number; header?: boolean }) {
  return (
    <div className="space-y-4" role="status" aria-busy="true" aria-label="Loading">
      {header && (
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-64 max-w-[70vw]" />
          </div>
          <Skeleton className="h-8 w-24" />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-36" />
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-9 w-32" />
      </div>
      {kpis > 0 && <KpiRowSkeleton n={kpis} />}
      {chart > 0 && <ChartSkeleton height={chart} />}
      {rows > 0 && <TableSkeleton rows={rows} />}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
