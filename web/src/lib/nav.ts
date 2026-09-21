import {
  BookOpen, GraduationCap, LayoutDashboard, ListChecks, MessageSquareText,
  RefreshCw, Rows3, ScrollText, Settings, SlidersHorizontal, Table2, UserCog, Users, FileText, type LucideIcon,
} from "lucide-react";
import type { Role } from "./session";
import { hrefIn, TEAM_SLUG } from "./workspace-shared";

export type NavItem = {
  key: string;
  label: string;
  /** Workspace-relative ("/queue") or absolute ("/admin/scoring"). */
  path: string;
  icon: LucideIcon;
  roles: Role[];
  /** Active only on the exact path (the team overview lives at `/team`, the parent of the rest). */
  exact?: boolean;
};
export type ResolvedNavItem = NavItem & { href: string };
export type NavSection = { title: string | null; items: ResolvedNavItem[] };

const STAFF: Role[] = ["admin", "pm"];
const EVERYONE: Role[] = ["admin", "pm", "learner"];

/** Inside a course workspace (`/c/<slug>/…`). */
export const WORKSPACE_NAV: NavItem[] = [
  { key: "overview", label: "Overview", path: "/overview", icon: LayoutDashboard, roles: EVERYONE },
  { key: "classes", label: "Classes", path: "/classes", icon: Table2, roles: STAFF },
  { key: "queue", label: "Needs analysis", path: "/queue", icon: ListChecks, roles: STAFF },
  { key: "instructors", label: "Instructors", path: "/instructors", icon: GraduationCap, roles: STAFF },
  { key: "cohorts", label: "Cohorts", path: "/cohorts", icon: Users, roles: STAFF },
  { key: "modules", label: "Modules", path: "/modules", icon: BookOpen, roles: STAFF },
  { key: "feedback", label: "Feedback", path: "/feedback", icon: MessageSquareText, roles: STAFF },
  { key: "reports", label: "Reports", path: "/reports", icon: FileText, roles: STAFF },
  { key: "settings", label: "Settings", path: "/settings", icon: Settings, roles: STAFF },
];

/** The leadership level (`/team/…`). */
export const TEAM_NAV: NavItem[] = [
  { key: "overview", label: "Overview", path: "/overview", icon: LayoutDashboard, roles: EVERYONE, exact: true },
  { key: "queue", label: "Queue", path: "/queue", icon: ListChecks, roles: STAFF },
  { key: "instructors", label: "Instructors", path: "/instructors", icon: GraduationCap, roles: STAFF },
  { key: "reports", label: "Reports", path: "/reports", icon: FileText, roles: STAFF },
];

export const ADMIN_NAV: NavItem[] = [
  { key: "scoring", label: "Scoring", path: "/admin/scoring", icon: SlidersHorizontal, roles: ["admin"] },
  { key: "identity", label: "Identity", path: "/admin/identity", icon: UserCog, roles: ["admin"] },
  { key: "people", label: "People", path: "/admin/people", icon: Users, roles: ["admin"] },
  { key: "sync", label: "Sync", path: "/admin/sync", icon: RefreshCw, roles: ["admin"] },
  { key: "audit", label: "Audit", path: "/admin/audit", icon: ScrollText, roles: ["admin"] },
];

/** The URL of a nav item inside a workspace (absolute items pass through). */
export function hrefFor(item: NavItem, slug: string | null | undefined): string {
  return hrefIn(slug ?? TEAM_SLUG, item.path);
}

/** Sections for a role inside a workspace: the workspace (or team) pages, the tools, and — for
 *  admins — the admin pages. Empty sections are dropped. */
export function navForRole(role: Role, slug: string | null | undefined): NavSection[] {
  const isTeam = !slug || slug === TEAM_SLUG;
  const resolve = (items: NavItem[]): ResolvedNavItem[] =>
    items.filter((i) => i.roles.includes(role)).map((i) => ({ ...i, href: hrefFor(i, slug) }));
  const sections: NavSection[] = [
    { title: null, items: resolve(isTeam ? TEAM_NAV : WORKSPACE_NAV) },
    { title: "Admin", items: resolve(ADMIN_NAV) },
  ];
  return sections.filter((s) => s.items.length > 0);
}

/** Is this nav item the one the pathname is on? */
export function isActive(item: ResolvedNavItem, pathname: string): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(item.href + "/");
}

/** A label for a workspace page path ("/queue" → "Needs analysis"), for breadcrumbs and titles. */
export function labelForPage(page: string, isTeam: boolean): string | null {
  const items = isTeam ? TEAM_NAV : WORKSPACE_NAV;
  const first = "/" + page.split("/").filter(Boolean)[0];
  return items.find((i) => i.path === first)?.label ?? null;
}

/** Labels for the absolute pages outside a workspace. */
export const GLOBAL_LABELS: Record<string, string> = {
  feedback: "Feedback",
  new: "New analysis",
  admin: "Admin",
  scoring: "Scoring",
  identity: "Identity",
  people: "People",
  sync: "Sync",
  audit: "Audit",
  share: "Shared report",
  classes: "Classes",
  queue: "Queue",
  overview: "Overview",
  instructors: "Instructors",
  cohorts: "Cohorts",
  modules: "Modules",
  reports: "Reports",
  settings: "Settings",
  team: "All courses",
};

/** Table2 is the classes icon; Rows3 stays exported for dense-list callers. */
export const ICONS = { classes: Table2, rows: Rows3 };
