import { test } from "node:test";
import assert from "node:assert/strict";
import { addMonths, monthEnd, reportPeriod, weekStart } from "./report-period.ts";

// Monday 7 Sep 2026 is "today" in every case; the sheet's last rated class varies.
const TODAY = "2026-09-07";

test("date helpers", () => {
  assert.equal(weekStart("2026-09-07"), "2026-09-07"); // a Monday
  assert.equal(weekStart("2026-09-13"), "2026-09-07"); // the Sunday of that week
  assert.equal(monthEnd("2026-02"), "2026-02-28");
  assert.equal(addMonths("2026-01", -1), "2025-12");
  assert.equal(addMonths("2026-12", 1), "2027-01");
});

test("weekly: the last complete Mon–Sun week when the data is current", () => {
  const w = reportPeriod({}, "2026-09-06", TODAY);
  assert.deepEqual([w.from, w.to, w.label, w.stale], ["2026-08-31", "2026-09-06", "Weekly", true]);
  assert.equal(w.prev, "2026-08-24");
  assert.equal(w.next, null); // nothing rated after the anchor
});

test("weekly: never empty when the sheet is behind — ends on the last rated class", () => {
  const w = reportPeriod({}, "2026-08-30", TODAY); // last class = Sunday 30 Aug
  assert.deepEqual([w.from, w.to, w.stale], ["2026-08-24", "2026-08-30", true]);
  const mid = reportPeriod({}, "2026-08-28", TODAY); // last class = Friday 28 Aug
  assert.deepEqual([mid.from, mid.to], ["2026-08-24", "2026-08-28"]);
});

test("weekly: today is used when the data is newer than today or missing", () => {
  const w = reportPeriod({}, null, TODAY);
  assert.deepEqual([w.from, w.to], ["2026-08-31", "2026-09-06"]);
  assert.equal(w.anchor, TODAY);
  assert.equal(reportPeriod({}, "2026-09-09", TODAY).anchor, TODAY);
});

test("weekly: ‹ › step through weeks and stop at the last rated class", () => {
  const w = reportPeriod({ at: "2026-08-12" }, "2026-08-30", TODAY);
  assert.deepEqual([w.from, w.to], ["2026-08-10", "2026-08-16"]);
  assert.equal(w.prev, "2026-08-03");
  assert.equal(w.next, "2026-08-17");
  const last = reportPeriod({ at: "2026-08-25" }, "2026-08-30", TODAY);
  assert.equal(last.next, null);
  // an `at` after the anchor is ignored
  assert.deepEqual(reportPeriod({ at: "2026-09-03" }, "2026-08-30", TODAY).from, "2026-08-24");
});

test("monthly: the last complete month, trimmed to the last rated class", () => {
  const m = reportPeriod({ period: "month" }, "2026-08-30", TODAY);
  assert.deepEqual([m.from, m.to, m.label, m.stale], ["2026-08-01", "2026-08-30", "Monthly", true]);
  assert.equal(m.prev, "2026-07-01");
  assert.equal(m.next, null);
  const live = reportPeriod({ period: "month" }, "2026-09-06", TODAY);
  assert.deepEqual([live.from, live.to], ["2026-08-01", "2026-08-31"]);
  assert.equal(live.next, "2026-09-01");
});

test("monthly: the data ends before the last complete month — the month of the last class", () => {
  const m = reportPeriod({ period: "month" }, "2026-07-20", TODAY);
  assert.deepEqual([m.from, m.to], ["2026-07-01", "2026-07-20"]);
  const nav = reportPeriod({ period: "month", at: "2026-05-15" }, "2026-07-20", TODAY);
  assert.deepEqual([nav.from, nav.to, nav.next], ["2026-05-01", "2026-05-31", "2026-06-01"]);
});

test("custom: explicit dates, swapped when reversed, defaults to the last 30 days", () => {
  const c = reportPeriod({ period: "custom", from: "2026-08-20", to: "2026-08-10" }, "2026-08-30", TODAY);
  assert.deepEqual([c.from, c.to, c.label, c.prev, c.next], ["2026-08-10", "2026-08-20", "Custom", null, null]);
  const d = reportPeriod({ period: "custom" }, "2026-08-30", TODAY);
  assert.deepEqual([d.from, d.to], ["2026-08-08", TODAY]);
});
