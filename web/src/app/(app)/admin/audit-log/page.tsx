import { ComingSoon } from "@/components/coming-soon";

export default function Page() {
  return (
    <ComingSoon
      title="Audit Log"
      description="Admin: an append-only trail of every meaningful action — analyzed, edited, approved — with actor, time, and detail."
      cards={["Recent actions", "By actor", "By class"]}
    />
  );
}
