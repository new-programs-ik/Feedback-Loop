"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { recheckCredit } from "@/app/(app)/feedback/recording-actions";

/** Asks once, when the notice appears, whether the credit is still empty. If it has been
 *  recharged, the page refreshes and the notice is gone. */
export function CreditRecheck() {
  const router = useRouter();
  const [state, setState] = React.useState<"checking" | "empty" | "unknown">("checking");
  React.useEffect(() => {
    let live = true;
    void recheckCredit().then((r) => {
      if (!live) return;
      if (r === "ok") router.refresh();
      else setState(r);
    });
    return () => { live = false; };
  }, [router]);
  if (state === "checking") {
    return (
      <div className="text-muted-foreground mt-1.5 flex items-center gap-1.5 text-xs">
        <Loader2 className="size-3 animate-spin" aria-hidden /> Checking whether it has been recharged…
      </div>
    );
  }
  return (
    <div className="text-muted-foreground mt-1.5 text-xs">
      {state === "empty"
        ? `Checked just now (${new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}): still empty.`
        : "Could not check just now; it is re-checked every few minutes."}
    </div>
  );
}
