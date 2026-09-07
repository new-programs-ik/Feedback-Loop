/** Workspace types + pure helpers, importable from server AND client code. */

export const TEAM_SLUG = "team";
export const WS_COOKIE = "fl_ws";

export type MemberRole = "owner" | "pm" | "viewer";

export type CourseSummary = {
  id: string;
  slug: string;
  name: string;
  /** A CSS colour (resolved from `courses.color` or the eight fixed course colours). */
  color: string;
  initials: string;
  /** The signed-in user is a member of this course. */
  mine: boolean;
  role: MemberRole | null;
  cohorts: number;
  handler: string | null;
};

export type Workspace = {
  /** "team" for the leadership level. */
  slug: string;
  courseId: string | null;
  courseName: string;
  color: string;
  initials: string;
  role: MemberRole | null;
  isTeam: boolean;
  cohorts: number;
  handler: string | null;
};

export const TEAM_WORKSPACE: Workspace = {
  slug: TEAM_SLUG,
  courseId: null,
  courseName: "All courses",
  color: "var(--primary)",
  initials: "IK",
  role: null,
  isTeam: true,
  cohorts: 0,
  handler: null,
};

/** Team-level paths for the workspace pages that exist there under a different name. */
const TEAM_PATHS: Record<string, string> = {
  "/overview": "/team",
  "": "/team",
  "/": "/team",
};

/** A path inside a workspace: `hrefIn("agentic-ai", "/queue")` → `/c/agentic-ai/queue`;
 *  `hrefIn("team", "/queue")` → `/team/queue`; `hrefIn(null, "/overview")` → `/team`.
 *  Absolute app paths (`/admin/…`, `/tools/…`, `/feedback/new`) pass through untouched. */
export function hrefIn(slug: string | null | undefined, path: string): string {
  if (path.startsWith("/admin") || path.startsWith("/tools") || path.startsWith("/share") || path.startsWith("/feedback/")) return path;
  const p = path.startsWith("/") || path === "" ? path : `/${path}`;
  if (!slug || slug === TEAM_SLUG) return TEAM_PATHS[p] ?? `/team${p}`;
  return `/c/${slug}${p === "" || p === "/" ? "/overview" : p}`;
}

/** The workspace slug a pathname points at: "team", a course slug, or null (outside any). */
export function slugFromPath(pathname: string): string | null {
  if (pathname === "/team" || pathname.startsWith("/team/")) return TEAM_SLUG;
  const m = pathname.match(/^\/c\/([^/]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/** The page path inside the workspace ("/queue", "/classes/abc"), or null outside one. */
export function pageFromPath(pathname: string): string | null {
  if (pathname === "/team") return "/overview";
  if (pathname.startsWith("/team/")) return pathname.slice("/team".length);
  const m = pathname.match(/^\/c\/[^/]+(\/.*)?$/);
  if (!m) return null;
  return m[1] && m[1] !== "/" ? m[1] : "/overview";
}

const CSS_COLOUR = /^(#|oklch\(|rgb\(|hsl\(|var\()/i;

/** `courses.color` may be missing, a 1–8 index, or a real CSS colour; anything else hashes the
 *  slug onto the eight fixed course colours so a course keeps its colour everywhere. */
export function courseColor(raw: string | null | undefined, slug = ""): string {
  if (raw) {
    const v = raw.trim();
    if (/^[1-8]$/.test(v)) return `var(--course-${v})`;
    if (CSS_COLOUR.test(v)) return v;
    if (/^course-[1-8]$/.test(v)) return `var(--${v})`;
  }
  let h = 0;
  for (const ch of slug) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return `var(--course-${(h % 8) + 1})`;
}

export function courseInitials(raw: string | null | undefined, name = ""): string {
  if (raw && raw.trim()) return raw.trim().slice(0, 3).toUpperCase();
  const words = name.replace(/[()&,]/g, " ").split(/\s+/).filter((w) => w && !/^(and|of|the|for|in|with|to|a|an)$/i.test(w));
  const letters = words.slice(0, 3).map((w) => w[0]);
  return (letters.join("") || name.slice(0, 2)).toUpperCase();
}

export function workspaceFor(course: CourseSummary | null | undefined): Workspace {
  if (!course) return TEAM_WORKSPACE;
  return {
    slug: course.slug,
    courseId: course.id,
    courseName: course.name,
    color: course.color,
    initials: course.initials,
    role: course.role,
    isTeam: false,
    cohorts: course.cohorts,
    handler: course.handler,
  };
}
