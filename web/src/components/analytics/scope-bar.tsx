"use client";

import * as React from "react";
import Link from "next/link";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { AutoSubmit } from "@/components/auto-submit";
import type { RangePreset } from "@/components/filter-bar";
import { cn } from "@/lib/utils";
import type { Scope } from "@/lib/analytics";

/** The one filter bar on every data page: period · cohort · live/review · instructor · band.
 *  GET form, URL = state; auto-submits on change; sticks under the topbar from `md` up. */
export function ScopeBar({
  basePath,
  scope,
  defaultRange = "90d",
  cohorts,
  instructors,
  courses,
  courseId,
  show = { cohort: true, kind: true, instructor: true, band: true },
  extra,
  className,
}: {
  basePath: string;
  scope: Scope;
  defaultRange?: RangePreset;
  cohorts?: { key: string; name: string }[];
  instructors?: { key: string; name: string }[];
  /** Team level only: a course select (the course workspaces are already one course). */
  courses?: { id: string; name: string }[];
  courseId?: string;
  show?: { cohort?: boolean; kind?: boolean; instructor?: boolean; band?: boolean };
  /** Hidden inputs to preserve other query params. */
  extra?: Record<string, string | undefined>;
  className?: string;
}) {
  const active = scope.range !== defaultRange || !!scope.cohort || !!scope.kind || !!scope.instructor || !!scope.band || !!courseId;
  const [showCustom, setShowCustom] = React.useState(scope.range === "custom");
  return (
    <form
      method="get"
      action={basePath}
      data-print-hide
      data-slot="scope-bar"
      className={cn(
        "bg-background z-10 -mx-4 mb-4 flex flex-wrap items-center gap-2 border-b px-4 py-2 md:sticky md:top-16 md:-mx-8 md:px-8",
        className,
      )}
    >
      {Object.entries(extra ?? {}).map(([k, v]) => (v ? <input key={k} type="hidden" name={k} value={v} /> : null))}
      {/* Every preset applies itself. "Custom" does not: submitting it with no dates yet just
          reloaded the same data, which read as the control being broken. It reveals the two date
          boxes instead, and the page changes when a date is actually chosen. */}
      <Select
        name="range"
        defaultValue={scope.range}
        aria-label="Period"
        className="w-36"
        onChange={(e) => {
          const form = e.currentTarget.form;
          if (e.currentTarget.value !== "custom") form?.requestSubmit();
          else setShowCustom(true);
        }}
      >
        <option value="7d">Last 7 days</option>
        <option value="30d">Last 30 days</option>
        <option value="90d">Last 90 days</option>
        <option value="month">This month</option>
        <option value="custom">Custom…</option>
      </Select>
      {showCustom && (
        <>
          {/* No min/max tying these two together. They used to carry max={to} and min={from}, so to
              look at January you had to move "to" back first and the browser would not let you -
              the pair locked you inside the window you were trying to leave. The server already
              swaps them if they arrive the wrong way round. */}
          <Input
            type="date"
            name="from"
            defaultValue={scope.range === "custom" ? scope.from : ""}
            aria-label="From"
            className="w-[9.5rem]"
          />
          <span className="text-muted-foreground text-xs">to</span>
          <Input
            type="date"
            name="to"
            defaultValue={scope.range === "custom" ? scope.to : ""}
            aria-label="To"
            className="w-[9.5rem]"
          />
          <Button type="submit" size="sm" variant="outline">
            Show these dates
          </Button>
        </>
      )}
      {scope.anchor && scope.range !== "custom" && (
        <span className="text-muted-foreground text-xs" title="The sheet has nothing newer yet; presets count back from the last rated class">
          to the last rated class ({new Date(scope.anchor + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short" })})
        </span>
      )}
      {courses && courses.length > 0 && (
        <AutoSubmit>
          <Select name="course" defaultValue={courseId ?? ""} aria-label="Course" className="w-48">
            <option value="">All courses</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </AutoSubmit>
      )}
      {show.cohort && cohorts && cohorts.length > 0 && (
        <AutoSubmit>
          <Select name="cohort" defaultValue={scope.cohort ?? ""} aria-label="Cohort" className="w-44">
            <option value="">All cohorts</option>
            {cohorts.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </AutoSubmit>
      )}
      {show.kind && (
        <AutoSubmit>
          <Select name="kind" defaultValue={scope.kind ?? ""} aria-label="Session kind" className="w-32">
            <option value="">Live + review</option>
            <option value="live">Live only</option>
            <option value="review">Reviews only</option>
          </Select>
        </AutoSubmit>
      )}
      {show.instructor && instructors && instructors.length > 0 && (
        <AutoSubmit>
          <Select name="instructor" defaultValue={scope.instructor ?? ""} aria-label="Instructor" className="w-44">
            <option value="">All instructors</option>
            {instructors.map((i) => (
              <option key={i.key} value={i.key}>
                {i.name}
              </option>
            ))}
          </Select>
        </AutoSubmit>
      )}
      {show.band && (
        <AutoSubmit>
          <Select name="band" defaultValue={scope.band ?? ""} aria-label="Band" className="w-32">
            <option value="">Any band</option>
            <option value="excellent">Excellent</option>
            <option value="good">Good</option>
            <option value="average">Average</option>
            <option value="bad">Bad</option>
          </Select>
        </AutoSubmit>
      )}
      {active && (
        <Link href={basePath} className="text-muted-foreground hover:text-foreground inline-flex h-9 items-center rounded-md px-2 text-xs">
          Clear
        </Link>
      )}
    </form>
  );
}
