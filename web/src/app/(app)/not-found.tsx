import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="bg-card shadow-soft mx-auto mt-16 max-w-md rounded-xl border px-6 py-8 text-center">
      <p className="text-sm font-medium">That page or course does not exist.</p>
      <p className="text-muted-foreground mt-1 text-sm">The link may be old, or the course may have been renamed.</p>
      <Button asChild className="mt-4">
        <Link href="/">Go to your workspace</Link>
      </Button>
    </div>
  );
}
