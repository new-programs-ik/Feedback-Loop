/**
 * seed-catalog.mjs — seed the snapshot from the Cohort planning sheet (interim, demo-only).
 * Adds the course, its instructors, and its planned classes (topic → instructor).
 * Safe to re-run (upserts by name). Uses the service key (bypasses RLS).
 *
 *   node scripts/seed-catalog.mjs
 */
import { createClient } from "@supabase/supabase-js";
import { readFileSync } from "node:fs";

const env = {};
for (const l of readFileSync(new URL("../.env.local", import.meta.url), "utf8").split(/\r?\n/)) {
  const t = l.trim();
  if (t && !t.startsWith("#") && t.includes("=")) {
    const i = t.indexOf("=");
    env[t.slice(0, i).trim()] = t.slice(i + 1).trim();
  }
}
const s = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
});

const COURSE = "LLM Ops & AI System Design";
const CLASSES = [
  ["Introduction to Machine Learning", "Deekshant"],
  ["Ensemble Methods", "Manoj"],
  ["ML Architectures", "Sanatan"],
  ["Build a conversational chatbot", "Justin Joseph"],
  ["Workshop - 4: Conversational Audio Bot Project (Live Guided) - Saturday", "Justin Joseph"],
];

function slug(x) {
  return x.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

async function ensure(table, match, insert) {
  const f = await s.from(table).select("id").match(match).maybeSingle();
  if (f.data) return f.data.id;
  const ins = await s.from(table).insert(insert).select("id").single();
  if (ins.error) throw new Error(`${table}: ${ins.error.message}`);
  return ins.data.id;
}

const courseId = await ensure("courses", { name: COURSE }, { name: COURSE, slug: slug(COURSE) });
console.log("course:", COURSE, courseId);

for (const [topic, instructor] of CLASSES) {
  const instructorId = await ensure("instructors", { name: instructor }, { name: instructor });
  const up = await s
    .from("class_catalog")
    .upsert({ course_id: courseId, topic, instructor_id: instructorId }, { onConflict: "course_id,topic" });
  if (up.error) throw new Error(`class_catalog "${topic}": ${up.error.message}`);
  console.log(`  ✓ ${topic}  →  ${instructor}`);
}
console.log("done — seeded", CLASSES.length, "classes.");
