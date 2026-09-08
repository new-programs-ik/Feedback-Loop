import type { MonthOption } from "./scoring-workbench";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** The last `n` calendar months, newest first, as preview options. Computed on the server so
 *  the client never has to know "today" during hydration. The current month runs to today. */
export function lastMonths(n = 12, today = new Date()): { months: MonthOption[]; defaultMonth: string } {
  const months: MonthOption[] = [];
  for (let i = 0; i < n; i++) {
    const first = new Date(today.getFullYear(), today.getMonth() - i, 1);
    const lastDay = new Date(first.getFullYear(), first.getMonth() + 1, 0);
    const end = i === 0 ? today : lastDay;
    const value = `${first.getFullYear()}-${String(first.getMonth() + 1).padStart(2, "0")}`;
    months.push({
      value,
      label: first.toLocaleDateString("en-US", { month: "long", year: "numeric" }) + (i === 0 ? " (so far)" : ""),
      from: iso(first),
      to: iso(end),
    });
  }
  // Default to the last FULL month — a whole month is the honest unit for "analyses per week".
  const defaultMonth = months[1]?.value ?? months[0].value;
  return { months, defaultMonth };
}
