import { Skeleton } from "@/components/ui/skeleton";

/** Skeletons that match the real geometry of the pages they stand in for, so nothing reflows
 *  when the data lands. */

function HeaderSkeleton({ action = true }: { action?: boolean }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div className="space-y-2">
        <Skeleton className="h-6 w-44" />
        <Skeleton className="h-3.5 w-80 max-w-[70vw]" />
      </div>
      {action && <Skeleton className="h-9 w-28" />}
    </div>
  );
}

function FilterSkeleton({ n = 3 }: { n?: number }) {
  return (
    <div className="mb-5 flex flex-wrap gap-2 border-b py-2.5">
      <Skeleton className="h-9 w-40" />
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-44" />
      ))}
    </div>
  );
}

/** A table card: title row, 36px header band, `rows` 40px rows with a score pill first. */
function TableSkeleton({ rows = 8, title = true }: { rows?: number; title?: boolean }) {
  return (
    <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
      {title && (
        <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5">
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3 w-40" />
        </div>
      )}
      <div className="surface-inset flex h-9 items-center gap-6 border-y px-4">
        <Skeleton className="h-2.5 w-12" />
        <Skeleton className="h-2.5 w-36" />
        <Skeleton className="h-2.5 w-20" />
        <Skeleton className="hidden h-2.5 w-24 sm:block" />
        <Skeleton className="hidden h-2.5 w-16 md:block" />
        <Skeleton className="hidden h-2.5 w-14 md:block" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex h-10 items-center gap-6 border-b px-4 last:border-0">
          <Skeleton className="h-6 w-14 rounded-md" />
          <Skeleton className="h-3.5 w-44 max-w-[40vw]" />
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="hidden h-3.5 w-24 sm:block" />
          <Skeleton className="hidden h-3.5 w-14 md:block" />
          <Skeleton className="hidden h-3.5 w-12 md:block" />
        </div>
      ))}
    </div>
  );
}

/** The queue: header, filter row, the cost line, then three section cards. */
export function QueueSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading the queue">
      <HeaderSkeleton />
      <FilterSkeleton n={4} />
      <Skeleton className="mb-4 h-4 w-72" />
      <div className="space-y-4">
        <TableSkeleton rows={4} />
        <TableSkeleton rows={6} />
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

/** The classes table: header, filter row, one long table with pagination. */
export function ClassesSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading classes">
      <HeaderSkeleton action={false} />
      <FilterSkeleton n={4} />
      <TableSkeleton rows={14} title={false} />
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export { HeaderSkeleton, FilterSkeleton, TableSkeleton };
