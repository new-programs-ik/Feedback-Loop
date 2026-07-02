/**
 * test-feedback-flow.mjs — end-to-end test of the Feedback pipeline (B2), mirroring the
 * server action: sign in as admin → call the worker → store under RLS → read back.
 * Requires the worker running on :8000 and a real ANTHROPIC_API_KEY (in the worker's env).
 *
 *   node scripts/test-feedback-flow.mjs
 */
import { createClient } from "@supabase/supabase-js";
import { readFileSync } from "node:fs";

function loadEnv(rel) {
  const env = {};
  for (const line of readFileSync(new URL(rel, import.meta.url), "utf8").split(/\r?\n/)) {
    const t = line.trim();
    if (t && !t.startsWith("#") && t.includes("=")) {
      const i = t.indexOf("=");
      env[t.slice(0, i).trim()] = t.slice(i + 1).trim();
    }
  }
  return env;
}

const web = loadEnv("../.env.local");
const sampleVtt = readFileSync(new URL("../../ratings_module_build_kit/sample_transcript.vtt", import.meta.url), "utf8");
const WORKER = "http://localhost:8000";
const EMAIL = "new-programs@interviewkickstart.com";
const PASS = "IK-np-admin-2026";

const supa = createClient(web.NEXT_PUBLIC_SUPABASE_URL, web.NEXT_PUBLIC_SUPABASE_ANON_KEY);
const { error: signErr } = await supa.auth.signInWithPassword({ email: EMAIL, password: PASS });
if (signErr) throw new Error("sign-in failed: " + signErr.message);
const { data: { user } } = await supa.auth.getUser();

const { data: course } = await supa.from("courses").select("id,name").eq("name", "Advanced ML").single();

const r = await fetch(`${WORKER}/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    transcript: sampleVtt, course: course.name, topic: "Decision Trees (sample)",
    instructor: "Justin", rating: "4.2", agenda: "Trees; Gini; Random forests; Gradient boosting",
  }),
});
if (!r.ok) throw new Error(`worker /analyze ${r.status}: ${await r.text()}`);
const { result, meta, transcript_used } = await r.json();
console.log(`worker OK — reclass=${result.reclass.recommended}  flags=${result.flags.length}  $${meta.cost_usd}`);

async function ensure(table, match, insert) {
  const f = await supa.from(table).select("id").match(match).maybeSingle();
  if (f.data) return f.data.id;
  const ins = await supa.from(table).insert(insert).select("id").single();
  if (ins.error) throw new Error(`${table} insert (RLS) failed: ${ins.error.message}`);
  return ins.data.id;
}
const instructor_id = await ensure("instructors", { name: "Justin" }, { name: "Justin" });
const cohort_id = await ensure("cohorts", { course_id: course.id, name: "Sample Cohort" }, { course_id: course.id, name: "Sample Cohort" });

const cls = await supa.from("classes").insert({
  course_id: course.id, cohort_id, instructor_id, topic: "Decision Trees (sample)",
  class_date: "2026-07-01", rating: 4.2, num_ratings: 18, status: "analyzing", created_by: user.id,
}).select("id").single();
if (cls.error) throw new Error("classes insert (RLS) failed: " + cls.error.message);
const classId = cls.data.id;

await supa.from("transcripts").insert({ class_id: classId, content: transcript_used, format: "vtt", source: "upload" });
const an = await supa.from("analyses").insert({
  class_id: classId, model: meta.model, result,
  reclass: result.reclass.recommended, reclass_reason: result.reclass.reason,
  tokens_in: meta.tokens_in, tokens_out: meta.tokens_out, cost_usd: meta.cost_usd,
}).select("id").single();
if (an.error) throw new Error("analyses insert (RLS) failed: " + an.error.message);
await supa.from("feedback").insert({ class_id: classId, analysis_id: an.data.id, draft_text: result.feedback, status: "draft" });
await supa.from("classes").update({ status: "draft_ready" }).eq("id", classId);
await supa.from("audit_log").insert({ class_id: classId, actor_id: user.id, action: "analyzed", detail: { cost_usd: meta.cost_usd } });

const { data: back } = await supa
  .from("classes")
  .select("topic,status,rating,courses(name),instructors(name),analyses(reclass),feedback(status,draft_text)")
  .eq("id", classId).single();
console.log(`stored & read back via RLS: "${back.topic}" status=${back.status} course=${back.courses.name} instructor=${back.instructors.name}`);
console.log(`  reclass=${back.analyses[0].reclass}  feedback=${back.feedback[0].status}  draft=${back.feedback[0].draft_text.length} chars`);
await supa.auth.signOut();
console.log("✅ B2 end-to-end OK (analyze → store under RLS → read back)");
