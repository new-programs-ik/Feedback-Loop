"use client";

import * as React from "react";

/** Wraps a form control; any `change` inside submits the parent GET form, so filters apply
 *  without an explicit button while staying plain-URL, server-rendered navigation. */
export function AutoSubmit({ children }: { children: React.ReactNode }) {
  return (
    <span
      onChange={(e) => {
        const form = (e.target as HTMLElement).closest("form");
        form?.requestSubmit();
      }}
    >
      {children}
    </span>
  );
}
