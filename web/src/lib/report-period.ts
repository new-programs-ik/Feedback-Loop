/** The report window — pure date logic with no server imports, so `npm test` can pin it.
 *
 *  Weekly = the last complete Mon–Sun week; monthly = the last complete calendar month. If the
 *  synced data ends before that period starts (the sheet is a few days behind), the report uses the
 *  period that contains the last rated class and ends there — a report is never empty just because
 *  nothing newer has synced. `at` (any date inside a period) steps to another week or month. */

export type ReportPeriod = "week" | "month" | "custom";
export type SearchParamsLike = Record<string, string | string[] | undefined>;

export type ReportWindow = {
  period: ReportPeriod;
  from: string;
  to: string;
  /** "Weekly" · "Monthly" · "Custom" — the report's title word. */
  label: string;
  /** The last date a report can reach: today, or the last rated class when the sheet is behind. */
  anchor: string;
  /** A date inside the previous / next period, for the ‹ › links; null at the edges. */
  prev: string | null;
  next: string | null;
  /** The window ends before today because the synced data does. */
  stale: boolean;
};

const ISO = /^\d{4}-\d{2}-\d{2}$/;
export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (isoDate: string, n: number) => iso(new Date(+new Date(isoDate + "T00:00:00Z") + n * 86400000));

/** Monday of the week containing the date. */
export function weekStart(isoDate: string): string {
  const d = new Date(isoDate + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return iso(d);
}
export const monthEnd = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return iso(new Date(Date.UTC(y, m, 0)));
};
export const addMonths = (ym: string, n: number) => {
  const [y, m] = ym.split("-").map(Number);
  return iso(new Date(Date.UTC(y, m - 1 + n, 1))).slice(0, 7);
};

const first = (sp: SearchParamsLike, k: string) => {
  const v = sp[k];
  return Array.isArray(v) ? v[0] : v;
};

/** The longest custom window a report or export will run: fifteen months, like the what-if preview. */
export const MAX_CUSTOM_DAYS = 460;

export function reportPeriod(sp: SearchParamsLike, latest?: string | null, todayIso?: string): ReportWindow {
  const raw = first(sp, "period");
  const period: ReportPeriod = raw === "month" || raw === "custom" ? raw : "week";
  const t = todayIso ?? iso(new Date());
  const anchor = latest && ISO.test(latest) && latest < t ? latest : t;
  const atRaw = first(sp, "at");
  const at = atRaw && ISO.test(atRaw) && atRaw <= anchor ? atRaw : null;

  if (period === "custom") {
    const f0 = first(sp, "from");
    const t0 = first(sp, "to");
    const f = f0 && ISO.test(f0) ? f0 : addDays(t, -30);
    const tt = t0 && ISO.test(t0) ? t0 : t;
    let [from, to] = f <= tt ? [f, tt] : [tt, f];
    // Bounded: `from=1900-01-01&to=2100-01-01` used to read the whole archive twice in one request.
    if (to > t) to = t;
    if (from < addDays(to, -MAX_CUSTOM_DAYS)) from = addDays(to, -MAX_CUSTOM_DAYS);
    return { period, from, to, label: "Custom", anchor, prev: null, next: null, stale: false };
  }

  if (period === "month") {
    let ym = at ? at.slice(0, 7) : addMonths(t.slice(0, 7), -1);
    if (`${ym}-01` > anchor) ym = anchor.slice(0, 7);
    const from = `${ym}-01`;
    const end = monthEnd(ym);
    const to = end < anchor ? end : anchor;
    const nextFrom = `${addMonths(ym, 1)}-01`;
    return { period, from, to, label: "Monthly", anchor, prev: `${addMonths(ym, -1)}-01`, next: nextFrom <= anchor ? nextFrom : null, stale: to < t };
  }

  let from = at ? weekStart(at) : addDays(weekStart(t), -7);
  if (from > anchor) from = weekStart(anchor);
  const sunday = addDays(from, 6);
  const to = sunday < anchor ? sunday : anchor;
  const nextFrom = addDays(from, 7);
  return { period, from, to, label: "Weekly", anchor, prev: addDays(from, -7), next: nextFrom <= anchor ? nextFrom : null, stale: to < t };
}
