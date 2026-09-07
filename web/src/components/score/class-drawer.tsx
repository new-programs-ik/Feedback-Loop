"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Sheet } from "@/components/ui/sheet";

/** The right-side class drawer. It is open whenever the URL carries `?class=<id>` (the page
 *  renders it with the server-rendered detail as children), so a drawer is a shareable link;
 *  closing it strips the parameter. */
export function ClassDrawer({ closeHref, title, children }: { closeHref: string; title: string; children: React.ReactNode }) {
  const router = useRouter();
  const close = React.useCallback(() => router.replace(closeHref, { scroll: false }), [router, closeHref]);
  return (
    <Sheet open side="right" ariaLabel={title} title={title} onClose={close}>
      <div className="px-5 py-4">{children}</div>
    </Sheet>
  );
}
