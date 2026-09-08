import { PageSkeleton } from "@/components/analytics/skeletons";

export default function Loading() {
  return <PageSkeleton kpis={6} chart={260} rows={10} />;
}
