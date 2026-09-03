import { CircleAlert, CircleDashed, TriangleAlert, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { APPROVAL_BAR, BAND_LABEL, type FlagReason, type HealthBand } from "@/lib/decision";
import { cn } from "@/lib/utils";

export const BAND_ICON: Record<HealthBand, LucideIcon> = {
  urgent: TriangleAlert,
  look: CircleAlert,
  borderline: CircleDashed,
};

/** BandDot tone for an approval percentage: bad under the bar, warn under 90, good above. */
export const approvalTone = (v: number | null | undefined): "good" | "warn" | "bad" =>
  v == null ? "good" : v < APPROVAL_BAR ? "bad" : v < 90 ? "warn" : "good";

/** The Health-Score band as a chip — icon + label, never colour alone — with the score beside it. */
export function PriorityChip({
  band,
  score,
  className,
}: {
  band: HealthBand | null | undefined;
  score?: number | null;
  className?: string;
}) {
  if (!band) return <span className="text-muted-foreground">—</span>;
  const Icon = BAND_ICON[band];
  const variant = band === "urgent" ? "destructive" : band === "look" ? "warning" : "secondary";
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <Badge variant={variant} className="gap-1">
        <Icon className="size-3" aria-hidden /> {BAND_LABEL[band]}
      </Badge>
      {score != null && (
        <span className="text-muted-foreground text-xs" data-numeric title="Class Health Score, 0–100">
          {Math.round(score)}
        </span>
      )}
    </span>
  );
}

/** Why a class was flagged: "rating" / "approval" / "escalated" as quiet outline chips. */
export function ReasonChips({ reasons, className }: { reasons: FlagReason[]; className?: string }) {
  if (reasons.length === 0) return null;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {reasons.map((r) => (
        <span
          key={r}
          className="text-muted-foreground inline-flex items-center rounded-full border px-1.5 py-px text-[10px] font-medium"
        >
          {r}
        </span>
      ))}
    </span>
  );
}
