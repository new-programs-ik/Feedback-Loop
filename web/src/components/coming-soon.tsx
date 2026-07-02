import { Construction } from "lucide-react";
import { Badge } from "@/components/ui/badge";

/** Polished placeholder for modules that are planned but not yet built. */
export function ComingSoon({
  title,
  description,
  cards = ["Overview", "Trends", "Details"],
}: {
  title: string;
  description: string;
  cards?: string[];
}) {
  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <Badge variant="secondary">Coming soon</Badge>
        </div>
        <p className="text-muted-foreground mt-1 max-w-2xl">{description}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((c) => (
          <div key={c} className="bg-card rounded-xl border p-5">
            <div className="text-muted-foreground text-sm font-medium">{c}</div>
            <div className="text-muted-foreground/50 mt-4 flex h-32 items-center justify-center rounded-lg border border-dashed">
              <Construction className="mr-2 size-4" /> planned
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
