import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Instructor Analytics"
      description="How each instructor is trending across their classes — ratings over time, recurring feedback themes, and re-class history. Viewed by PMs; instructors do not log in."
      cards={["Ratings over time", "Recurring feedback themes", "Re-class history"]}
    />
  );
}
