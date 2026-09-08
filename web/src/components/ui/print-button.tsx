"use client";

import * as React from "react";
import { Printer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

/** Print / Save PDF. The toast paints first (the print dialog freezes the page while open), so
 *  the button acknowledges the click before the browser takes over. */
export function PrintButton() {
  const [busy, setBusy] = React.useState(false);
  const onPrint = () => {
    if (busy) return;
    setBusy(true);
    toast("Opening print…", { description: "Choose “Save as PDF” in the dialog to keep a copy." });
    window.setTimeout(() => {
      try {
        window.print();
      } finally {
        setBusy(false);
      }
    }, 280);
  };
  return (
    <Button variant="outline" onClick={onPrint} isLoading={busy} data-print-hide>
      <Printer aria-hidden />
      Print / Save PDF
    </Button>
  );
}
