import { test } from "node:test";
import assert from "node:assert/strict";
import { MAX_CUSTOM_DAYS, reportPeriod } from "./report-period.ts";

test("a custom window never runs past today or further back than the cap", () => {
  const w = reportPeriod({ period: "custom", from: "1900-01-01", to: "2100-01-01" }, "2026-09-20", "2026-09-21");
  assert.equal(w.to, "2026-09-21");
  const days = (Date.parse(w.to) - Date.parse(w.from)) / 86_400_000;
  assert.equal(days, MAX_CUSTOM_DAYS);
});

test("a sensible custom window is left alone", () => {
  const w = reportPeriod({ period: "custom", from: "2026-08-01", to: "2026-08-31" }, "2026-09-20", "2026-09-21");
  assert.deepEqual([w.from, w.to], ["2026-08-01", "2026-08-31"]);
});

test("a reversed custom window is put the right way round", () => {
  const w = reportPeriod({ period: "custom", from: "2026-08-31", to: "2026-08-01" }, "2026-09-20", "2026-09-21");
  assert.deepEqual([w.from, w.to], ["2026-08-01", "2026-08-31"]);
});
