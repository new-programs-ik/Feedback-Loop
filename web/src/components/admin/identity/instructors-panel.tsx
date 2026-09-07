"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, GitMerge, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { InstructorRow, MergeRow } from "@/lib/admin";
import { getMergePreview, mergeInstructorIdentities, undoInstructorMerge } from "@/app/(app)/admin/actions";
import { ConfirmDialog } from "../confirm-dialog";
import { Typeahead, type TypeaheadOption } from "../typeahead";

const when = (iso: string) => new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });

/** The instructor directory's admin side: search, merge two identities (with a preview of what
 *  moves), and the recent merges with a 30-day Undo. Merges are soft — the duplicate row stays,
 *  an alias is recorded, every moved row id is stored, so Undo simply replays it. */
export function InstructorsPanel({ instructors, merges }: { instructors: InstructorRow[]; merges: MergeRow[] }) {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [from, setFrom] = React.useState<TypeaheadOption | null>(null);
  const [into, setInto] = React.useState<TypeaheadOption | null>(null);
  const [preview, setPreview] = React.useState<{ id: string; ratings: number; classes: number; aliases: number | null } | null>(null);
  const [confirm, setConfirm] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const options = React.useMemo(() => instructors.map((i) => ({ id: i.id, label: i.name })), [instructors]);
  const q = query.trim().toLowerCase();
  const filtered = q ? instructors.filter((i) => i.name.toLowerCase().includes(q)) : instructors;

  const pickFrom = (v: TypeaheadOption | null) => {
    setFrom(v);
    if (!v) {
      setPreview(null);
      return;
    }
    startTransition(async () => {
      const r = await getMergePreview(v.id);
      if (r.ok) setPreview({ id: v.id, ...r.data });
    });
  };

  const merge = () =>
    startTransition(async () => {
      if (!from || !into) return;
      const r = await mergeInstructorIdentities({ fromId: from.id, intoId: into.id });
      setConfirm(false);
      if (!r.ok) {
        toast.error("Merge failed", { description: r.error });
        return;
      }
      toast.success(`Merged “${from.label}” into ${into.label}`, { description: "Undo is available for 30 days below." });
      setFrom(null);
      setInto(null);
      setPreview(null);
      router.refresh();
    });

  const undo = (m: MergeRow) =>
    startTransition(async () => {
      const r = await undoInstructorMerge({ mergeId: m.id });
      if (!r.ok) {
        toast.error("Undo failed", { description: r.error });
        return;
      }
      toast.success(`Undid the merge of “${m.from_name}”`);
      router.refresh();
    });

  const ready = !!from && !!into && from.id !== into.id;
  const showPreview = preview && from && preview.id === from.id;

  return (
    <section className="bg-card shadow-soft rounded-xl border" aria-labelledby="ins-title">
      <div className="px-4 pt-4 pb-3">
        <h2 id="ins-title" className="text-[14px] font-semibold tracking-[-0.01em]">
          Instructors <span className="text-muted-foreground font-normal">· {instructors.length}</span>
        </h2>
        <p className="text-muted-foreground text-[11.5px]">Search the directory, or merge two identities when the matcher did not spot them.</p>
      </div>

      <div className="grid gap-4 border-t px-4 py-4 lg:grid-cols-2">
        <div>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search instructors…" aria-label="Search instructors" className="mb-2" />
          <ul className="max-h-64 divide-y overflow-auto rounded-md border text-[13px]">
            {filtered.slice(0, 60).map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2 px-3 py-1.5">
                <span className="truncate">{i.name}</span>
                <span className="flex shrink-0 gap-1">
                  <button type="button" className="text-muted-foreground hover:text-foreground text-[11px] hover:underline" onClick={() => pickFrom({ id: i.id, label: i.name })}>
                    as duplicate
                  </button>
                  <span className="text-muted-foreground/50 text-[11px]">·</span>
                  <button type="button" className="text-muted-foreground hover:text-foreground text-[11px] hover:underline" onClick={() => setInto({ id: i.id, label: i.name })}>
                    keep
                  </button>
                </span>
              </li>
            ))}
            {filtered.length === 0 && <li className="text-muted-foreground px-3 py-4 text-center">No instructor matches.</li>}
            {filtered.length > 60 && <li className="text-muted-foreground px-3 py-1.5 text-[11px]">…and {filtered.length - 60} more — narrow the search.</li>}
          </ul>
        </div>

        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-end">
            <label className="block space-y-1">
              <span className="text-muted-foreground block text-[11.5px] font-medium">Merge this (duplicate)</span>
              <Typeahead options={options} value={from} onChange={pickFrom} placeholder="Type a name…" ariaLabel="Duplicate instructor" disabled={pending} />
            </label>
            <ArrowRight className="text-muted-foreground mx-auto mb-2.5 hidden size-4 sm:block" aria-hidden />
            <label className="block space-y-1">
              <span className="text-muted-foreground block text-[11.5px] font-medium">Into this (keep)</span>
              <Typeahead options={options} value={into} onChange={setInto} placeholder="Type a name…" ariaLabel="Instructor to keep" disabled={pending} />
            </label>
          </div>
          <div className="surface-inset rounded-md border px-3 py-2 text-[12px]" aria-live="polite">
            {showPreview ? (
              <>
                Moves <b data-numeric>{preview.ratings}</b> rated {preview.ratings === 1 ? "class" : "classes"}, <b data-numeric>{preview.classes}</b> analysed{" "}
                {preview.classes === 1 ? "class" : "classes"}
                {preview.aliases != null ? (
                  <>
                    {" "}and <b data-numeric>{preview.aliases}</b> {preview.aliases === 1 ? "alias" : "aliases"}
                  </>
                ) : null}{" "}
                from “{from!.label}”{into ? ` to ${into.label}` : ""}. The duplicate name stays as an alias.
              </>
            ) : (
              <span className="text-muted-foreground">Pick the duplicate to see what would move.</span>
            )}
          </div>
          <Button type="button" onClick={() => setConfirm(true)} disabled={!ready || pending}>
            <GitMerge aria-hidden /> Merge
          </Button>
        </div>
      </div>

      <div className="border-t">
        <div className="px-4 pt-3 pb-2">
          <h3 className="text-[12.5px] font-semibold">Recent merges</h3>
        </div>
        {merges.length === 0 ? (
          <p className="text-muted-foreground px-4 pb-4 text-[12.5px]">No merges yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Merged</TableHead>
                <TableHead>Into</TableHead>
                <TableHead>By · when</TableHead>
                <TableHead>Moved</TableHead>
                <TableHead className="text-right">Undo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {merges.map((m) => {
                const moved = m.moved ?? {};
                const parts = Object.entries(moved)
                  .filter(([, v]) => Array.isArray(v) || typeof v === "number")
                  .map(([k, v]) => `${Array.isArray(v) ? v.length : v} ${k.replace(/_/g, " ")}`);
                return (
                  <TableRow key={m.id} className={m.undone_at ? "opacity-60" : undefined}>
                    <TableCell className="font-medium">{m.from_name}</TableCell>
                    <TableCell>{m.into_name}</TableCell>
                    <TableCell className="text-[12px] whitespace-nowrap">
                      {m.performed_by_name ?? "—"} · {when(m.performed_at)}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-[12px]">{parts.length ? parts.join(" · ") : "—"}</TableCell>
                    <TableCell className="text-right">
                      {m.undone_at ? (
                        <span className="text-muted-foreground text-[11px]">undone {when(m.undone_at)}</span>
                      ) : m.undoable ? (
                        <Button type="button" size="sm" variant="outline" onClick={() => undo(m)} disabled={pending}>
                          <Undo2 aria-hidden /> Undo
                        </Button>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">older than 30 days</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </div>

      <ConfirmDialog
        open={confirm}
        title={from && into ? `Merge “${from.label}” into ${into.label}?` : "Merge"}
        description="Every class and alias on the duplicate moves to the kept name. The duplicate spelling is kept as an alias so future syncs resolve it. Undo stays available for 30 days."
        confirmLabel="Merge"
        busy={pending}
        onConfirm={merge}
        onClose={() => setConfirm(false)}
      />
    </section>
  );
}
