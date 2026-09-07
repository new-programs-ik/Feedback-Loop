"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { FilePlus2, Save, Send, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, fieldClasses } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { PreviewPayload, ScoringConfigRow } from "@/lib/admin";
import {
  createScoringDraft,
  deleteScoringDraft,
  getPreviewRows,
  proposeScoringDraft,
  publishScoringConfig,
  saveScoringDraft,
} from "@/app/(app)/admin/actions";
import { MANAGER_ORIGINAL, PRESETS, cloneConfig, validateConfig, type ScoringConfig } from "../scoring-config";
import { ConfirmDialog } from "../confirm-dialog";
import { ScoringEditor } from "./scoring-editor";
import { ScoringPreview } from "./scoring-preview";
import { VersionsTable } from "./versions-table";
import { ConfigDiff } from "./config-diff";
import { NoteDialog } from "./note-dialog";
import type { PreviewStats } from "./preview-math";

export type MonthOption = { value: string; label: string; from: string; to: string };

type Selected = { id: string | null; status: "draft" | "active" | "retired" | "scratch"; version: number | null };

const pretty = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });

/** The scoring page's working surface, in two modes. Admin: open any version, edit drafts,
 *  save, publish, roll back, delete; what-if (any staff): edit a local copy freely and propose it
 *  as a draft. Left = every setting; right = the live preview over a chosen month or range. */
export function ScoringWorkbench({
  mode,
  versions,
  versionsError,
  months,
  defaultMonth,
}: {
  mode: "admin" | "whatif";
  versions: ScoringConfigRow[];
  versionsError: string | null;
  months: MonthOption[];
  defaultMonth: string;
}) {
  const router = useRouter();
  const active = versions.find((v) => v.status === "active") ?? null;
  const baseline = active?.config ?? MANAGER_ORIGINAL;
  const baselineLabel = active ? `v${active.version} · ${active.name}` : "Manager's original (no active version stored)";

  // ── the draft being edited ────────────────────────────────────────────────
  const initial = active ?? versions[0] ?? null;
  const [selected, setSelected] = React.useState<Selected>(
    initial ? { id: initial.id, status: initial.status, version: initial.version } : { id: null, status: "scratch", version: null },
  );
  const [draft, setDraft] = React.useState<ScoringConfig>(() => cloneConfig(initial?.config ?? MANAGER_ORIGINAL));
  const [meta, setMeta] = React.useState({ name: initial?.name ?? MANAGER_ORIGINAL.name!, key: initial?.key ?? "", note: initial?.note ?? "" });
  const [resetKey, setResetKey] = React.useState(0);
  const [dirty, setDirty] = React.useState(false);
  const live = selected.id ? versions.find((v) => v.id === selected.id) : undefined;
  const status = live?.status ?? selected.status;
  const editable = mode === "whatif" || status === "draft" || status === "scratch";
  const errors = validateConfig(draft);

  const load = (cfg: ScoringConfig, m: { name: string; key: string; note: string }, sel: Selected) => {
    setSelected(sel);
    setDraft(cloneConfig(cfg));
    setMeta(m);
    setResetKey((k) => k + 1);
    setDirty(false);
  };
  const openVersion = (v: ScoringConfigRow) => load(v.config, { name: v.name, key: v.key ?? "", note: v.note ?? "" }, { id: v.id, status: v.status, version: v.version });
  const openPreset = (key: string) => {
    const p = PRESETS.find((x) => x.key === key);
    if (!p) return;
    load(p.config, { name: p.config.name ?? p.label, key: "", note: "" }, { id: null, status: "scratch", version: null });
  };
  const edit = (next: ScoringConfig) => {
    setDraft(next);
    setDirty(true);
  };

  // ── preview range + rows ──────────────────────────────────────────────────
  const [monthKey, setMonthKey] = React.useState(defaultMonth);
  const [custom, setCustom] = React.useState<{ from: string; to: string } | null>(null);
  const month = months.find((m) => m.value === monthKey) ?? months[0];
  const range = custom ?? { from: month.from, to: month.to };
  const [payload, setPayload] = React.useState<PreviewPayload | null>(null);
  const loading = !payload || payload.from !== range.from || payload.to !== range.to;
  const { from: rangeFrom, to: rangeTo } = range;
  React.useEffect(() => {
    // The cleanup flag drops a response that arrives after the range moved on.
    let alive = true;
    getPreviewRows(rangeFrom, rangeTo).then((p) => {
      if (alive) setPayload(p);
    });
    return () => {
      alive = false;
    };
  }, [rangeFrom, rangeTo]);
  const [stats, setStats] = React.useState<PreviewStats | null>(null);
  const rangeLabel = `${pretty(range.from)} – ${pretty(range.to)}`;

  // ── actions ───────────────────────────────────────────────────────────────
  const [busy, startTransition] = React.useTransition();
  const [dialog, setDialog] = React.useState<null | { kind: "publish" } | { kind: "rollback"; v: ScoringConfigRow } | { kind: "delete"; v: ScoringConfigRow } | { kind: "propose" }>(null);

  const newDraftFrom = (source: ScoringConfigRow | null, preset?: "C0" | "C5") =>
    startTransition(async () => {
      const r = await createScoringDraft(source ? { fromConfigId: source.id } : { preset: preset ?? "C0" });
      if (!r.ok) {
        toast.error("Could not create the draft", { description: r.error });
        return;
      }
      const cfg = source?.config ?? PRESETS.find((p) => p.key === (preset ?? "C0"))!.config;
      const name = `${source?.name ?? cfg.name ?? "Draft"} (draft)`;
      load(cfg, { name, key: "", note: "" }, { id: r.data.id, status: "draft", version: r.data.version });
      toast.success(`Draft v${r.data.version} created`, { description: "Change settings on the left; the preview updates as you type." });
      router.refresh();
    });

  const saveDraft = async (): Promise<boolean> => {
    if (!selected.id) return false;
    const r = await saveScoringDraft({ id: selected.id, name: meta.name, key: meta.key, note: meta.note, config: draft });
    if (!r.ok) {
      toast.error("Could not save", { description: r.error });
      return false;
    }
    setDirty(false);
    router.refresh();
    return true;
  };

  const onSave = () =>
    startTransition(async () => {
      if (await saveDraft()) toast.success("Draft saved");
    });

  const onPublish = (v: { name: string; note: string }) =>
    startTransition(async () => {
      if (!selected.id) return;
      setMeta((m) => ({ ...m, name: v.name, note: v.note }));
      const saved = await saveScoringDraft({ id: selected.id, name: v.name, key: meta.key, note: v.note, config: draft });
      if (!saved.ok) {
        toast.error("Could not save before publishing", { description: saved.error });
        return;
      }
      const r = await publishScoringConfig({ id: selected.id, name: v.name, note: v.note });
      if (!r.ok) {
        toast.error("Publish failed", { description: r.error });
        return;
      }
      setDialog(null);
      setDirty(false);
      const bc = r.data?.band_counts ?? {};
      toast.success(`Version ${r.data?.version ?? ""} is live`, {
        description: `${r.data?.scored ?? 0} classes re-scored · Excellent ${bc.excellent ?? 0} · Good ${bc.good ?? 0} · Average ${bc.average ?? 0} · Bad ${bc.bad ?? 0}`,
      });
      router.refresh();
    });

  const onRollback = (v: ScoringConfigRow, note: string) =>
    startTransition(async () => {
      const r = await publishScoringConfig({ id: v.id, note });
      if (!r.ok) {
        toast.error("Rollback failed", { description: r.error });
        return;
      }
      setDialog(null);
      toast.success(`Rolled back to v${v.version}`, { description: `${r.data?.scored ?? 0} classes re-scored.` });
      openVersion({ ...v, status: "active" });
      router.refresh();
    });

  const onDelete = (v: ScoringConfigRow) =>
    startTransition(async () => {
      const r = await deleteScoringDraft({ id: v.id });
      if (!r.ok) {
        toast.error("Could not delete", { description: r.error });
        return;
      }
      setDialog(null);
      toast.success(`Draft v${v.version} deleted`);
      if (selected.id === v.id) {
        const next = active ?? versions.find((x) => x.id !== v.id) ?? null;
        if (next) openVersion(next);
        else load(MANAGER_ORIGINAL, { name: MANAGER_ORIGINAL.name!, key: "", note: "" }, { id: null, status: "scratch", version: null });
      }
      router.refresh();
    });

  const onPropose = (v: { name: string; note: string }) =>
    startTransition(async () => {
      const r = await proposeScoringDraft({ name: v.name, note: v.note, config: draft });
      if (!r.ok) {
        toast.error("Could not send the proposal", { description: r.error });
        return;
      }
      setDialog(null);
      toast.success(`Proposed as draft v${r.data.version}`, { description: "An admin will see it under Versions on the scoring page." });
      router.refresh();
    });

  const statusBadge =
    status === "active" ? <Badge variant="success">active</Badge> : status === "retired" ? <Badge variant="outline">retired</Badge> : status === "draft" ? <Badge variant="soft">draft</Badge> : <Badge variant="outline">unsaved</Badge>;

  return (
    <div className="space-y-5" data-slot="scoring-workbench">
      {versionsError && (
        <p className="border-warning/40 bg-warning/5 rounded-md border px-3 py-2 text-[12.5px]">
          Stored versions are not available yet ({versionsError}). You can still preview the presets below; saving and publishing need
          the <code className="font-mono text-[11.5px]">scoring_configs</code> table.
        </p>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,31rem)_minmax(0,1fr)]">
        {/* ── left: what to start from, the draft's name, every setting ── */}
        <div className="min-w-0 space-y-4">
          <div className="bg-card shadow-soft rounded-xl border p-4">
            <div className="flex flex-wrap items-end gap-2">
              <label className="block min-w-0 flex-1 space-y-1">
                <span className="text-muted-foreground block text-[11.5px] font-medium">Start from</span>
                <Select
                  value={selected.id ?? "__scratch"}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val.startsWith("preset:")) openPreset(val.slice(7));
                    else {
                      const v = versions.find((x) => x.id === val);
                      if (v) openVersion(v);
                    }
                  }}
                  aria-label="Version to start from"
                >
                  {versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      v{v.version} · {v.name} ({v.status})
                    </option>
                  ))}
                  {selected.id === null && <option value="__scratch">Unsaved settings</option>}
                  {PRESETS.map((p) => (
                    <option key={p.key} value={`preset:${p.key}`}>
                      Preset · {p.label}
                    </option>
                  ))}
                </Select>
              </label>
              <div className="flex h-9 items-center gap-2">
                {statusBadge}
                {dirty && <span className="text-warning text-[11px] font-medium">unsaved changes</span>}
              </div>
            </div>

            {mode === "admin" && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {status === "draft" ? (
                  <>
                    <Button type="button" variant="outline" size="sm" onClick={onSave} disabled={busy || !dirty || errors.length > 0}>
                      <Save aria-hidden /> Save draft
                    </Button>
                    <Button type="button" size="sm" onClick={() => setDialog({ kind: "publish" })} disabled={busy || errors.length > 0 || loading}>
                      <Upload aria-hidden /> Publish…
                    </Button>
                  </>
                ) : status === "scratch" ? (
                  <Button type="button" size="sm" onClick={() => newDraftFrom(null, "C0")} disabled={busy || !!versionsError}>
                    <FilePlus2 aria-hidden /> Save as a new draft
                  </Button>
                ) : (
                  <Button type="button" size="sm" onClick={() => live && newDraftFrom(live)} disabled={busy || !live}>
                    <FilePlus2 aria-hidden /> New draft from this version
                  </Button>
                )}
                {status !== "draft" && status !== "scratch" && (
                  <span className="text-muted-foreground text-[11.5px]">This version is {status} — settings are read-only.</span>
                )}
              </div>
            )}
            {mode === "whatif" && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button type="button" size="sm" onClick={() => setDialog({ kind: "propose" })} disabled={busy || errors.length > 0 || !dirty}>
                  <Send aria-hidden /> Propose to admin…
                </Button>
                <span className="text-muted-foreground text-[11.5px]">Nothing here changes the live score. A proposal is saved as a draft for an admin.</span>
              </div>
            )}
            {errors.length > 0 && (
              <ul className="text-destructive mt-3 list-disc space-y-0.5 pl-4 text-[12px]">
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
          </div>

          {mode === "admin" && status === "draft" && (
            <div className="bg-card shadow-soft grid gap-3 rounded-xl border p-4 sm:grid-cols-[1fr_10rem]">
              <label className="block space-y-1">
                <span className="text-muted-foreground block text-[11.5px] font-medium">Name</span>
                <Input value={meta.name} onChange={(e) => { setMeta((m) => ({ ...m, name: e.target.value })); setDirty(true); }} maxLength={120} disabled={busy} />
              </label>
              <label className="block space-y-1">
                <span className="text-muted-foreground block text-[11.5px] font-medium">Key</span>
                <Input value={meta.key} onChange={(e) => { setMeta((m) => ({ ...m, key: e.target.value })); setDirty(true); }} maxLength={40} placeholder="two-lines-graded" className="font-mono" disabled={busy} />
              </label>
              <label className="block space-y-1 sm:col-span-2">
                <span className="text-muted-foreground block text-[11.5px] font-medium">Note</span>
                <textarea
                  value={meta.note}
                  onChange={(e) => { setMeta((m) => ({ ...m, note: e.target.value })); setDirty(true); }}
                  rows={2}
                  maxLength={2000}
                  disabled={busy}
                  placeholder="Why this version exists — required to publish."
                  className={cn(fieldClasses, "placeholder:text-muted-foreground h-auto w-full resize-y px-3 py-2")}
                />
              </label>
            </div>
          )}

          <div className="bg-card shadow-soft rounded-xl border p-4">
            <ScoringEditor config={draft} onChange={edit} disabled={!editable || busy} resetKey={resetKey} />
          </div>
        </div>

        {/* ── right: the range and the live preview ── */}
        <div className="min-w-0 space-y-4">
          <div className="bg-card shadow-soft flex flex-wrap items-end gap-2 rounded-xl border p-3">
            <label className="block space-y-1">
              <span className="text-muted-foreground block text-[11.5px] font-medium">Preview over</span>
              <Select
                value={custom ? "__custom" : monthKey}
                onChange={(e) => {
                  if (e.target.value === "__custom") setCustom({ from: range.from, to: range.to });
                  else {
                    setCustom(null);
                    setMonthKey(e.target.value);
                  }
                }}
                className="w-52"
                aria-label="Preview month"
              >
                {months.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
                <option value="__custom">Custom range…</option>
              </Select>
            </label>
            {custom && (
              <CustomRange value={custom} onApply={(v) => setCustom(v)} />
            )}
            <span className="text-muted-foreground ml-auto text-[11.5px]" aria-live="polite">
              {loading ? "Loading classes…" : `${payload?.rows.length ?? 0} classes · ${rangeLabel}`}
            </span>
          </div>
          <ScoringPreview
            config={draft}
            baseline={baseline}
            baselineLabel={baselineLabel}
            rows={payload?.rows ?? []}
            globalPrior={payload?.global_prior ?? { rating: null, approval: null }}
            from={range.from}
            to={range.to}
            loading={loading}
            error={payload?.error ?? null}
            onStats={setStats}
          />
        </div>
      </div>

      {versions.length > 0 && (
        <section className="space-y-3" aria-labelledby="versions-title">
          <h2 id="versions-title" className="text-[15px] font-semibold tracking-[-0.01em]">
            Versions <span className="text-muted-foreground font-normal">· {versions.length}</span>
          </h2>
          <VersionsTable
            versions={versions}
            selectedId={selected.id}
            mode={mode}
            busy={busy}
            onOpen={openVersion}
            onNewDraftFrom={(v) => newDraftFrom(v)}
            onRollback={(v) => setDialog({ kind: "rollback", v })}
            onDelete={(v) => setDialog({ kind: "delete", v })}
          />
          <ConfigDiff versions={versions} />
        </section>
      )}

      <NoteDialog
        open={dialog?.kind === "publish"}
        title="Publish this version"
        description="Re-scores every class in the database in one step and writes a history row per class. Rolling back = activating the previous version."
        confirmLabel="Publish and re-score"
        requireName
        initialName={meta.name}
        initialNote={meta.note}
        summary={stats}
        rangeLabel={rangeLabel}
        busy={busy}
        onConfirm={onPublish}
        onClose={() => setDialog(null)}
      />
      <NoteDialog
        open={dialog?.kind === "rollback"}
        title={dialog?.kind === "rollback" ? `Roll back to v${dialog.v.version} · ${dialog.v.name}` : "Roll back"}
        description="Activates this earlier version again and re-scores every class with it."
        confirmLabel="Roll back and re-score"
        busy={busy}
        destructive
        onConfirm={(v) => dialog?.kind === "rollback" && onRollback(dialog.v, v.note)}
        onClose={() => setDialog(null)}
      />
      <NoteDialog
        open={dialog?.kind === "propose"}
        title="Propose to admin"
        description="Saves your settings as a draft with your note. The live score does not change until an admin publishes it."
        confirmLabel="Send proposal"
        requireName
        initialName={meta.name.replace(/\s*\(draft\)$/, "")}
        summary={stats}
        rangeLabel={rangeLabel}
        busy={busy}
        onConfirm={onPropose}
        onClose={() => setDialog(null)}
      />
      <ConfirmDialog
        open={dialog?.kind === "delete"}
        title={dialog?.kind === "delete" ? `Delete draft v${dialog.v.version}?` : "Delete draft"}
        description="Only drafts can be deleted. Published versions stay for the audit trail."
        confirmLabel="Delete draft"
        destructive
        busy={busy}
        onConfirm={() => dialog?.kind === "delete" && onDelete(dialog.v)}
        onClose={() => setDialog(null)}
      />
    </div>
  );
}

function CustomRange({ value, onApply }: { value: { from: string; to: string }; onApply: (v: { from: string; to: string }) => void }) {
  const [from, setFrom] = React.useState(value.from);
  const [to, setTo] = React.useState(value.to);
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(from) && /^\d{4}-\d{2}-\d{2}$/.test(to) && from <= to;
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onApply({ from, to });
      }}
    >
      <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From date" className="w-[9.75rem]" />
      <span className="text-muted-foreground pb-2 text-sm">to</span>
      <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date" className="w-[9.75rem]" />
      <Button type="submit" size="sm" variant="outline" disabled={!valid}>
        Apply
      </Button>
    </form>
  );
}
