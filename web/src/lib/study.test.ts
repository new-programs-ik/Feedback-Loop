import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { scoreClass, type ScoreInputs, type ScoringConfig } from "./sentiment.ts";
import {
  approvalOf,
  badAboveLine,
  driftByMonth,
  falseAlarm,
  falseComfort,
  inputsOf,
  nextClassRisk,
  priorsByCourse,
  scoreUnder,
  slices,
  studyMeasures,
  studyWindow,
  trustByVotes,
  voicesOf,
  weekdayOf,
  type StudyRow,
} from "./study.ts";

/** The live study's arithmetic on synthetic classes (fictional names throughout). The expected
 *  numbers below are worked out by hand from the contract (sentiment.ts) — the point is to pin
 *  the study's definitions, not to re-test the scorer. Run with `npm test`. */

const read = (rel: string) => JSON.parse(readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8"));
const configs = read("../../../supabase/fixtures/scoring_configs.json") as Record<string, ScoringConfig>;
const C0 = configs.C0; // the manager's original — version 1
/** The recommended shape: C5 (two lines + graded score) with the guard off and an analysis from 6 votes. */
const REC: ScoringConfig = { ...configs.C5, name: "recommended (test)", guard: { k: 0, prior: "course" }, min_votes: { band: 3, action: 6 } };
/** Band edges so high almost everything is Bad — the only way to manufacture a false alarm. */
const STRICT: ScoringConfig = { ...C0, name: "strict (test)", bands: { excellent: 99, good: 98, average: 97 } };

let seq = 0;
function row(over: Partial<StudyRow> = {}): StudyRow {
  seq += 1;
  return {
    id: `r${seq}`,
    class_date: "2026-03-02",
    rating: 4.8,
    num_ratings: 12,
    attended: 30,
    yes_votes: 12,
    no_votes: 0,
    course_id: "course-a",
    course_label: "Course A",
    instructor: "Pat Example",
    topic: "Module 1",
    session_kind: "Live Class",
    ...over,
  };
}

// ── the window ────────────────────────────────────────────────────────────────
test("studyWindow: the last eight full months, or 1 January → today while the year is shorter", () => {
  const sep = studyWindow("2026-09-07");
  assert.deepEqual([sep.from, sep.to, sep.fullMonths, sep.label, sep.days], ["2026-01-01", "2026-08-31", true, "Jan–Aug 2026", 243]);
  assert.ok(Math.abs(sep.weeks - 243 / 7) < 1e-9);
  const dec = studyWindow("2026-12-15");
  assert.deepEqual([dec.from, dec.to, dec.label], ["2026-04-01", "2026-11-30", "Apr–Nov 2026"]);
  const mar = studyWindow("2026-03-10");
  assert.deepEqual([mar.from, mar.to, mar.fullMonths, mar.label], ["2026-01-01", "2026-03-10", false, "1 Jan – 10 Mar 2026"]);
  const jan = studyWindow("2027-01-03");
  assert.deepEqual([jan.from, jan.to, jan.days], ["2027-01-01", "2027-01-03", 3]);
});

// ── row readers ───────────────────────────────────────────────────────────────
test("voices are the vote count when a vote exists, else the rating count; approval is yes over votes", () => {
  assert.equal(voicesOf(row({ yes_votes: 7, no_votes: 3 })), 10);
  assert.equal(voicesOf(row({ yes_votes: null, no_votes: null, num_ratings: 7 })), 7);
  assert.equal(voicesOf(row({ yes_votes: null, no_votes: null, num_ratings: null })), 0);
  assert.equal(approvalOf(row({ yes_votes: 3, no_votes: 1 })), 75);
  assert.equal(approvalOf(row({ yes_votes: 0, no_votes: 0, approval_pct: 66 })), 66);
  assert.equal(approvalOf(row({ yes_votes: null, no_votes: null })), null);
});

test("priorsByCourse: the course's mean rating and pooled approval, keyed like the app", () => {
  const rows = [
    row({ rating: 4.8, yes_votes: 12, no_votes: 0 }),
    row({ rating: 4.4, yes_votes: 5, no_votes: 5 }),
    row({ course_id: null, course_label: "Course B", rating: 4.0, yes_votes: null, no_votes: null }),
  ];
  const p = priorsByCourse(rows);
  const a = p.get("course-a")!;
  assert.ok(Math.abs(a.rating! - 4.6) < 1e-9);
  assert.ok(Math.abs(a.approval! - (17 / 22) * 100) < 1e-9);
  assert.deepEqual(p.get("label:Course B"), { rating: 4, approval: null });
});

// ── scoring plumbing ──────────────────────────────────────────────────────────
test("scoreUnder agrees with scoreClass on every numeric fixture case of the original (no guard)", () => {
  const fixture = read("../../../supabase/fixtures/scoring_cases.json") as { cases: { id: string; config: string; inputs: ScoreInputs }[] };
  let checked = 0;
  for (const c of fixture.cases) {
    if (c.config !== "C0") continue;
    const i = c.inputs;
    const plain = (v: unknown) => v == null || typeof v === "number";
    if (typeof i.rating !== "number" || !plain(i.num_ratings) || !plain(i.attended) || !plain(i.yes_votes) || !plain(i.no_votes) || !plain(i.track_avg)) continue;
    const r = row({
      rating: i.rating,
      num_ratings: (i.num_ratings as number | null | undefined) ?? null,
      attended: (i.attended as number | null | undefined) ?? null,
      yes_votes: (i.yes_votes as number | null | undefined) ?? null,
      no_votes: (i.no_votes as number | null | undefined) ?? null,
      escalated: i.escalated ?? null,
      track_avg: (i.track_avg as number | null | undefined) ?? null,
    });
    const want = scoreClass(i, C0);
    const got = scoreUnder([r], C0)[0];
    assert.deepEqual([got.score, got.band, got.action, got.provisional], [want.score, want.band, want.action, want.provisional], c.id);
    checked += 1;
  }
  assert.ok(checked >= 10, `checked ${checked} cases`);
});

test("scoreUnder hands the guard the course prior computed from the rows in hand", () => {
  const a = row({ rating: 4.8, num_ratings: 12, yes_votes: 12, no_votes: 0 });
  const b = row({ rating: 4.0, num_ratings: 4, attended: 20, yes_votes: 2, no_votes: 2 });
  const guarded = configs.C3; // k = 5
  const got = scoreUnder([a, b], guarded)[1];
  const want = scoreClass({ ...inputsOf(b), prior_rating: 4.4, prior_approval: 87.5 }, guarded);
  assert.deepEqual(got, want);
  assert.ok(got.flags.includes("guarded"));
});

// ── the two human signals ─────────────────────────────────────────────────────
/** Six voiced classes and one thin one; every verdict below is worked out from the contract. */
const H1 = row({ id: "H1", rating: 4.4, num_ratings: 12, yes_votes: 12, no_votes: 0 }); // C0 90.4 Excellent (low!) · REC Average by cap
const H2 = row({ id: "H2", rating: 4.8, num_ratings: 12, yes_votes: 9, no_votes: 3 }); // C0 65.2 Average · REC Average by cap
const H3 = row({ id: "H3", rating: 4.8, num_ratings: 8, attended: 40, yes_votes: 6, no_votes: 2 }); // C0 58.4 Bad though rated 4.8 · REC Average
const H4 = row({ id: "H4", rating: 4.2, num_ratings: 12, yes_votes: 6, no_votes: 6 }); // C0 58.0 Bad · REC 41.76 Bad
const H5 = row({ id: "H5", rating: 4.3, num_ratings: 4, yes_votes: 4, no_votes: 0 }); // 4 voices: not in the population
const H6 = row({ id: "H6", rating: 4.5, num_ratings: 5, yes_votes: 5, no_votes: 0 }); // C0 84.67 Good firm (low) · REC 79.71 Good provisional
const H7 = row({ id: "H7", rating: 4.9, num_ratings: 12, yes_votes: 12, no_votes: 0 }); // C0 96.4 Excellent · REC 96.08 Excellent
const HUMAN = [H1, H2, H3, H4, H5, H6, H7];

test("the worked verdicts hold (guards the hand arithmetic behind the next three tests)", () => {
  const c0 = scoreUnder(HUMAN, C0).map((x) => [x.score, x.band, x.provisional]);
  assert.deepEqual(c0, [
    [90.4, "excellent", false],
    [65.2, "average", false],
    [58.4, "bad", false],
    [58, "bad", false],
    [82.13, "good", false],
    [84.67, "good", false],
    [96.4, "excellent", false],
  ]);
  const rec = scoreUnder(HUMAN, REC).map((x) => [x.band, x.provisional]);
  assert.deepEqual(rec, [
    ["average", false],
    ["average", false],
    ["average", false],
    ["bad", false],
    ["average", true],
    ["good", true],
    ["excellent", false],
  ]);
});

test("falseComfort: low classes with 5+ votes shown Good or Excellent — firm vs provisional", () => {
  const c0 = falseComfort(HUMAN, C0);
  assert.deepEqual(
    [c0.voiced, c0.count, c0.firm, c0.provisional, c0.byRating, c0.byApproval],
    [6, 2, 2, 0, 2, 0],
  );
  assert.ok(Math.abs(c0.sharePct! - (2 / 6) * 100) < 1e-9);
  const rec = falseComfort(HUMAN, REC);
  assert.deepEqual([rec.voiced, rec.count, rec.firm, rec.provisional, rec.byRating], [6, 1, 0, 1, 1]);
  assert.equal(rec.firmSharePct, 0);
});

test("badAboveLine: Bad classes that were rated 4.55 or better", () => {
  assert.deepEqual(badAboveLine(HUMAN, C0), { bad: 2, count: 1, sharePct: 50 });
  assert.deepEqual(badAboveLine(HUMAN, REC), { bad: 1, count: 0, sharePct: 0 });
  assert.deepEqual(badAboveLine([], REC), { bad: 0, count: 0, sharePct: null });
});

test("falseAlarm: a voiced Bad class that clears both lines (only a strict band edge can make one)", () => {
  assert.equal(falseAlarm(HUMAN, C0).count, 0);
  assert.equal(falseAlarm(HUMAN, REC).count, 0);
  const strict = falseAlarm(HUMAN, STRICT);
  assert.deepEqual([strict.voiced, strict.count], [6, 1]);
  assert.ok(Math.abs(strict.sharePct! - (1 / 6) * 100) < 1e-9);
  assert.deepEqual(badAboveLine(HUMAN, STRICT), { bad: 7, count: 3, sharePct: (3 / 7) * 100 });
});

test("studyMeasures bundles the three measures over one scoring pass", () => {
  const m = studyMeasures(HUMAN, REC, { minPairs: 1 });
  assert.equal(m.results.length, HUMAN.length);
  assert.deepEqual(m.bands, { excellent: 1, good: 1, average: 4, bad: 1 });
  assert.equal(m.noBand, 0);
  assert.equal(m.provisional, 2);
  assert.equal(m.comfort.count, 1);
  assert.equal(m.badAbove.bad, 1);
  assert.equal(m.alarm.count, 0);
});

// ── the next class ────────────────────────────────────────────────────────────
const P = (id: string, date: string, over: Partial<StudyRow>) => row({ id, class_date: date, instructor: "Pat Example", ...over });
const Q = (id: string, date: string, over: Partial<StudyRow>) => row({ id, class_date: date, instructor: "Sam Sample", ...over });
const JOURNEY: StudyRow[] = [
  P("P1", "2026-02-01", { rating: 4.9 }), // Excellent → next P2 is low
  P("P2", "2026-02-08", { rating: 4.2, yes_votes: 6, no_votes: 6 }), // Bad → next P3 is fine
  P("P3", "2026-02-15", { rating: 4.8 }), // Excellent → next P4 is low (approval 75%)
  P("P4", "2026-02-22", { rating: 4.7, yes_votes: 9, no_votes: 3 }), // Average by cap → next P5 has 4 votes: pair dropped
  P("P5", "2026-03-01", { rating: 4.6, num_ratings: 4, yes_votes: 4, no_votes: 0 }), // thin → pair with P6 dropped too
  P("P6", "2026-03-08", { rating: 4.9 }), // the last class: no next
  Q("Q1", "2026-02-03", { rating: 4.5, num_ratings: 5, yes_votes: 5, no_votes: 0 }), // Good, provisional → in the baseline, not in a band row
  Q("Q2", "2026-02-10", { rating: 4.9 }),
  row({ id: "R1", instructor: "", instructor_canonical: null, rating: 4.0 }), // nobody named: ignored
];

test("nextClassRisk: pairs need 5+ votes on both sides; provisional bands stay out of the band rows", () => {
  const r = nextClassRisk(JOURNEY, REC, { minPairs: 1 });
  assert.equal(r.pairs, 4);
  assert.deepEqual(r.baseline, { n: 4, low: 2, lowPct: 50 });
  const by = Object.fromEntries(r.bands.map((b) => [b.band, b]));
  assert.deepEqual(by.excellent, { band: "excellent", n: 2, low: 2, lowPct: 100, tooFew: false });
  assert.deepEqual(by.bad, { band: "bad", n: 1, low: 0, lowPct: 0, tooFew: false });
  assert.deepEqual([by.good.n, by.good.tooFew, by.good.lowPct], [0, true, null]);
  assert.deepEqual([by.average.n, by.average.tooFew], [0, true]);
});

test("nextClassRisk: order of the input rows does not matter; the default floor is 20 pairs", () => {
  const shuffled = [...JOURNEY].reverse();
  const r = nextClassRisk(shuffled, REC);
  assert.equal(r.minPairs, 20);
  assert.equal(r.pairs, 4);
  assert.deepEqual(r.baseline, { n: 4, low: 2, lowPct: 50 });
  for (const b of r.bands) {
    assert.equal(b.tooFew, true, b.band);
    assert.equal(b.lowPct, null, b.band);
  }
  assert.equal(r.bands.find((b) => b.band === "excellent")!.n, 2);
});

// ── drift, slices, votes ──────────────────────────────────────────────────────
test("driftByMonth: one row per month, in order, with the study's monthly measures", () => {
  const rows = [
    row({ class_date: "2026-03-05", rating: 4.2, score: 40, band: "bad", attended: 10, yes_votes: 6, no_votes: 6, participation_pct: 30 }),
    row({ class_date: "2026-02-10", rating: 4.8, score: 92, band: "excellent", attended: 30, participation_pct: 40 }),
    row({ class_date: "2026-02-20", rating: 4.4, score: 70, band: "average", attended: 20, participation_pct: 50 }),
  ];
  const d = driftByMonth(rows);
  assert.deepEqual(
    d.map((m) => [m.month, m.label, m.n]),
    [
      ["2026-02", "Feb", 2],
      ["2026-03", "Mar", 1],
    ],
  );
  const feb = d[0];
  assert.ok(Math.abs(feb.avgRating! - 4.6) < 1e-9);
  assert.deepEqual([feb.underLinePct, feb.avgAttended, feb.avgReach, feb.avgScore, feb.badPct, feb.underBarPct], [50, 25, 45, 81, 0, 0]);
  const mar = d[1];
  assert.deepEqual([mar.underLinePct, mar.underBarPct, mar.badPct, mar.avgScore], [100, 100, 100, 40]);
});

test("slices: live vs review, region only when the rows carry one, weekday Monday-first", () => {
  assert.equal(weekdayOf("2026-03-02"), "Mon");
  assert.equal(weekdayOf("2026-03-08"), "Sun");
  const rows = [
    row({ class_date: "2026-03-02", session_kind: "Live Class", score: 90, band: "excellent", region: "IND" }),
    row({ class_date: "2026-03-02", session_kind: "Live Class", score: 70, band: "average", region: "US" }),
    row({ class_date: "2026-03-04", session_kind: "Test Review", score: 50, band: "bad", region: null, attended: null }),
  ];
  const s = slices(rows);
  assert.deepEqual(
    s.kind.map((k) => [k.label, k.n, k.avgScore, k.badPct]),
    [
      ["Live class", 2, 80, 0],
      ["Test review", 1, 50, 100],
    ],
  );
  assert.deepEqual(s.region!.map((k) => [k.label, k.n, k.avgScore]), [
    ["India", 1, 90],
    ["US", 1, 70],
  ]);
  assert.deepEqual(s.weekday.map((k) => [k.key, k.n]), [
    ["Mon", 2],
    ["Wed", 1],
  ]);
  assert.equal(s.kind[1].avgAttended, null);
  assert.equal(slices(rows.map((r) => ({ ...r, region: null }))).region, null);
});

test("trustByVotes: bands by vote bucket and the provisional share", () => {
  const rows = [
    row({ yes_votes: 1, no_votes: 0, num_ratings: 1, band: null }),
    row({ yes_votes: 4, no_votes: 0, num_ratings: 4, band: "good", provisional: true }),
    row({ yes_votes: null, no_votes: null, num_ratings: 7, band: "good" }),
    row({ yes_votes: 12, no_votes: 0, band: "excellent" }),
    row({ yes_votes: 6, no_votes: 6, band: "bad" }),
  ];
  const t = trustByVotes(rows);
  assert.deepEqual(t.buckets.map((b) => [b.key, b.n]), [
    ["0-2", 1],
    ["3-5", 1],
    ["6-9", 1],
    ["10+", 2],
  ]);
  assert.deepEqual(t.buckets[0].counts, { excellent: 0, good: 0, average: 0, bad: 0, none: 1 });
  assert.deepEqual([t.buckets[1].provisional, t.buckets[1].provisionalPct], [1, 100]);
  assert.deepEqual(t.buckets[3].counts, { excellent: 1, good: 0, average: 0, bad: 1, none: 0 });
  assert.deepEqual([t.n, t.banded, t.provisional, t.provisionalPct, t.noBand, t.noBandPct], [5, 4, 1, 20, 1, 20]);
});
