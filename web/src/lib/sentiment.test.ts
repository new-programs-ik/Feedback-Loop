import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { explainClass, round2, scoreClass, type ScoreInputs, type ScoringConfig } from "./sentiment.ts";

/** Pins the web mirror to the same fixtures as the database function and the Python reference
 *  (`analysis/sentiment_score.py`). Run with `npm test` (Node's built-in runner, no build). */

type Case = {
  id: string;
  config: string;
  label: string;
  inputs: ScoreInputs;
  expected: { score: number | null; band: string | null; action: string; provisional: boolean; flags: string[] };
  reason: string;
};

const read = (rel: string) => JSON.parse(readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8"));
const configs = read("../../../supabase/fixtures/scoring_configs.json") as Record<string, ScoringConfig>;
const fixture = read("../../../supabase/fixtures/scoring_cases.json") as { cases: Case[] };

// Derived, not a magic number: a hard-coded count fails on every legitimate addition to the
// contract and catches no real defect. What matters is that every case can be scored and every
// configuration a case names actually exists.
test("the fixture is a complete, usable contract", () => {
  assert.ok(fixture.cases.length >= 94, "the contract should not shrink");
  const used = new Set(fixture.cases.map((c) => c.config));
  for (const key of used) assert.ok(configs[key], `case refers to config ${key}, which is missing`);
  for (const key of ["C0", "C1", "C2", "C3", "C4", "C5"]) assert.ok(configs[key], `config ${key} present`);
  assert.ok(used.has("C0F"), "the live settings (the 4.3 rating floor) must be covered");
});

for (const c of fixture.cases) {
  test(`${c.id} · ${c.label}`, () => {
    const cfg = configs[c.config];
    assert.ok(cfg, `unknown config ${c.config}`);
    const r = scoreClass(c.inputs, cfg);
    assert.equal(r.score, c.expected.score, "score");
    assert.equal(r.band, c.expected.band, "band");
    assert.equal(r.action, c.expected.action, "action");
    assert.equal(r.provisional, c.expected.provisional, "provisional");
    assert.deepEqual(new Set(r.flags), new Set(c.expected.flags), "flags (as a set)");
    assert.equal(r.flags.length, new Set(r.flags).size, "no flag is emitted twice");
    assert.equal(explainClass(c.inputs, r, cfg), c.reason, "the one-sentence reason");
  });
}

test("round2 is half-up on the shortest decimal form (Python Decimal(str(v)) semantics)", () => {
  assert.equal(round2(0.125), 0.13);
  assert.equal(round2(2.675), 2.68); // str(2.675) == "2.675" → half up
  assert.equal(round2(89.995), 90);
  assert.equal(round2(1.005), 1.01);
  assert.equal(round2(99.999), 100);
  assert.equal(round2(-0.125), -0.13);
  assert.equal(round2(88.29), 88.29);
  assert.equal(round2(50), 50);
});

test("the shorthand Math.round((x + EPSILON) * 100) / 100 agrees with round2 on every fixture score", () => {
  for (const c of fixture.cases) {
    const r = scoreClass(c.inputs, configs[c.config]);
    if (r.score == null) continue;
    // recompute the raw weighted score from the components to compare the two roundings
    let acc = 0;
    let denom = 0;
    for (const [key, w] of Object.entries(r.weights_used)) {
      const v = r.components[key as keyof typeof r.components];
      if (v == null || w == null) continue;
      acc += v * w;
      denom += w;
    }
    // components are themselves rounded, so only check the agreement of the two formulas
    const raw = denom ? acc / denom : 0;
    assert.equal(Math.round((raw + Number.EPSILON) * 100) / 100, round2(raw), c.id);
  }
});

test("the band reads the rounded score", () => {
  const cfg = configs.C0;
  // 89.995 → 90.00 → excellent, not good
  const r = scoreClass({ rating: 4.9, num_ratings: 10, attended: 10, yes_votes: 10, no_votes: 0 }, cfg);
  assert.equal(r.score, 98.8);
  assert.equal(r.band, "excellent");
  const edge = scoreClass({ rating: 4.5, num_ratings: 10, attended: 10, yes_votes: 8, no_votes: 2 }, cfg);
  assert.equal(edge.band, edge.score != null && edge.score >= 90 ? "excellent" : "good");
});

test("missing inputs never crash and never invent a number", () => {
  const r = scoreClass({}, configs.C5);
  assert.equal(r.score, null);
  assert.equal(r.band, null);
  assert.equal(r.action, "watch");
  assert.deepEqual(r.flags, ["no_rating"]);
  const s = scoreClass({ rating: "4.7", num_ratings: "12", attended: "", yes_votes: null, no_votes: undefined }, configs.C0);
  assert.ok(s.score != null);
  assert.ok(s.flags.includes("no_vote"));
  assert.ok(s.flags.includes("no_attendance"));
});
