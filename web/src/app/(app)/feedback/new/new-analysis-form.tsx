"use client";

import { useActionState, useState } from "react";
import { createAnalysis, type AnalyzeState } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const label = "text-sm font-medium";
const field =
  "border-input flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

type ClassRow = { id: string; topic: string; date: string; instructor: string };

export function NewAnalysisForm({
  courses,
  cohortsByCourse,
  classesByCohort,
  instructorNames,
}: {
  courses: { id: string; name: string }[];
  cohortsByCourse: Record<string, { id: string; name: string }[]>;
  classesByCohort: Record<string, ClassRow[]>;
  instructorNames: string[];
}) {
  const [state, formAction, pending] = useActionState<AnalyzeState, FormData>(createAnalysis, {});
  const [courseId, setCourseId] = useState("");
  const [cohortId, setCohortId] = useState("");
  const [classId, setClassId] = useState("");
  const [topic, setTopic] = useState("");
  const [classDate, setClassDate] = useState("");
  const [instructor, setInstructor] = useState("");
  const [classType, setClassType] = useState<"live_class" | "ars">("live_class");
  const [source, setSource] = useState<"vimeo" | "upload">("vimeo");

  const cohorts = cohortsByCourse[courseId] ?? [];
  const classes = classesByCohort[cohortId] ?? [];

  function onClassChange(id: string) {
    setClassId(id);
    const cls = classes.find((c) => c.id === id);
    if (cls) {
      setTopic(cls.topic);
      setClassDate(cls.date);
      setInstructor(cls.instructor);
      // auto-detect an assignment-review session from the class name (still editable below)
      if (/assignment\s*review/i.test(cls.topic)) setClassType("ars");
    }
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>New analysis</CardTitle>
        <CardDescription>
          Pick the course → cohort → class. Topic, date and instructor fill in automatically
          (all editable). Then add the rating and the recording.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form action={formAction} className="space-y-5">
          <input type="hidden" name="cohort_id" value={cohortId} />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="course_id" className={label}>Course</label>
              <select
                id="course_id" name="course_id" required className={field}
                value={courseId}
                onChange={(e) => { setCourseId(e.target.value); setCohortId(""); setClassId(""); }}
              >
                <option value="" disabled>Select a course…</option>
                {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="cohort" className={label}>Cohort</label>
              <select
                id="cohort" className={field} value={cohortId} disabled={!courseId}
                onChange={(e) => { setCohortId(e.target.value); setClassId(""); }}
              >
                <option value="">{courseId ? "Select a cohort…" : "Pick a course first"}</option>
                {cohorts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <label htmlFor="class" className={label}>Class</label>
              <select
                id="class" className={field} value={classId} disabled={!cohortId}
                onChange={(e) => onClassChange(e.target.value)}
              >
                <option value="">{cohortId ? "Select a class…" : "Pick a cohort first"}</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>{c.date ? `${c.date} — ` : ""}{c.topic}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="topic" className={label}>Topic (editable)</label>
              <input id="topic" name="topic" required className={field}
                     value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Class topic" />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="instructor" className={label}>Instructor</label>
              <input id="instructor" name="instructor" list="instructor-options" className={field}
                     value={instructor} onChange={(e) => setInstructor(e.target.value)} placeholder="Instructor" />
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
              <p className="text-muted-foreground text-xs">Each type is analyzed with its own rubric.</p>
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

          <div className="space-y-1.5">
            <label htmlFor="materials" className={label}>Class materials (optional — you can pick several)</label>
            <Input id="materials" name="materials" type="file" multiple
                   accept=".pdf,.pptx,.docx,.txt,.md,.ipynb" className="file:mr-3 file:text-sm" />
            <textarea name="materials_text" rows={2} className={field + " h-auto py-2"}
                      placeholder="…or paste key materials/notes here (useful if a deck is too big to upload)." />
            <p className="text-muted-foreground text-xs">
              Slides, coding notebook, docs — the AI checks the class against them (was the content
              covered, and taught correctly?). Keep the total upload under <strong>~4&nbsp;MB</strong>
              (compress or export to PDF, or paste text above for bigger decks). Materials are used
              only for this analysis and are <strong>never stored</strong>.
            </p>
          </div>

          <div className="space-y-2">
            <div className={label}>Transcript source</div>
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
          </div>

          {state.error && <p className="text-destructive text-sm">{state.error}</p>}

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={pending}>
              {pending ? "Analyzing… (this can take ~30s)" : "Analyze"}
            </Button>
            <span className="text-muted-foreground text-xs">Runs Claude on the transcript — costs a few cents.</span>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
