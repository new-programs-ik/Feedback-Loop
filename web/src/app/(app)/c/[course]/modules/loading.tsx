import { PageSkeleton } from "@/components/analytics/skeletons";

export default function Loading() {
  return <PageSkeleton kpis={0} chart={0} rows={12} />;
}
