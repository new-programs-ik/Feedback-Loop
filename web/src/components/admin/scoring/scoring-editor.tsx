"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  ACTIONS,
  COMPONENTS,
  FIELD_HELP,
  cloneConfig,
  includedComponents,
  weightSum,
  type ActionKind,
  type Component,
  type ScoringConfig,
} from "../scoring-config";
import { bandMeta } from "./band-meta";

/** Every switch of the scoring contract as a labelled control with a one-line plain-English
 *  helper. Numeric inputs are uncontrolled (so "4." can be typed) and re-seeded through
 *  `resetKey` whenever a whole config is loaded; selects are controlled. `onChange` receives a
 *  fresh config object on every edit — the preview recomputes from it. */
export function ScoringEditor({
  config,
  onChange,
  disabled = false,
  resetKey,
}: {
  config: ScoringConfig;
  onChange: (next: ScoringConfig) => void;
  disabled?: boolean;
  resetKey: number | string;
}) {
  const patch = (fn: (c: ScoringConfig) => void) => {
    const next = cloneConfig(config);
    fn(next);
    onChange(next);
  };
  const included = includedComponents(config);
  const sum = weightSum(config);
  const sumOk = Math.abs(sum - 100) < 1e-9;

  return (
    <div key={resetKey} className="space-y-5" data-slot="scoring-editor">
      <Section title="Rating" hint="How the star rating becomes points.">
        <Row>
          <Field label="Mode" help={FIELD_HELP.ratingMode}>
            <Select
              value={config.rating.mode}
              disabled={disabled}
              onChange={(e) => patch((c) => (c.rating.mode = e.target.value as ScoringConfig["rating"]["mode"]))}
              aria-label="Rating mode"
            >
              <option value="linear">Linear (÷ scale)</option>
              <option value="knee">Knee (steeper below the line)</option>
            </Select>
          </Field>
          <Num label="Scale" help={FIELD_HELP.ratingScale} value={config.rating.scale} step={0.5} min={1} disabled={disabled} onCommit={(v) => patch((c) => (c.rating.scale = v))} />
        </Row>
        <Row>
          <Num label="Floor" help={FIELD_HELP.ratingFloor} value={config.rating.floor} step={0.05} min={0} disabled={disabled || config.rating.mode !== "knee"} onCommit={(v) => patch((c) => (c.rating.floor = v))} />
          <Num label="Line" help={FIELD_HELP.ratingLine} value={config.rating.line} step={0.05} min={0} disabled={disabled} onCommit={(v) => patch((c) => (c.rating.line = v))} />
          <Num label="Points at the line" help={FIELD_HELP.ratingLineValue} value={config.rating.line_value} step={1} min={1} max={99} disabled={disabled || config.rating.mode !== "knee"} onCommit={(v) => patch((c) => (c.rating.line_value = v))} />
        </Row>
      </Section>

      <Section title="Approval" hint="“Would you have this instructor back?” — the share of yes votes.">
        <Row>
          <Field label="Mode" help={FIELD_HELP.approvalMode}>
            <Select value={config.approval.mode} disabled={disabled} onChange={(e) => patch((c) => (c.approval.mode = e.target.value as ScoringConfig["approval"]["mode"]))} aria-label="Approval mode">
              <option value="cliff">Cliff (all or nothing at the bar)</option>
              <option value="graded">Graded (floor → bar)</option>
            </Select>
          </Field>
          <Num label="Bar %" help={FIELD_HELP.approvalBar} value={config.approval.bar} step={1} min={1} max={100} disabled={disabled} onCommit={(v) => patch((c) => (c.approval.bar = v))} />
          <Num label="Floor %" help={FIELD_HELP.approvalFloor} value={config.approval.floor} step={1} min={0} max={99} disabled={disabled || config.approval.mode !== "graded"} onCommit={(v) => patch((c) => (c.approval.floor = v))} />
        </Row>
      </Section>

      <Section title="How many rated, and how many of those who attended" hint="How many learners rated, and what share of the room that was.">
        <Row>
          <Field label="Responses" help={FIELD_HELP.sampleMode}>
            <Select value={config.sample.mode} disabled={disabled} onChange={(e) => patch((c) => (c.sample.mode = e.target.value as ScoringConfig["sample"]["mode"]))} aria-label="Responses mode">
              <option value="cliff">Cliff at the target</option>
              <option value="graded">Graded up to the target</option>
              <option value="off">Off</option>
            </Select>
          </Field>
          <Num label="Target" help={FIELD_HELP.sampleTarget} value={config.sample.target} step={1} min={1} disabled={disabled || config.sample.mode === "off"} onCommit={(v) => patch((c) => (c.sample.target = v))} />
          <Field label="Rated / attended" help={FIELD_HELP.reachMode}>
            <Select value={config.reach.mode} disabled={disabled} onChange={(e) => patch((c) => (c.reach.mode = e.target.value as ScoringConfig["reach"]["mode"]))} aria-label="Rated-of-attended mode">
              <option value="graded">Graded (share of attendees who rated)</option>
              <option value="off">Off</option>
            </Select>
          </Field>
        </Row>
      </Section>

      <Section title="Track record" hint="The instructor's average over earlier classes.">
        <Row>
          <Field label="Mode" help={FIELD_HELP.trackMode}>
            <Select value={config.track.mode} disabled={disabled} onChange={(e) => patch((c) => (c.track.mode = e.target.value as ScoringConfig["track"]["mode"]))} aria-label="Track record mode">
              <option value="off">Off</option>
              <option value="on">On</option>
            </Select>
          </Field>
          <Num label="Floor" help={FIELD_HELP.trackFloor} value={config.track.floor} step={0.05} min={0} disabled={disabled || config.track.mode !== "on"} onCommit={(v) => patch((c) => (c.track.floor = v))} />
          <Num label="Line" help={FIELD_HELP.trackLine} value={config.track.line} step={0.05} min={0} disabled={disabled || config.track.mode !== "on"} onCommit={(v) => patch((c) => (c.track.line = v))} />
          <Num label="Min classes" help={FIELD_HELP.trackMinClasses} value={config.track.min_classes} step={1} min={0} disabled={disabled || config.track.mode !== "on"} onCommit={(v) => patch((c) => (c.track.min_classes = v))} />
        </Row>
      </Section>

      <Section
        title="Weights"
        hint={FIELD_HELP.weights}
        aside={
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
              sumOk ? "text-foreground" : "text-warning border-warning/40",
            )}
            role="status"
          >
            <span aria-hidden className="size-1.5 rounded-full" style={{ background: sumOk ? "var(--success)" : "var(--warning)" }} />
            {sumOk ? "Included weights sum to 100" : `Included weights sum to ${sum} — re-scaled to 100 when scoring`}
          </span>
        }
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {COMPONENTS.map((c) => (
            <Num
              key={c}
              label={COMPONENT_LABEL[c]}
              value={config.weights[c]}
              step={1}
              min={0}
              max={100}
              disabled={disabled}
              muted={!included.includes(c)}
              onCommit={(v) => patch((cfg) => (cfg.weights[c] = v))}
            />
          ))}
        </div>
      </Section>

      <Section title="Small-sample guard" hint="Protects classes where only a handful of learners voted.">
        <Row>
          <Num label="k (typical answers blended in)" help={FIELD_HELP.guardK} value={config.guard.k} step={1} min={0} disabled={disabled} onCommit={(v) => patch((c) => (c.guard.k = v))} />
          <Field label="Prior" help={FIELD_HELP.guardPrior}>
            <Select value={config.guard.prior} disabled={disabled || config.guard.k === 0} onChange={(e) => patch((c) => (c.guard.prior = e.target.value as ScoringConfig["guard"]["prior"]))} aria-label="Guard prior">
              <option value="course">This course&apos;s typical class</option>
              <option value="global">All courses</option>
            </Select>
          </Field>
        </Row>
      </Section>

      <Section title="Minimum approval answers" hint="Below these, the score is shown with care.">
        <Row>
          <Num label="To show a band" help={FIELD_HELP.minVotesBand} value={config.min_votes.band} step={1} min={0} disabled={disabled} onCommit={(v) => patch((c) => (c.min_votes.band = v))} />
          <Num label="To trigger an analysis" help={FIELD_HELP.minVotesAction} value={config.min_votes.action} step={1} min={0} disabled={disabled} onCommit={(v) => patch((c) => (c.min_votes.action = v))} />
        </Row>
      </Section>

      <Section title="Hard lines" hint="The two lines the team already agreed, as ceilings on the band.">
        <Row>
          <Toggle
            label="Rating line"
            help={FIELD_HELP.capRating}
            on={config.caps.rating_line != null}
            disabled={disabled}
            onToggle={(on) => patch((c) => (c.caps.rating_line = on ? c.rating.line : null))}
          >
            <Num label="Under this rating" value={config.caps.rating_line ?? config.rating.line} step={0.05} min={0} disabled={disabled || config.caps.rating_line == null} onCommit={(v) => patch((c) => (c.caps.rating_line = v))} compact />
          </Toggle>
          <Toggle
            label="Approval bar"
            help={FIELD_HELP.capApproval}
            on={config.caps.approval_bar != null}
            disabled={disabled}
            onToggle={(on) => patch((c) => (c.caps.approval_bar = on ? c.approval.bar : null))}
          >
            <Num label="Under this approval %" value={config.caps.approval_bar ?? config.approval.bar} step={1} min={1} max={100} disabled={disabled || config.caps.approval_bar == null} onCommit={(v) => patch((c) => (c.caps.approval_bar = v))} compact />
          </Toggle>
        </Row>
      </Section>

      <Section title="Band edges" hint={FIELD_HELP.bands}>
        <Row>
          <Num label="Excellent from" value={config.bands.excellent} step={1} min={1} max={100} disabled={disabled} onCommit={(v) => patch((c) => (c.bands.excellent = v))} />
          <Num label="Good from" value={config.bands.good} step={1} min={1} max={100} disabled={disabled} onCommit={(v) => patch((c) => (c.bands.good = v))} />
          <Num label="Average from" value={config.bands.average} step={1} min={1} max={100} disabled={disabled} onCommit={(v) => patch((c) => (c.bands.average = v))} />
        </Row>
        <EdgeStrip edges={config.bands} />
      </Section>

      <Section title="Missing inputs" hint={FIELD_HELP.missing}>
        <Row>
          {(["approval", "reach", "track"] as const).map((k) => (
            <Field key={k} label={`No ${k === "track" ? "track record" : k}`}>
              <Select value={config.missing[k]} disabled={disabled} onChange={(e) => patch((c) => (c.missing[k] = e.target.value as ScoringConfig["missing"]["approval"]))} aria-label={`Missing ${k} policy`}>
                <option value="neutral">Neutral (left out)</option>
                <option value="zero">Zero (scores 0)</option>
              </Select>
            </Field>
          ))}
        </Row>
      </Section>

      <Section title="Band → action" hint={FIELD_HELP.actions}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {(["excellent", "good", "average", "bad", "no_data"] as const).map((b) => (
            <Field
              key={b}
              label={
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden className="size-1.5 rounded-full" style={{ background: bandMeta(b).color }} />
                  {bandMeta(b).label}
                </span>
              }
            >
              <Select value={config.actions[b]} disabled={disabled} onChange={(e) => patch((c) => (c.actions[b] = e.target.value as ActionKind))} aria-label={`Action for ${bandMeta(b).label}`}>
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>
                    {ACTION_TEXT[a]}
                  </option>
                ))}
              </Select>
            </Field>
          ))}
        </div>
      </Section>
    </div>
  );
}

const COMPONENT_LABEL: Record<Component, string> = {
  rating: "Rating",
  approval: "Approval",
  sample: "Responses",
  reach: "Rated / attended",
  track: "Track record",
};
const ACTION_TEXT: Record<ActionKind, string> = {
  video: "Video analysis",
  transcript: "Transcript analysis",
  none: "No analysis",
  watch: "Watch",
};

function Section({
  title,
  hint,
  aside,
  children,
}: {
  title: string;
  hint?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="min-w-0 space-y-3 border-t pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <legend className="float-left text-[13px] font-semibold tracking-[-0.01em]">{title}</legend>
        {aside}
      </div>
      {hint && <p className="text-muted-foreground -mt-2 text-[11.5px]">{hint}</p>}
      {children}
    </fieldset>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">{children}</div>;
}

function Field({ label, help, children }: { label: React.ReactNode; help?: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0 space-y-1">
      <span className="text-muted-foreground block text-[11.5px] font-medium">{label}</span>
      {children}
      {help && <span className="text-muted-foreground/80 block text-[11px] leading-snug">{help}</span>}
    </label>
  );
}

/** Uncontrolled number input; commits on change when the text parses, so partial input never
 *  fights the caret. The surrounding `key={resetKey}` re-seeds it when a config is loaded. */
function Num({
  label,
  help,
  value,
  onCommit,
  step,
  min,
  max,
  disabled,
  muted,
  compact,
}: {
  label: string;
  help?: string;
  value: number;
  onCommit: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  muted?: boolean;
  compact?: boolean;
}) {
  return (
    <Field label={label} help={help}>
      <Input
        type="number"
        inputMode="decimal"
        defaultValue={value}
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        onChange={(e) => {
          const v = e.target.valueAsNumber;
          if (Number.isFinite(v)) onCommit(v);
        }}
        className={cn("font-mono", compact && "h-8", muted && "opacity-60")}
        aria-label={label}
      />
    </Field>
  );
}

function Toggle({
  label,
  help,
  on,
  onToggle,
  disabled,
  children,
}: {
  label: string;
  help?: string;
  on: boolean;
  onToggle: (on: boolean) => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-[12.5px] font-medium">
        <input type="checkbox" checked={on} disabled={disabled} onChange={(e) => onToggle(e.target.checked)} className="accent-primary size-3.5" />
        {label}
      </label>
      {children}
      {help && <p className="text-muted-foreground/80 text-[11px] leading-snug">{help}</p>}
    </div>
  );
}

/** The four zones the edges create, drawn to scale — an instant sanity check. */
function EdgeStrip({ edges }: { edges: ScoringConfig["bands"] }) {
  const zones = [
    { band: "bad" as const, from: 0, to: edges.average },
    { band: "average" as const, from: edges.average, to: edges.good },
    { band: "good" as const, from: edges.good, to: edges.excellent },
    { band: "excellent" as const, from: edges.excellent, to: 100 },
  ];
  return (
    <div className="relative mt-1 h-5 w-full overflow-hidden rounded-sm text-[10px]" aria-hidden>
      {zones.map((z) => {
        const w = Math.max(0, Math.min(100, z.to) - Math.max(0, z.from));
        return (
          <span
            key={z.band}
            className="absolute inset-y-0 flex items-center justify-center truncate px-1"
            style={{ left: `${Math.max(0, z.from)}%`, width: `${w}%`, background: bandMeta(z.band).soft, color: "var(--foreground)" }}
          >
            {w > 8 ? `${bandMeta(z.band).label} ${z.from}–${z.to}` : ""}
          </span>
        );
      })}
    </div>
  );
}
