"use client";

import { useActionState, useMemo, useState } from "react";
import { createAnalysis, type AnalyzeState } from "../actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const label = "text-sm font-medium";
const field =
  "border-input flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

type CatalogEntry = { topic: string; instructor: string };

export function NewAnalysisForm({
  courses,
  catalog,
}: {
  courses: { id: string; name: string }[];
  catalog: Record<string, CatalogEntry[]>;
}) {
  const [state, formAction, pending] = useActionState<AnalyzeState, FormData>(createAnalysis, {});
  const [courseId, setCourseId] = useState("");
  const [topic, setTopic] = useState("");
  const [instructor, setInstructor] = useState("");
  const [source, setSource] = useState<"vimeo" | "upload">("vimeo");

  const entries = catalog[courseId] ?? [];
  const topics = useMemo(() => Array.from(new Set(entries.map((e) => e.topic))), [entries]);
  const instructors = useMemo(
    () => Array.from(new Set(entries.map((e) => e.instructor).filter(Boolean))),
    [entries],
  );

  function onCourseChange(id: string) {
    setCourseId(id);
    setTopic("");
    setInstructor("");
  }
  function onTopicChange(value: string) {
    setTopic(value);
    const match = entries.find((e) => e.topic === value);
    if (match?.instructor) setInstructor(match.instructor); // auto-fill the assigned instructor
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>New analysis</CardTitle>
        <CardDescription>
          Pick the course and class — the instructor fills in automatically. You can also type a new
          class or instructor. Then add the recording.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form action={formAction} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="course_id" className={label}>Course</label>
              <select
                id="course_id" name="course_id" required className={field}
                value={courseId} onChange={(e) => onCourseChange(e.target.value)}
              >
                <option value="" disabled>Select a course…</option>
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="cohort" className={label}>Cohort</label>
              <Input id="cohort" name="cohort" placeholder="e.g. Aug 2026" />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="topic" className={label}>Class / topic</label>
              <input
                id="topic" name="topic" required list="topic-options" className={field}
                value={topic} onChange={(e) => onTopicChange(e.target.value)}
                placeholder={courseId ? "Pick a class or type one" : "Select a course first"}
              />
              <datalist id="topic-options">
                {topics.map((t) => <option key={t} value={t} />)}
              </datalist>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="instructor" className={label}>Instructor</label>
              <input
                id="instructor" name="instructor" list="instructor-options" className={field}
                value={instructor} onChange={(e) => setInstructor(e.target.value)}
                placeholder="Auto-fills from the class"
              />
              <datalist id="instructor-options">
                {instructors.map((i) => <option key={i} value={i} />)}
              </datalist>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="class_date" className={label}>Class date</label>
              <Input id="class_date" name="class_date" type="date" required />
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
            <textarea
              id="agenda" name="agenda" rows={3} className={field + " h-auto py-2"}
              placeholder="Paste the planned agenda — helps judge coverage & pacing."
            />
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
