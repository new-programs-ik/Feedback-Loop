"use client";

import { useActionState, useState } from "react";
import { createAnalysis, type AnalyzeState } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Clapperboard, FileText, Loader2, Paperclip } from "lucide-react";
import {
  APPROVAL_BAR, BORDERLINE, GOOD, MIN_VOICES, PARTICIPATION_BAR, URGENT, decide, decideV2, explain, explainV2,
  voteLabel, type HealthBand,
} from "@/lib/decision";
import { PriorityChip } from "@/components/priority-chip";

const label = "text-sm font-medium";
const field =
  "border-input flex h-9 w-full rounded-md border bg-card px-3 py-1 text-sm shadow-sm outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring";

const prettyDate = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

function Section({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="text-primary size-4" />
        <span className="text-sm font-semibold">{title}</span>
        {hint && <span className="text-muted-foreground text-xs">{hint}</span>}
      </div>
      <div className="space-y-4 pl-6">{children}</div>
    </section>
  );
}

export type Prefill = {
  classRatingId: string;
  courseId: string;
  topic: string;
  instructor: string;
  classDate: string;
  classType: "live_class" | "ars";
  rating: string;
  numRatings: string;
  attended: string;
  yesVotes: string;
  noVotes: string;
  trackAvg: number | null;
  healthScore: number | null;
  healthBand: HealthBand | null;
  escalated: boolean;
  video: boolean;
};

export function NewAnalysisForm({
  courses,
  instructorNames,
  prefill,
}: {
  courses: { id: string; name: string }[];
  instructorNames: string[];
  prefill?: Prefill;
}) {
  const [state, formAction, pending] = useActionState<AnalyzeState, FormData>(createAnalysis, {});
  const [courseId, setCourseId] = useState(prefill?.courseId ?? "");
  const [classType, setClassType] = useState<"live_class" | "ars">(prefill?.classType ?? "live_class");
  const [source, setSource] = useState<"vimeo" | "upload">("vimeo");
  const [analyzeVideo, setAnalyzeVideo] = useState(prefill?.video ?? false);
  // "Which analysis?" helper (the team's decision rules, built in) — a queue prefill
  // lights it up so the recommendation is visible immediately.
  const [hRating, setHRating] = useState(prefill?.rating ?? "");
  const [hAttended, setHAttended] = useState(prefill?.attended ?? "");
  const [hRated, setHRated] = useState(prefill?.numRatings ?? "");
  const [hYes, setHYes] = useState(prefill?.yesVotes ?? "");
  const [hNo, setHNo] = useState(prefill?.noVotes ?? "");
  const [hEscalation, setHEscalation] = useState(prefill?.escalated ?? false);
  const r = parseFloat(hRating);
  const att = parseInt(hAttended, 10);
  const yes = parseInt(hYes, 10);
  const no = parseInt(hNo, 10);
  const hasVote = !Number.isNaN(yes) && !Number.isNaN(no) && yes + no > 0;
  // Yes + No equals the number of ratings on every sheet row, so the vote can stand in for it.
  const typedRated = parseInt(hRated, 10);
  const rat = !Number.isNaN(typedRated) ? typedRated : hasVote ? yes + no : NaN;
  const participation = att > 0 && rat >= 0 ? Math.round((rat / att) * 100) : null;
  // The team rule lives in ONE place — src/lib/decision.ts (mirrored by the sync worker's
  // decision.py). This helper only translates the verdict into form advice.
  let advice: {
    title: string; detail: string; video: boolean | null; band?: HealthBand | null; score?: number | null;
  } | null = null;
  if (hEscalation) {
    advice = { title: "Video Analysis", detail: "There is an escalation — always use video for escalated classes.", video: true };
  } else if (!Number.isNaN(r)) {
    if (hasVote) {
      const input = {
        rating: r,
        numRatings: Number.isNaN(rat) ? null : rat,
        attended: att > 0 ? att : null,
        yesVotes: yes,
        noVotes: no,
        trackAvg: prefill?.trackAvg ?? null,
      };
      const v = decideV2(input);
      const title =
        v.decision === "none" ? "No analysis needed"
        : v.decision === "watch" ? "Watch only"
        : v.decision === "video" ? "Video Analysis"
        : "Transcript Analysis";
      advice = {
        title,
        detail: explainV2(v, input),
        video: v.decision === "none" ? false : v.decision === "watch" ? null : v.decision === "video",
        band: v.healthBand,
        score: v.healthScore,
      };
    } else if (r >= GOOD) {
      advice = { title: "No analysis needed", detail: explain("none", participation, rat), video: false };
    } else if (participation != null) {
      const d = decide(r, rat, att);
      advice =
        d === "watch"
          ? { title: "Watch only", detail: explain(d, participation, rat), video: null }
          : d === "video"
            ? { title: "Video Analysis", detail: explain(d, participation, rat), video: true }
            : { title: "Transcript Analysis", detail: explain(d, participation, rat), video: false };
    } else {
      advice = { title: "Almost there", detail: "Fill in attended + rated counts to get the recommendation.", video: null };
    }
  }
  const prefillVote = prefill ? voteLabel(parseInt(prefill.yesVotes, 10), parseInt(prefill.noVotes, 10)) : null;

  return (
    <Card className="shadow-soft max-w-2xl">
      <CardHeader>
        <CardTitle>Class details</CardTitle>
        <CardDescription>
          Fill in the class, attach the recording (and optionally the materials), then analyze.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form action={formAction} className="space-y-7">
          {prefill && <input type="hidden" name="class_rating_id" value={prefill.classRatingId} />}
          {prefill && (
            <div className="bg-card flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border px-4 py-3 text-sm">
              <span className="font-semibold">From the queue:</span>
              <span className="text-muted-foreground min-w-0 truncate">
                {prefill.topic} · {prettyDate(prefill.classDate)}
              </span>
              <span data-numeric>
                rated <b className="font-semibold">{prefill.rating}</b>
              </span>
              <span data-numeric>
                {prefillVote ? (
                  <>
                    <b className="font-semibold">{prefillVote}</b>{" "}
                    <span className="text-muted-foreground">would have the instructor back</span>
                  </>
                ) : (
                  <span className="text-muted-foreground">no vote recorded</span>
                )}
              </span>
              <PriorityChip band={prefill.healthBand} score={prefill.healthScore} />
            </div>
          )}
          <div className="bg-accent/40 space-y-3 rounded-xl border p-4">
            <div className="text-sm font-semibold">🧭 Not sure which analysis? Answer a few things:</div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <label className="text-muted-foreground text-xs font-medium">Class rating</label>
                <input type="number" step="0.01" min="0" max="5" value={hRating}
                       onChange={(e) => setHRating(e.target.value)} placeholder="4.3" className={field} />
              </div>
              <div className="space-y-1">
                <label className="text-muted-foreground text-xs font-medium">Learners attended</label>
                <input type="number" min="0" value={hAttended}
                       onChange={(e) => setHAttended(e.target.value)} placeholder="10" className={field} />
              </div>
              <div className="space-y-1">
                <label className="text-muted-foreground text-xs font-medium">Learners who rated</label>
                <input type="number" min="0" value={hRated}
                       onChange={(e) => setHRated(e.target.value)} placeholder="8" className={field} />
              </div>
              <div className="space-y-1">
                <label className="text-muted-foreground text-xs font-medium">Would have them back — Yes</label>
                <input type="number" min="0" value={hYes}
                       onChange={(e) => setHYes(e.target.value)} placeholder="7" className={field} />
              </div>
              <div className="space-y-1">
                <label className="text-muted-foreground text-xs font-medium">Would have them back — No</label>
                <input type="number" min="0" value={hNo}
                       onChange={(e) => setHNo(e.target.value)} placeholder="1" className={field} />
              </div>
              <label className="flex items-end gap-2 pb-2 text-sm">
                <input type="checkbox" checked={hEscalation} onChange={(e) => setHEscalation(e.target.checked)} />
                Escalation reported
              </label>
            </div>
            {advice && (
              <div className="bg-card flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
                <div className="text-sm">
                  <span className="font-semibold">{advice.title}</span>
                  {advice.band && <PriorityChip band={advice.band} score={advice.score} className="ml-2 align-middle" />}
                  <span className="text-muted-foreground"> — {advice.detail}</span>
                </div>
                {advice.video != null && advice.title !== "No analysis needed" && (
                  <Button type="button" size="sm" variant={advice.video === analyzeVideo ? "outline" : "default"}
                          onClick={() => setAnalyzeVideo(advice.video === true)}>
                    {advice.video === analyzeVideo ? "Applied ✓" : advice.video ? "Turn video ON" : "Keep transcript only"}
                  </Button>
                )}
              </div>
            )}
            <p className="text-muted-foreground text-xs">
              Team rule: below {GOOD}, or under {APPROVAL_BAR}% would have the instructor back → needs a look ·
              fewer than {MIN_VOICES} ratings → watch only · Health Score under {URGENT} → urgent, video ·{" "}
              {BORDERLINE}+ → borderline, transcript first · in between, ≥ {PARTICIPATION_BAR}% of attendees rating → video,
              under → transcript · any escalation → video.
            </p>
          </div>

          <Section icon={FileText} title="The class">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label htmlFor="course_id" className={label}>Course</label>
                <select
                  id="course_id" name="course_id" required className={field}
                  value={courseId} onChange={(e) => setCourseId(e.target.value)}
                >
                  <option value="" disabled>Select a course…</option>
                  {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  <option value="__other__">➕ Other — add a new course…</option>
                </select>
                {courseId === "__other__" && (
                  <input name="new_course" required className={field} placeholder="New course name (e.g. B2B)" />
                )}
              </div>
              <div className="space-y-1.5">
                <label htmlFor="topic" className={label}>Class topic</label>
                <input id="topic" name="topic" required className={field} placeholder="e.g. Decision Trees & Ensembles"
                       defaultValue={prefill?.topic} />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="instructor" className={label}>Instructor</label>
                <input id="instructor" name="instructor" list="instructor-options" className={field}
                       placeholder="Type or pick a name" defaultValue={prefill?.instructor} />
                <datalist id="instructor-options">
                  {instructorNames.map((n) => <option key={n} value={n} />)}
                </datalist>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="class_date" className={label}>Class date</label>
                <input id="class_date" name="class_date" type="date" required className={field}
                       defaultValue={prefill?.classDate} />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="class_type" className={label}>Class type</label>
                <select id="class_type" name="class_type" className={field} value={classType}
                        onChange={(e) => setClassType(e.target.value as "live_class" | "ars")}>
                  <option value="live_class">Live class</option>
                  <option value="ars">Assignment review (ARS)</option>
                </select>
                <p className="text-muted-foreground text-xs">Each type has its own checklist.</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label htmlFor="rating" className={label}>Avg rating</label>
                  <Input id="rating" name="rating" type="number" step="0.01" min="0" max="5" placeholder="4.2"
                         defaultValue={prefill?.rating} />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="num_ratings" className={label}># ratings</label>
                  <Input id="num_ratings" name="num_ratings" type="number" min="0" placeholder="18"
                         defaultValue={prefill?.numRatings} />
                </div>
              </div>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="agenda" className={label}>Class agenda (planned items)</label>
              <textarea id="agenda" name="agenda" rows={3} className={field + " h-auto py-2"}
                        placeholder="Paste the planned agenda — helps judge coverage & pacing." />
            </div>
          </Section>

          <Section icon={Clapperboard} title="The recording">
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" name="source" checked={source === "vimeo"} onChange={() => setSource("vimeo")} />
                Vimeo link
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="source" checked={source === "upload"} onChange={() => setSource("upload")} />
                Upload .vtt / .srt
              </label>
            </div>
            {source === "vimeo" ? (
              <Input name="vimeo_url" type="url" placeholder="https://vimeo.com/123456789" />
            ) : (
              <Input name="file" type="file" accept=".vtt,.srt" className="file:mr-3 file:text-sm" />
            )}

            <div className="bg-muted/40 space-y-2 rounded-lg border p-3">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" name="analyze_video"
                       checked={analyzeVideo} onChange={(e) => setAnalyzeVideo(e.target.checked)} />
                🎬 Analyze the video too (recommended for important classes)
              </label>
              {analyzeVideo && (
                <Input name="video_url" type="url"
                       placeholder="Optional: direct mp4 / Google Drive link (Vimeo links work automatically)" />
              )}
              <p className="text-muted-foreground text-xs">
                Samples ~1 frame every 2–3 minutes to <strong>see</strong> the class — camera on, screen
                shared, slides vs the plan, real live coding. Adds ~$0.20–0.40 and ~5–10 min. Frames are
                analyzed in memory and <strong>never stored</strong>; if the video can&apos;t be read, the
                analysis continues transcript-only.
              </p>
            </div>
          </Section>

          <Section icon={Paperclip} title="Class materials" hint="optional — improves accuracy, costs more tokens">
            <Input id="materials" name="materials" type="file" multiple
                   accept=".pdf,.pptx,.docx,.txt,.md,.ipynb" className="file:mr-3 file:text-sm" />
            <input name="materials_url" type="url" className={field}
                   placeholder="…or paste a materials LINK (Google Drive / Docs / Slides)" />
            <textarea name="materials_text" rows={2} className={field + " h-auto py-2"}
                      placeholder="…or paste key materials/notes here." />
            <p className="text-muted-foreground text-xs">
              The AI checks the class against what was planned (coverage &amp; correctness). Uploads under
              ~4&nbsp;MB; links have no size limit (share &quot;Anyone with the link&quot;). Materials are used only
              for this analysis and <strong>never stored</strong>.
            </p>
          </Section>

          {state.error && (
            <p className="text-destructive bg-destructive/5 rounded-lg border border-current/20 px-3 py-2 text-sm">
              {state.error}
            </p>
          )}

          <div className="flex items-center gap-3 border-t pt-5">
            <Button type="submit" disabled={pending} className="min-w-32">
              {pending ? (<><Loader2 className="size-4 animate-spin" /> Starting…</>) : "Analyze class"}
            </Button>
            <span className="text-muted-foreground text-xs">
              Runs in the background — you&apos;ll land on the report page while it works.
            </span>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
