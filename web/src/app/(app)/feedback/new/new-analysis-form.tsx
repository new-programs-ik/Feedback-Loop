"use client";

import * as React from "react";
import { useActionState, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { createAnalysis, type AnalyzeState } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Reveal, EASE_OUT } from "@/components/motion/reveal";
import {
  Check, CircleDashed, Clapperboard, Eye, FileText, Loader2, Paperclip, Upload, type LucideIcon,
} from "lucide-react";
import { voteLabel } from "@/lib/decision";
import { ACTION_LABEL, BAND_META, BAND_ORDER, explainClass, scoreClass, type Action, type Band, type ScoreInputs, type ScoringConfig } from "@/lib/sentiment";
import { ScorePill } from "@/components/score/score-pill";
import { cn } from "@/lib/utils";

const label = "text-sm font-medium";
const field =
  "border-input flex h-9 w-full rounded-md border bg-card px-3 py-1 text-sm shadow-sm outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring";

const prettyDate = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

const fmtSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

const VERDICT_ICON: Record<string, LucideIcon> = {
  "Video Analysis": Clapperboard,
  "Transcript Analysis": FileText,
  "Watch only": Eye,
  "No analysis needed": Check,
  "Almost there": CircleDashed,
};

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
  /** The stored Class Sentiment Score of the class this form was opened from. */
  score: number | null;
  band: Band | null;
  action: Action | null;
  escalated: boolean;
  video: boolean;
};

const ACTION_TITLE: Record<Action, string> = {
  video: "Video Analysis",
  transcript: "Transcript Analysis",
  none: "No analysis needed",
  watch: "Watch only",
};

/** Drop zone for class materials. Files dropped on it are handed to the real <input type=file>
 *  (via DataTransfer) so the form posts exactly as before; the input stays focusable for
 *  keyboard users. Drag-over is a visible state, not just a cursor. */
function MaterialsDropZone() {
  const reduce = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<{ name: string; size: number }[]>([]);

  const readFiles = (list: FileList | null) => setFiles(Array.from(list ?? []).map((f) => ({ name: f.name, size: f.size })));
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!dragging) setDragging(true);
  };
  const onDragLeave = (e: React.DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    setDragging(false);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const input = inputRef.current;
    if (!input) return;
    const dt = new DataTransfer();
    for (const f of Array.from(e.dataTransfer.files)) dt.items.add(f);
    input.files = dt.files;
    readFiles(dt.files);
  };
  const clear = () => {
    if (inputRef.current) inputRef.current.value = "";
    setFiles([]);
  };

  return (
    <div className="space-y-2">
      <motion.label
        htmlFor="materials"
        onDragEnter={onDragOver}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        animate={{ scale: dragging && !reduce ? 1.01 : 1 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        className={cn(
          "focus-within:ring-ring flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed px-4 py-5 text-center transition-colors focus-within:ring-2",
          dragging ? "border-primary bg-primary/5" : "hover:bg-muted/40",
        )}
      >
        <span
          className={cn(
            "bg-muted text-muted-foreground flex size-9 items-center justify-center rounded-full transition-colors",
            dragging && "bg-primary/10 text-primary",
          )}
        >
          <Upload className="size-4" aria-hidden />
        </span>
        <span className="text-sm font-medium">{dragging ? "Drop to attach" : "Drop files here, or click to browse"}</span>
        <span className="text-muted-foreground text-xs">PDF, PPTX, DOCX, TXT, MD, IPYNB · keep the total under ~4 MB</span>
        <input
          ref={inputRef}
          id="materials"
          name="materials"
          type="file"
          multiple
          accept=".pdf,.pptx,.docx,.txt,.md,.ipynb"
          className="sr-only"
          onChange={(e) => readFiles(e.target.files)}
        />
      </motion.label>
      <AnimatePresence initial={false}>
        {files.length > 0 && (
          <motion.ul
            className="space-y-1 text-xs"
            initial={reduce ? false : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
          >
            {files.map((f) => (
              <li key={`${f.name}-${f.size}`} className="flex items-center gap-2">
                <FileText className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                <span className="min-w-0 truncate">{f.name}</span>
                <span className="text-muted-foreground shrink-0" data-numeric>{fmtSize(f.size)}</span>
              </li>
            ))}
            <li>
              <button type="button" onClick={clear} className="text-muted-foreground hover:text-foreground underline-offset-2 hover:underline">
                Clear files
              </button>
            </li>
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

export function NewAnalysisForm({
  courses,
  instructorNames,
  prefill,
  scoring,
}: {
  courses: { id: string; name: string }[];
  instructorNames: string[];
  prefill?: Prefill;
  /** The active scoring version — the helper scores what you type with the same rule as the queue. */
  scoring: { version: number | null; config: ScoringConfig };
}) {
  const reduce = useReducedMotion();
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

  // A failed start is loud (toast) AND persistent (inline, below the form).
  useEffect(() => {
    if (state.error) toast.error("Couldn't start the analysis", { description: state.error });
  }, [state]);

  const r = parseFloat(hRating);
  const att = parseInt(hAttended, 10);
  const yes = parseInt(hYes, 10);
  const no = parseInt(hNo, 10);
  const hasVote = !Number.isNaN(yes) && !Number.isNaN(no) && yes + no > 0;
  // Yes + No equals the number of ratings on every sheet row, so the vote can stand in for it.
  const typedRated = parseInt(hRated, 10);
  const rat = !Number.isNaN(typedRated) ? typedRated : hasVote ? yes + no : NaN;
  // The rule lives in ONE place — the scoring function in the database, mirrored by
  // src/lib/sentiment.ts and pinned to the same fixtures. This helper only translates the
  // verdict of the ACTIVE version into form advice, so it can never disagree with the queue.
  let advice: {
    title: string; detail: string; video: boolean | null; band?: Band | null; score?: number | null; provisional?: boolean;
  } | null = null;
  if (hEscalation) {
    advice = { title: "Video Analysis", detail: "There is an escalation — always use video for escalated classes.", video: true };
  } else if (!Number.isNaN(r)) {
    const inputs: ScoreInputs = {
      rating: r,
      num_ratings: Number.isNaN(rat) ? null : rat,
      attended: att > 0 ? att : null,
      yes_votes: hasVote ? yes : null,
      no_votes: hasVote ? no : null,
      escalated: false,
      track_avg: prefill?.trackAvg ?? null,
    };
    const res = scoreClass(inputs, scoring.config);
    advice = {
      title: ACTION_TITLE[res.action],
      detail: explainClass(inputs, res, scoring.config),
      video: res.action === "none" ? false : res.action === "watch" ? null : res.action === "video",
      band: res.band,
      score: res.score,
      provisional: res.provisional,
    };
  }
  const prefillVote = prefill ? voteLabel(parseInt(prefill.yesVotes, 10), parseInt(prefill.noVotes, 10)) : null;
  // The card re-animates only when the VERDICT changes — not on every keystroke that nudges
  // the explanation, which would flicker while you type.
  const verdictKey = advice ? `${advice.title}|${advice.band ?? ""}` : "none";
  const VerdictIcon = advice ? (VERDICT_ICON[advice.title] ?? CircleDashed) : CircleDashed;

  return (
    <Card className="shadow-soft">
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
            <Reveal>
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
                    <span className="text-muted-foreground">no approval answer recorded</span>
                  )}
                </span>
                <ScorePill variant="sm" score={prefill.score} band={prefill.band} action={prefill.action ?? undefined} />
              </div>
            </Reveal>
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
            {/* height reserved so the card never jumps the rest of the form around */}
            <div className={cn("relative", advice ? "min-h-14" : "min-h-0")}>
              <AnimatePresence mode="wait" initial={false}>
                {advice && (
                  <motion.div
                    key={verdictKey}
                    initial={reduce ? false : { opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduce ? undefined : { opacity: 0, y: -4 }}
                    transition={{ duration: 0.22, ease: EASE_OUT }}
                    className="bg-card flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
                    aria-live="polite"
                  >
                    <div className="flex min-w-0 items-start gap-2.5 text-sm">
                      <span
                        className={cn(
                          "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
                          advice.video === true ? "bg-destructive/10 text-destructive"
                          : advice.title === "No analysis needed" ? "bg-success/10 text-success"
                          : advice.title === "Transcript Analysis" ? "bg-warning/15 text-warning"
                          : "bg-muted text-muted-foreground",
                        )}
                      >
                        <VerdictIcon className="size-3.5" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <span className="font-semibold">{advice.title}</span>
                        {advice.band && <ScorePill variant="sm" score={advice.score} band={advice.band} provisional={advice.provisional} className="ml-2 align-middle" />}
                        <span className="text-muted-foreground"> — {advice.detail}</span>
                      </div>
                    </div>
                    {advice.video != null && advice.title !== "No analysis needed" && (
                      <Button type="button" size="sm" variant={advice.video === analyzeVideo ? "outline" : "default"}
                              onClick={() => setAnalyzeVideo(advice!.video === true)}>
                        {advice.video === analyzeVideo ? "Applied ✓" : advice.video ? "Turn video ON" : "Keep transcript only"}
                      </Button>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <p className="text-muted-foreground text-xs">
              Class Sentiment Score{scoring.version != null ? `, version ${scoring.version}` : ""}:{" "}
              {BAND_ORDER.map((b) => `${BAND_META[b].label} → ${ACTION_LABEL[scoring.config.actions[b]]}`).join(" · ")} · fewer than{" "}
              {scoring.config.min_votes.action || 6} responses → {ACTION_LABEL[scoring.config.actions.no_data]} · any escalation → watch the recording.
            </p>
          </div>

          {/* two columns from lg: the class on the left, the recording and materials on the right */}
          <div className="grid gap-7 lg:grid-cols-2 lg:gap-8">
          <div className="space-y-7">
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
                  <label htmlFor="rating" className={label}>Class rating (of 5)</label>
                  <Input id="rating" name="rating" type="number" step="0.01" min="0" max="5" placeholder="4.2"
                         defaultValue={prefill?.rating} />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="num_ratings" className={label}>Learners who rated</label>
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
          </div>
          <div className="space-y-7">
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
            <MaterialsDropZone />
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
          </div>
          </div>

          <AnimatePresence initial={false}>
            {state.error && (
              <motion.p
                key={state.error}
                role="alert"
                initial={reduce ? false : { opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease: EASE_OUT }}
                className="text-destructive bg-destructive/5 rounded-lg border border-current/20 px-3 py-2 text-sm"
              >
                {state.error}
              </motion.p>
            )}
          </AnimatePresence>

          <div className="border-t pt-5">
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={pending} aria-busy={pending} className="min-w-36">
                {pending ? (<><Loader2 className="size-4 animate-spin" aria-hidden /> Starting…</>) : "Analyze class"}
              </Button>
              <span className="text-muted-foreground text-xs" aria-live="polite">
                {pending
                  ? "Handing the recording to the AI engine — a few seconds."
                  : "Runs in the background — you'll land on the report page while it works."}
              </span>
            </div>
            {/* indeterminate progress line: the track is always there (no shift), the bar only while pending */}
            <div className={cn("mt-3 h-0.5 overflow-hidden rounded-full", pending ? "bg-muted" : "bg-transparent")} aria-hidden>
              {pending && (
                <motion.div
                  className="bg-primary h-full w-1/3 rounded-full"
                  animate={reduce ? { opacity: [0.4, 1, 0.4], x: "100%" } : { x: ["-100%", "300%"] }}
                  transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                />
              )}
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
