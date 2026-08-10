import { Skeleton } from "@/components/ui/skeleton";

/** Instant feedback for EVERY page in the app: the moment a tab is clicked this renders,
 *  while the real page's data loads on the server. No more dead clicks. */
export default function AppLoading() {
  return (
    <div className="animate-in-up space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}
