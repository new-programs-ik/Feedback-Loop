import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="My Health Score"
      description="Your overall health score and what's driving it, so you know where to focus."
      cards={["My score", "What's helping", "What to improve"]}
    />
  );
}
