/** The eight fixed course colours (plan 5e) — used only as the course identity square, never for
 *  data. `courses.color` stores the 1–8 index; the shell's `--course-N` tokens (globals.css)
 *  paint it, and `courseColor` (lib/workspace-shared) resolves missing values by hashing the slug
 *  so a course keeps its colour everywhere. */

export { courseColor, courseInitials } from "@/lib/workspace-shared";

export const COURSE_HUES: { key: string; label: string; token: string }[] = [
  { key: "1", label: "Blue", token: "var(--course-1, oklch(0.55 0.16 250))" },
  { key: "2", label: "Violet", token: "var(--course-2, oklch(0.55 0.17 300))" },
  { key: "3", label: "Teal", token: "var(--course-3, oklch(0.58 0.12 180))" },
  { key: "4", label: "Amber", token: "var(--course-4, oklch(0.7 0.15 70))" },
  { key: "5", label: "Red", token: "var(--course-5, oklch(0.58 0.18 15))" },
  { key: "6", label: "Green", token: "var(--course-6, oklch(0.56 0.14 145))" },
  { key: "7", label: "Pink", token: "var(--course-7, oklch(0.55 0.15 330))" },
  { key: "8", label: "Cyan", token: "var(--course-8, oklch(0.56 0.12 215))" },
];
