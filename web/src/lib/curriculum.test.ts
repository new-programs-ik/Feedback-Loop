import { test } from "node:test";
import assert from "node:assert/strict";
import {
  attendanceJourney,
  buildCurriculumMap,
  fmtSigned,
  instructorModuleFit,
  moduleFixers,
  ratingBand,
  ratioBand,
  reachBand,
  shortCohortName,
  shortModuleName,
  type CohortRefLike,
  type CurriculumRow,
} from "./curriculum.ts";

/** A synthetic course: seven cohorts on two tracks, seven modules, one deliberate attendance
 *  drop (Agents), one instructor who rates high on that weak module (the fixer), a cohort with a
 *  live + review on one module, a cohort that took two modules out of order, and a cohort still
 *  running. Every name is made up. Run with `npm test`. */

const ASOF = "2026-07-27";
const MODULES = [
  { id: "m1", name: "Foundations" },
  { id: "m2", name: "Prompting" },
  { id: "m3", name: "Retrieval" },
  { id: "m4", name: "Agents" },
  { id: "m5", name: "Evaluation" },
  { id: "m6", name: "SWE : Deployment" }, // SWE track only
  { id: "m7", name: "PM : Capstone" }, // PM track only
];
const COHORTS: { key: string; name: string; start: string; audience: string; room: number; no: number }[] = [
  { key: "c1", name: "Cohort 1, Jan", start: "2026-01-05", audience: "swe", room: 40, no: 1 },
  { key: "c2", name: "Cohort 2, Feb", start: "2026-02-02", audience: "swe", room: 44, no: 2 },
  { key: "c3", name: "Cohort 3, Mar", start: "2026-03-02", audience: "swe", room: 38, no: 3 },
  { key: "c4", name: "Cohort 4, Apr", start: "2026-04-06", audience: "swe", room: 50, no: 4 },
  { key: "c5", name: "Cohort 5, May", start: "2026-05-04", audience: "swe", room: 42, no: 5 },
  { key: "c6", name: "Cohort 6, Jun", start: "2026-06-01", audience: "pm", room: 36, no: 6 },
  { key: "c7", name: "Cohort 7, Jul", start: "2026-07-06", audience: "pm", room: 30, no: 7 },
];
const ALPHA = "Alpha Teacher";
const BETA = "Beta Teacher";
const GAMMA = "Gamma Teacher";

const addDays = (d: string, n: number) => new Date(+new Date(d + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);

const refs = new Map<string, CohortRefLike>();
const refByRow = new Map<string, CohortRefLike>();
const rows: CurriculumRow[] = [];

function row(cohort: (typeof COHORTS)[number], mod: (typeof MODULES)[number], week: number, kind: string, instructor: string, rating: number, attended: number, rated: number): CurriculumRow {
  const r: CurriculumRow = {
    id: `${cohort.key}-${mod.id}-${kind === "Live Class" ? "live" : "review"}`,
    topic: mod.name,
    topic_id: mod.id,
    class_date: addDays(cohort.start, (week - 1) * 7 + (kind === "Live Class" ? 0 : 1)),
    session_kind: kind,
    rating,
    num_ratings: rated,
    attended,
    participation_pct: (rated / attended) * 100,
    week_no: week,
    instructor,
    instructor_id: null,
    instructor_canonical: null,
    score: rating >= 4.55 ? 80 : 65,
    band: rating >= 4.55 ? "good" : "average",
  };
  rows.push(r);
  refByRow.set(r.id, refs.get(cohort.key)!);
  return r;
}

for (const c of COHORTS) refs.set(c.key, { key: c.key, name: c.name, start: c.start.slice(0, 7), region: "IND", audience: c.audience, cohortNo: c.no });

const AGENTS: Record<string, [string, number]> = { c1: [ALPHA, 4.3], c2: [ALPHA, 4.3], c3: [GAMMA, 4.8], c4: [ALPHA, 4.25], c5: [GAMMA, 4.85], c6: [BETA, 4.35] };
const BASE_RATING = [4.7, 4.72, 4.68, 0, 4.65, 4.75, 4.75];

for (const c of COHORTS) {
  const swe = c.audience === "swe";
  const taken = c.key === "c7" ? MODULES.slice(0, 3) : swe ? MODULES.slice(0, 6) : [...MODULES.slice(0, 5), MODULES[6]];
  let att = c.room;
  let agentsRoom = 0;
  taken.forEach((mod) => {
    const idx = MODULES.indexOf(mod);
    // Attendance drifts down one a module, and falls 25% at Agents in every SWE cohort.
    if (idx === 3) att = swe ? Math.round(att * 0.75) : att;
    else if (idx === 4) att = agentsRoom - 1;
    else if (idx >= 5) att = agentsRoom - 2;
    else att = c.room - idx;
    if (idx === 3) agentsRoom = att;
    // Cohort 3 took Retrieval before Prompting.
    let week = idx + 1;
    if (c.key === "c3" && idx === 1) week = 3;
    if (c.key === "c3" && idx === 2) week = 2;
    const teacher = idx === 3 ? AGENTS[c.key][0] : c.no % 2 ? ALPHA : BETA;
    const rating = idx === 3 ? AGENTS[c.key][1] : BASE_RATING[idx];
    row(c, mod, week, "Live Class", teacher, rating, att, Math.round(att * 0.5));
    // Cohort 2 also had a test review on Prompting: a second, thinner session on the same module.
    if (c.key === "c2" && idx === 1) row(c, mod, week, "Test Review", teacher, 4.6, 30, 12);
    // The PM capstone has been taught to one cohort so far, live and reviewed (two classes).
    if (c.key === "c6" && idx === 6) row(c, mod, week, "Test Review", teacher, 4.7, att - 4, Math.round((att - 4) * 0.5));
  });
}
// A generic sheet label with no module name: counts as a class, never as a module.
rows.push({ ...rows[0], id: "c1-generic", topic: "Live Class", topic_id: null, class_date: addDays("2026-01-05", 3), week_no: 1 });
refByRow.set("c1-generic", refs.get("c1")!);

const refsOf = (r: CurriculumRow) => [refByRow.get(r.id)!];
const build = (track?: string) => buildCurriculumMap(rows, { refsOf, track, asOf: ASOF, links: { module: (k) => `/m/${k}`, instructor: (k) => `/i/${encodeURIComponent(k)}` } });

test("tracks: the biggest track is the default, 'all' is the union, a track shows only its modules", () => {
  const def = build();
  assert.deepEqual(def.tracks.map((t) => [t.track, t.label, t.cohorts]), [["swe", "SWE", 5], ["pm", "PM", 2]]);
  assert.equal(def.track, "swe");
  assert.equal(def.cohorts.length, 5);
  assert.ok(!def.modules.some((m) => m.name === "PM : Capstone"), "a SWE cohort never sees the PM capstone");

  const pm = build("pm");
  assert.equal(pm.cohorts.length, 2);
  assert.deepEqual(pm.modules.map((m) => m.name), ["Foundations", "Prompting", "Retrieval", "Agents", "Evaluation", "PM : Capstone"]);

  const all = build("all");
  assert.equal(all.cohorts.length, 7);
  assert.deepEqual(all.modules.map((m) => m.name), ["Foundations", "Prompting", "Retrieval", "Agents", "Evaluation", "SWE : Deployment", "PM : Capstone"]);
  assert.equal(build("nope").track, "all", "an unknown track in the URL falls back to everything");
});

test("modules sit in median-week order with W labels, even when one cohort took two out of order", () => {
  const map = build("all");
  assert.deepEqual(map.modules.map((m) => m.order), [1, 2, 3, 4, 5, 6, 7]);
  assert.equal(map.modules[1].short, "Prompting");
  assert.equal(map.modules[5].short, "Deployment", "the track prefix is stripped from the short name");
  const c3 = map.cohorts.find((c) => c.key === "c3")!;
  assert.ok(c3.cells.m3.dates[0] < c3.cells.m2.dates[0], "cohort 3 really took Retrieval first");
});

test("cohorts come most recent first; a running cohort has empty cells to the right, not zeros", () => {
  const map = build("all");
  assert.equal(map.cohorts[0].key, "c7");
  assert.equal(map.cohorts[map.cohorts.length - 1].key, "c1");
  const c7 = map.cohorts[0];
  assert.deepEqual(Object.keys(c7.cells).sort(), ["m1", "m2", "m3"]);
  assert.equal(c7.cells.m4, undefined);
  assert.equal(c7.active, true);
  assert.equal(c7.lastOrder, 2);
  assert.ok(Math.abs(c7.retention! - 28 / 30) < 1e-9, "retention so far: the third module's room over the first's");
  assert.equal(map.cohorts.find((c) => c.key === "c1")!.active, false);
});

test("a live class and a test review on one module become one cell: rating = mean, attended = the fuller room, live opens first", () => {
  const c2 = build("all").cohorts.find((c) => c.key === "c2")!;
  const cell = c2.cells.m2;
  assert.equal(cell.classIds.length, 2);
  assert.equal(cell.classIds[0], "c2-m2-live");
  assert.deepEqual(cell.kinds, ["Live Class", "Test Review"]);
  assert.equal(cell.attended, 43);
  assert.equal(cell.rated, 22);
  assert.ok(Math.abs(cell.rating! - (4.72 + 4.6) / 2) < 1e-9);
});

test("retention and size read the cohort's first and last module rooms", () => {
  const c1 = build("all").cohorts.find((c) => c.key === "c1")!;
  assert.equal(c1.size, 40);
  assert.equal(c1.firstAttended, 40);
  assert.equal(c1.lastAttended, 27);
  assert.ok(Math.abs(c1.retention! - 27 / 40) < 1e-9);
  assert.equal(c1.n, 7, "the generic-label class counts as a class");
  assert.equal(Object.keys(c1.cells).length, 6, "but never as a module");
});

test("the attendance drop lands on Agents, measured against each cohort's previous module", () => {
  const agents = build("all").modules.find((m) => m.name === "Agents")!;
  assert.equal(agents.dropPairs, 6, "six cohorts have both Retrieval and Agents");
  assert.equal(agents.dropFell, 5, "the PM cohort held its room");
  assert.ok(agents.dropAttended! < -18 && agents.dropAttended! > -23, `mean drop ${agents.dropAttended}`);
  assert.equal(agents.prevName, "Retrieval");
  const evaluation = build("all").modules.find((m) => m.name === "Evaluation")!;
  assert.ok(evaluation.dropAttended! > -5, "after the drop the room only drifts");
});

test("the fixer: the highest-rated instructor with two classes on the weak module, only when others taught it too", () => {
  const map = build("all");
  const agents = map.modules.find((m) => m.name === "Agents")!;
  assert.ok(Math.abs(agents.avgRating! - 4.475) < 1e-9);
  assert.equal(agents.bestInstructor?.name, GAMMA);
  assert.equal(agents.bestInstructor?.n, 2);
  assert.equal(agents.underLine, 4);
  const foundations = map.modules.find((m) => m.name === "Foundations")!;
  assert.equal(foundations.instructors.length, 2);
  assert.ok(foundations.bestInstructor, "two instructors with repeat classes → a best one exists");
});

test("the sentences a PM reads", () => {
  const map = build("all");
  const kinds = map.insights.map((i) => i.kind);
  assert.deepEqual(kinds, ["attendance_drop", "rating_dip", "consistent_low", "fixer"]);
  const [drop, dip, low, fixer] = map.insights;
  assert.match(drop.title, /^Attendance falls most at \*\*Agents\*\*: −\d+% against the module before it, in 5 of 6 cohorts$/);
  assert.match(drop.detail, /^After Retrieval — the room goes from \d+ to \d+ on average\.$/);
  assert.match(dip.title, /^The rating dips most at \*\*Agents\*\*: 4\.48 against the course's 4\.\d\d$/);
  assert.match(dip.detail, /6 classes across 6 cohorts · 3 instructors have taught it · −0\.\d\d from Retrieval just before it\./);
  assert.equal(low.title, "**Agents** is under the 4.55 line in 4 of 6 cohorts");
  assert.match(low.detail, /^3 different instructors taught it/);
  assert.equal(fixer.title, `**${GAMMA}** teaches Agents above its average: ${((4.8 + 4.85) / 2).toFixed(2)} across 2 classes (module average 4.48)`);
  assert.match(fixer.detail, /^The other 2 instructors average 4\.32 on it\.$/);
  assert.equal(fixer.href, `/i/${encodeURIComponent(`name:${GAMMA}`)}`);
  assert.equal(dip.href, "/m/m4");
  for (const i of map.insights) console.log(`  · ${i.title.replace(/\*\*/g, "")} — ${i.detail}`);
});

test("the journeys: median attendance dips at Agents; weeks run to at least W14", () => {
  const map = build("all");
  const j = attendanceJourney(map.cohorts, map.modules);
  assert.deepEqual(j.byModule.labels.slice(0, 4), ["Foundations", "Prompting", "Retrieval", "Agents"]);
  assert.deepEqual(j.byModule.notes.slice(0, 2), ["W1", "W2"]);
  assert.ok(j.byModule.median.attended[3]! < j.byModule.median.attended[2]!);
  assert.equal(j.byModule.cohorts.length, 7);
  assert.equal(j.byModule.cohorts[0].attended[3], null, "cohort 7 has not reached Agents");
  assert.ok(j.byWeek.labels.length >= 14);
  assert.equal(j.byWeek.labels[0], "W1");
  assert.ok(j.byWeek.cohorts.every((c) => c.attended.length === j.byWeek.labels.length));
});

test("moduleFixers ranks instructors on a module and names who lifts and who struggles", () => {
  const agents = rows.filter((r) => r.topic_id === "m4");
  const f = moduleFixers({ rows: agents });
  assert.deepEqual(f.lifts.map((i) => i.name), [GAMMA]);
  assert.deepEqual(f.struggles.map((i) => i.name), [ALPHA]);
  assert.equal(f.instructors[0].name, GAMMA);
  assert.equal(f.instructors.find((i) => i.name === BETA)?.verdict, null, "one class is not enough for a verdict");
});

test("instructorModuleFit: Gamma lifts Agents; Alpha struggles with it and is fine elsewhere", () => {
  const gamma = instructorModuleFit(rows.filter((r) => r.instructor === GAMMA), rows);
  assert.deepEqual(gamma.lifts.map((m) => m.name), ["Agents"]);
  assert.equal(gamma.struggles.length, 0);
  const alpha = instructorModuleFit(rows.filter((r) => r.instructor === ALPHA), rows);
  assert.deepEqual(alpha.struggles.map((m) => m.name), ["Agents"]);
  assert.ok(alpha.all.every((m) => m.moduleN >= 2));
});

test("tint bands and formatting helpers", () => {
  assert.deepEqual([4.9, 4.6, 4.4, 4.2, 0, null].map(ratingBand), ["excellent", "good", "average", "bad", null, null]);
  assert.deepEqual([70, 45, 30, 10].map(reachBand), ["excellent", "good", "average", "bad"]);
  assert.deepEqual([1, 0.8, 0.65, 0.5].map(ratioBand), ["excellent", "good", "average", "bad"]);
  assert.equal(shortModuleName("SWE : Retrieval-Augmented Generation"), "Retrieval-Augme…");
  assert.equal(shortModuleName("Agents"), "Agents");
  assert.equal(shortCohortName({ key: "x", name: "Applied AI - March 2026 : Cohort 2, India", start: "Mid Mar 2026", region: "IND", audience: null, cohortNo: 2 }), "C2 · Mid Mar 2026 · IND");
  assert.equal(fmtSigned(-0.304), "−0.30");
  assert.equal(fmtSigned(0.001), "0.00");
  assert.equal(fmtSigned(-18.4, 0, "%"), "−18%");
});
