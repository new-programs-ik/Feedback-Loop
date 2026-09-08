"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import {
  TEAM_SLUG,
  TEAM_WORKSPACE,
  slugFromPath,
  workspaceFor,
  type CourseSummary,
  type Workspace,
} from "@/lib/workspace-shared";

export { hrefIn, TEAM_SLUG, slugFromPath, pageFromPath } from "@/lib/workspace-shared";
export type { CourseSummary, Workspace, MemberRole } from "@/lib/workspace-shared";

export type WorkspaceContextValue = Workspace & {
  courses: CourseSummary[];
  /** The workspace the shell falls back to outside `/c/…` and `/team` (the last one used). */
  defaultSlug: string;
};

const Ctx = React.createContext<WorkspaceContextValue | null>(null);

/** Provides the current workspace to everything beneath it.
 *
 *  Two ways to use it: the app shell passes `courses` + `defaultSlug` and the provider DERIVES the
 *  workspace from the pathname (`/c/<slug>` → that course, `/team` → the team level, anything else
 *  → the default), which is what the sidebar and breadcrumbs need since they sit outside the route
 *  layouts; the `c/[course]` and `team` layouts pass an explicit `workspace` (resolved on the
 *  server with the member's role) for the pages beneath them. */
export function WorkspaceProvider({
  courses,
  defaultSlug,
  workspace,
  children,
}: {
  courses: CourseSummary[];
  defaultSlug: string;
  workspace?: Workspace | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const value = React.useMemo<WorkspaceContextValue>(() => {
    if (workspace) return { ...workspace, courses, defaultSlug };
    const slug = slugFromPath(pathname) ?? defaultSlug;
    const ws = slug === TEAM_SLUG ? TEAM_WORKSPACE : workspaceFor(courses.find((c) => c.slug === slug)) ;
    return { ...ws, courses, defaultSlug };
  }, [workspace, courses, defaultSlug, pathname]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const v = React.useContext(Ctx);
  if (v) return v;
  return { ...TEAM_WORKSPACE, courses: [], defaultSlug: TEAM_SLUG };
}
