"use client";

import { useActionState, useState } from "react";
import { createAnalysis, type AnalyzeState } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Clapperboard, FileText, Loader2, Paperclip } from "lucide-react";

const label = "text-sm font-medium";
const field =
  "border-input flex h-9 w-full rounded-md border bg-card px-3 py-1 text-sm shadow-sm outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring";

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

export function NewAnalysisForm({
  courses,
  instructorNames,
}: {
  courses: { id: string; name: string }[];
  instructorNames: string[];
}) {
  const [state, formAction, pending] = useActionState<AnalyzeState, FormData>(createAnalysis, {});
  const [courseId, setCourseId] = useState("");
  const [classType, setClassType] = useState<"live_class" | "ars">("live_class");
  const [source, setSource] = useState<"vimeo" | "upload">("vimeo");
  const [analyzeVideo, setAnalyzeVideo] = useState(false);

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
                <input id="topic" name="topic" required className={field} placeholder="e.g. Decision Trees & Ensembles" />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="instructor" className={label}>Instructor</label>
                <input id="instructor" name="instructor" list="instructor-options" className={field}
                       placeholder="Type or pick a name" />
                <datalist id="instructor-options">
                  {instructorNames.map((n) => <option key={n} value={n} />)}
                </datalist>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="class_date" className={label}>Class date</label>
                <input id="class_date" name="class_date" type="date" required className={field} />
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
                  <Input id="rating" name="rating" type="number" step="0.01" min="0" max="5" placeholder="4.2" />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="num_ratings" className={label}># ratings</label>
                  <Input id="num_ratings" name="num_ratings" type="number" min="0" placeholder="18" />
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
