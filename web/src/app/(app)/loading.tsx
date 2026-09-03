import { Skeleton } from "@/components/ui/skeleton";

/** Instant feedback for EVERY page in the app: the moment a tab is clicked this renders, while
 *  the real page's data loads on the server. It mirrors the standard page anatomy — header with
 *  an action, filter row, four KPI tiles, a table — at the real elements' sizes, so the content
 *  lands in place instead of shoving the skeleton aside. */
export default function AppLoading() {
  return (
    <div className="animate-in-up space-y-5" role="status" aria-busy="true" aria-label="Loading page">
      {/* PageHeader: h1 (28px line) + description (18px line) + one action */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-6 w-44" />
          <Skeleton className="h-3.5 w-72 max-w-[70vw]" />
        </div>
        <Skeleton className="h-8 w-28" />
      </div>

      {/* FilterBar: two 36px selects */}
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-40" />
        <Skeleton className="h-9 w-52" />
      </div>

      {/* StatTile x4: label · number · delta row = 112px */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-card shadow-soft rounded-xl border p-4">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-7 w-20" />
            <Skeleton className="mt-3 h-4 w-28" />
          </div>
        ))}
      </div>

      {/* Table: title row, 36px header band, six 44px rows */}
      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-3 w-40" />
        </div>
        <div className="surface-inset flex h-9 items-center gap-6 border-y px-4">
          <Skeleton className="h-2.5 w-28" />
          <Skeleton className="h-2.5 w-14" />
          <Skeleton className="h-2.5 w-16" />
          <Skeleton className="hidden h-2.5 w-16 sm:block" />
          <Skeleton className="hidden h-2.5 w-20 md:block" />
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex h-11 items-center gap-6 border-b px-4 last:border-0">
            <Skeleton className="h-3.5 w-36 max-w-[40vw]" />
            <Skeleton className="h-3.5 w-10" />
            <Skeleton className="h-3.5 w-12" />
            <Skeleton className="hidden h-3.5 w-12 sm:block" />
            <Skeleton className="hidden h-1.5 w-14 rounded-full md:block" />
          </div>
        ))}
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
