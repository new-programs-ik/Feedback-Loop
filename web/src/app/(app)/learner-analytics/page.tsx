import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Learner Analytics"
      description="Individual learner performance across attendance, assignments, quizzes, participation, and support — with at-risk detection."
      cards={["Health score distribution", "At-risk learners", "Engagement timeline"]}
    />
  );
}
