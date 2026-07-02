import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Course Analytics"
      description="Course-level health across cohorts — average ratings, low-rated class rate, and outcomes for Flagship ML, Advanced ML, PwC Accelerator, and FDE."
      cards={["Ratings by course", "Low-rated class rate", "Cohort comparison"]}
    />
  );
}
