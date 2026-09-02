"use client";

import { Printer } from "lucide-react";
import { Button } from "@/components/ui/button";

export function PrintButton() {
  return (
    <Button variant="outline" onClick={() => window.print()} data-print-hide>
      <Printer className="size-4" aria-hidden />
      Print / Save PDF
    </Button>
  );
}
