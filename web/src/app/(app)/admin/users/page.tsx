import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Users & Roles"
      description="Admin: invite users, assign roles (Admin / PM / Learner), and map PMs to the courses they own."
      cards={["Users", "Role assignments", "PM ↔ course mapping"]}
    />
  );
}
