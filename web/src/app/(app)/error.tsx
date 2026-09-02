"use client";

import { useEffect } from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

/** Route-group error boundary — the app previously had none, so any render error
 *  white-screened the whole shell. */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="bg-card shadow-soft mx-auto mt-10 max-w-lg rounded-xl border">
      <EmptyState
        icon={TriangleAlert}
        title="Something went wrong"
        description="The page hit an unexpected error. Your data is safe — try again, and tell Bishal if it keeps happening."
        action={
          <Button onClick={reset} variant="outline">
            Try again
          </Button>
        }
      />
    </div>
  );
}
