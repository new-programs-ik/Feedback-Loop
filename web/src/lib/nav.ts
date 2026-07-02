import {
  LayoutDashboard, MessageSquareText, GraduationCap, Users, BookOpen, Boxes,
  HeartPulse, Settings, ScrollText, User, type LucideIcon,
} from "lucide-react";
import type { Role } from "./session";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  roles: Role[];
  live: boolean; // false → reachable but shows a "Coming soon" page
};
export type NavSection = { title: string | null; items: NavItem[] };

/** Full navigation for the platform. Only the Feedback module is live in this milestone. */
export const NAV: NavSection[] = [
  {
    title: null,
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, roles: ["admin", "pm", "learner"], live: true },
      { label: "Feedback", href: "/feedback", icon: MessageSquareText, roles: ["admin", "pm"], live: true },
    ],
  },
  {
    title: "Analytics",
    items: [
      { label: "Instructor Analytics", href: "/instructor-analytics", icon: GraduationCap, roles: ["admin", "pm"], live: false },
      { label: "Learner Analytics", href: "/learner-analytics", icon: Users, roles: ["admin", "pm"], live: false },
      { label: "Course Analytics", href: "/course-analytics", icon: BookOpen, roles: ["admin", "pm"], live: false },
      { label: "Cohort Analytics", href: "/cohort-analytics", icon: Boxes, roles: ["admin", "pm"], live: false },
      { label: "Learner Health", href: "/learner-health", icon: HeartPulse, roles: ["admin", "pm"], live: false },
    ],
  },
  {
    title: "My learning",
    items: [
      { label: "My Performance", href: "/my-performance", icon: User, roles: ["learner"], live: false },
      { label: "My Health Score", href: "/my-health", icon: HeartPulse, roles: ["learner"], live: false },
    ],
  },
  {
    title: "Admin",
    items: [
      { label: "Users & Roles", href: "/admin/users", icon: Settings, roles: ["admin"], live: false },
      { label: "Audit Log", href: "/admin/audit-log", icon: ScrollText, roles: ["admin"], live: false },
    ],
  },
];

/** Sections/items visible to a given role (empty sections dropped). */
export function navForRole(role: Role): NavSection[] {
  return NAV.map((s) => ({ ...s, items: s.items.filter((i) => i.roles.includes(role)) })).filter(
    (s) => s.items.length > 0,
  );
}
