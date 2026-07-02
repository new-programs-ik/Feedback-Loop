import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Cohort Analytics"
      description="A single cohort's story — session ratings week by week, learner health mix, and where the cohort needs attention."
      cards={["Session ratings", "Learner health mix", "Attention areas"]}
    />
  );
}
