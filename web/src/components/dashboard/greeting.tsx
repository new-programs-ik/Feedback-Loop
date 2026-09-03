"use client";

import * as React from "react";

/** "Good morning, Bishal · Wednesday, 3 September" — the time of day and the date are the
 *  VIEWER's, not the server's (a Vercel box in Virginia would wish an Indian PM good evening
 *  at breakfast). useSyncExternalStore renders a neutral line on the server and swaps to the
 *  local greeting right after hydration — no mismatch warning, no layout shift (height reserved). */
function readClock() {
  const d = new Date();
  const h = d.getHours();
  const part = h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  const date = d.toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long" });
  return `${part}|${date}`;
}
const subscribe = () => () => {};
const serverClock = () => "Welcome back|";

export function Greeting({
  name,
  status,
  children,
}: {
  name: string;
  /** One computed sentence: "3 urgent classes need a decision · last sync 12 min ago". */
  status?: string;
  /** Trailing inline nodes (the AI-engine pill). */
  children?: React.ReactNode;
}) {
  const [part, date] = React.useSyncExternalStore(subscribe, readClock, serverClock).split("|");
  const pieces: React.ReactNode[] = [];
  if (date) pieces.push(<span key="date" className="text-foreground/80 font-medium">{date}</span>);
  if (status) pieces.push(<span key="status">{status}</span>);
  if (children) pieces.push(<React.Fragment key="extra">{children}</React.Fragment>);

  return (
    <div className="min-w-0">
      <h1 className="text-2xl font-semibold tracking-tight">
        {part}, {name}
      </h1>
      <p className="text-muted-foreground mt-1 flex min-h-5 flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {pieces.map((node, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span aria-hidden className="text-muted-foreground/40">·</span>}
            {node}
          </React.Fragment>
        ))}
      </p>
    </div>
  );
}
