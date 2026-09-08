import { test } from "node:test";
import assert from "node:assert/strict";
import { OUTCOME_RANK, avgAttended, outcomeStage, worstOf } from "./table-rows.ts";

test("avgAttended averages only the classes that recorded a room size", () => {
  assert.equal(avgAttended([{ attended: 20 }, { attended: null }, { attended: 30 }]), 25);
  assert.equal(avgAttended([{ attended: null }]), null);
  assert.equal(avgAttended([]), null);
});

test("worstOf keeps banded rows only, lowest score then lowest rating first", () => {
  const row = (id: string, score: number | null, band: "bad" | "average" | "excellent" | null, rating: number) => ({ id, score, band, rating });
  const rows = [row("a", 62, "average", 4.4), row("b", null, null, 3.9), row("c", 55, "bad", 4.5), row("d", 55, "bad", 4.1), row("e", 91, "excellent", 4.9)];
  assert.deepEqual(
    worstOf(rows, 3).map((r) => r.id),
    ["d", "c", "a"],
  );
  assert.equal(worstOf(rows, 10).length, 4); // the unbanded row never makes the list
});

test("outcomeStage reads the loop's record first, then the review status", () => {
  const none = { analysed: false, approved: false, sent: false, classId: null };
  assert.equal(outcomeStage("new", none), "open");
  assert.equal(outcomeStage("notified", null), "open");
  assert.equal(outcomeStage("confirmed", none), "confirmed");
  assert.equal(outcomeStage("analysis_started", none), "confirmed");
  assert.equal(outcomeStage("dismissed", none), "dismissed");
  assert.equal(outcomeStage("new", { ...none, analysed: true }), "analysed");
  assert.equal(outcomeStage("new", { ...none, analysed: true, approved: true }), "approved");
  assert.equal(outcomeStage("dismissed", { ...none, analysed: true, approved: true, sent: true, classId: "c1" }), "sent");
});

test("OUTCOME_RANK follows the loop, open first", () => {
  const stages = Object.entries(OUTCOME_RANK)
    .sort((a, b) => a[1] - b[1])
    .map(([k]) => k);
  assert.deepEqual(stages, ["open", "dismissed", "confirmed", "analysed", "approved", "sent"]);
});
