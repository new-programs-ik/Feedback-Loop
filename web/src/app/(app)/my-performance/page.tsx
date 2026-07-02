import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="My Performance"
      description="Your personal view — attendance, assignments, quizzes, and participation across your cohort."
      cards={["My attendance", "My assignments", "My quizzes"]}
    />
  );
}
