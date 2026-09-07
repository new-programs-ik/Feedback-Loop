/** Next re-mounts a template on every navigation — the new page fades in over 120 ms (the
 *  animation is CSS, `.animate-in-up` in globals.css, and collapses under reduced motion).
 *  Nothing moves: a dashboard that slides reads as lag. */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="animate-in-up">{children}</div>;
}
