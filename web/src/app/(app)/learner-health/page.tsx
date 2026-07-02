import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Learner Health"
      description="A 0–100 health score per learner from attendance, assignment completion, quiz performance, support tickets, and participation — banded Healthy / At-risk / Critical, with configurable weights."
      cards={["Score distribution", "At-risk list", "Signal breakdown"]}
    />
  );
}
