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
import { Clapperboard, FileText, Loader2, Paperclip, Upload } from "lucide-react";
import { voteLabel } from "@/lib/decision";
import type { Action, Band } from "@/lib/sentiment";
import { ScorePill } from "@/components/score/score-pill";
import { cn } from "@/lib/utils";
import { RecordingFinder } from "./recording-finder";

const label = "text-sm font-medium";
const field =
  "border-input flex h-9 w-full rounded-md border bg-card px-3 py-1 text-sm shadow-sm outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring";

const prettyDate = (isoDate: string) =>
  new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" });

const MAX_MATERIALS_BYTES = 4 * 1024 * 1024;
const fmtSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

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
  yesVotes: string;
  noVotes: string;
  /** The stored Class Sentiment Score of the class this form was opened from. */
  score: number | null;
  band: Band | null;
  action: Action | null;
  video: boolean;
};

/** Drop zone for class materials. Files dropped on it are handed to the real <input type=file>
 *  (via DataTransfer) so the form posts exactly as before; the input stays focusable for
 *  keyboard users. Drag-over is a visible state, not just a cursor. */
function MaterialsDropZone() {
  const reduce = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<{ name: string; size: number }[]>([]);

  const [sizeError, setSizeError] = useState<string | null>(null);
  const readFiles = (list: FileList | null) => {
    const picked = Array.from(list ?? []);
    const total = picked.reduce((a, f) => a + f.size, 0);
    if (total > MAX_MATERIALS_BYTES) {
      // Checked here, before the upload: the server used to reject only after everything was sent.
      setSizeError(`Materials are ${fmtSize(total)} together — keep the total under 4 MB (export the deck as PDF, or paste the key content instead).`);
      if (inputRef.current) inputRef.current.value = "";
      setFiles([]);
      return;
    }
    setSizeError(null);
    setFiles(picked.map((f) => ({ name: f.name, size: f.size })));
  };
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
      {sizeError && <p className="text-destructive text-xs" role="alert">{sizeError}</p>}
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
  defaultCourseId,
  uplevel,
  isAdmin,
}: {
  courses: { id: string; name: string }[];
  instructorNames: string[];
  prefill?: Prefill;
  defaultCourseId?: string | null;
  /** The UpLevel connection's state (Admin › UpLevel): decides whether the recording is looked up. */
  uplevel: "ok" | "expired" | "not_set" | "unknown" | "error" | "empty";
  isAdmin: boolean;
}) {
  const reduce = useReducedMotion();
  const [state, formAction, pending] = useActionState<AnalyzeState, FormData>(createAnalysis, {});
  const [courseId, setCourseId] = useState(prefill?.courseId ?? defaultCourseId ?? "");   // the link from a course carries it
  const [classType, setClassType] = useState<"live_class" | "ars">(prefill?.classType ?? "live_class");
  const [source, setSource] = useState<"vimeo" | "upload">("vimeo");
  const [analyzeVideo, setAnalyzeVideo] = useState(prefill?.video ?? false);
  // The rating and the count are controlled so a queue prefill lands in them.
  const [hRating, setHRating] = useState(prefill?.rating ?? "");
  const [hRated, setHRated] = useState(prefill?.numRatings ?? "");
  // The class and the recording are controlled so the UpLevel lookup can read the details and
  // fill the link.
  const [topic, setTopic] = useState(prefill?.topic ?? "");
  const [instructor, setInstructor] = useState(prefill?.instructor ?? "");
  const [classDate, setClassDate] = useState(prefill?.classDate ?? "");
  const [vimeoUrl, setVimeoUrl] = useState("");
  const useRecording = React.useCallback((link: string) => {
    setSource("vimeo");
    setVimeoUrl(link);
  }, []);

  // A failed start is loud (toast) AND persistent (inline, below the form).
  useEffect(() => {
    if (state.error) toast.error("Couldn't start the analysis", { description: state.error });
  }, [state]);

  const prefillVote = prefill ? voteLabel(parseInt(prefill.yesVotes, 10), parseInt(prefill.noVotes, 10)) : null;

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
                       value={topic} onChange={(e) => setTopic(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="instructor" className={label}>Instructor</label>
                <input id="instructor" name="instructor" list="instructor-options" className={field}
                       placeholder="Type or pick a name" value={instructor} onChange={(e) => setInstructor(e.target.value)} />
                <datalist id="instructor-options">
                  {instructorNames.map((n) => <option key={n} value={n} />)}
                </datalist>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="class_date" className={label}>Class date</label>
                <input id="class_date" name="class_date" type="date" required className={field}
                       value={classDate} onChange={(e) => setClassDate(e.target.value)} />
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
                         value={hRating} onChange={(e) => setHRating(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="num_ratings" className={label}>Learners who rated</label>
                  <Input id="num_ratings" name="num_ratings" type="number" min="0" placeholder="18"
                         value={hRated} onChange={(e) => setHRated(e.target.value)} />
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
              <>
                <RecordingFinder
                  topic={topic} instructor={instructor} classDate={classDate} classType={classType}
                  connection={uplevel} currentLink={vimeoUrl} onUse={useRecording} isAdmin={isAdmin}
                />
                <Input name="vimeo_url" type="url" placeholder="https://vimeo.com/123456789" aria-label="Vimeo link"
                       value={vimeoUrl} onChange={(e) => setVimeoUrl(e.target.value)} />
              </>
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
