"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import { SortButton, useSortable, type SortSpec } from "@/components/ui/sortable";
import type { UnresolvedName } from "@/lib/admin";
import { addAliasToInstructor, createInstructorForName } from "@/app/(app)/admin/actions";
import { Typeahead, type TypeaheadOption } from "../typeahead";

const pretty = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—");

type SortKey = "name" | "classes" | "last";
const SPEC: SortSpec<UnresolvedName, SortKey> = {
  name: { value: (n) => n.name, first: "asc" },
  classes: { value: (n) => n.classes, first: "desc" },
  last: { value: (n) => n.last, first: "desc" },
};

/** Raw instructor spellings no instructor row claims. Each row: link it to an existing
 *  instructor (typeahead → Add alias) or create the instructor from the spelling. The most
 *  classes come first; any heading re-sorts. */
export function UnresolvedPanel({ names, instructors }: { names: UnresolvedName[]; instructors: { id: string; name: string }[] }) {
  const router = useRouter();
  const [gone, setGone] = React.useOptimistic<Set<string>, string>(new Set(), (prev, n) => new Set(prev).add(n));
  const [pending, startTransition] = React.useTransition();
  const [picks, setPicks] = React.useState<Record<string, TypeaheadOption | null>>({});
  const [showAll, setShowAll] = React.useState(false);
  const options = React.useMemo(() => instructors.map((i) => ({ id: i.id, label: i.name })), [instructors]);
  const visible = React.useMemo(() => names.filter((n) => !gone.has(n.name)), [names, gone]);
  const { sorted, state: sort, toggle } = useSortable(visible, SPEC, { key: "classes", dir: "desc" });
  const shown = showAll ? sorted : sorted.slice(0, 30);

  const link = (raw: UnresolvedName) => {
    const pick = picks[raw.name];
    if (!pick) return;
    startTransition(async () => {
      setGone(raw.name);
      const r = await addAliasToInstructor({ alias: raw.name, instructorId: pick.id });
      if (!r.ok) {
        toast.error("Could not add the alias", { description: r.error });
        return;
      }
      toast.success(`“${raw.name}” → ${pick.label}`, { description: `${raw.classes} classes now count for ${pick.label}.` });
      router.refresh();
    });
  };

  const create = (raw: UnresolvedName) =>
    startTransition(async () => {
      setGone(raw.name);
      const r = await createInstructorForName({ name: raw.name });
      if (!r.ok) {
        toast.error("Could not create the instructor", { description: r.error });
        return;
      }
      toast.success(`Created ${raw.name}`, { description: "The spelling is linked; future syncs resolve it automatically." });
      router.refresh();
    });

  return (
    <section className="bg-card shadow-soft overflow-hidden rounded-xl border" aria-labelledby="unres-title">
      <div className="px-4 pt-4 pb-3">
        <h2 id="unres-title" className="text-[14px] font-semibold tracking-[-0.01em]">
          Unresolved names <span className="text-muted-foreground font-normal">· {visible.length}</span>
        </h2>
        <p className="text-muted-foreground text-[11.5px]">Spellings on rated classes that no instructor claims. First-name-only entries need someone who knows the team.</p>
      </div>
      {visible.length === 0 ? (
        <p className="text-muted-foreground border-t px-4 py-6 text-center text-[13px]">Every recorded spelling is linked to an instructor.</p>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <SortButton sortKey="name" state={sort} onToggle={toggle}>Recorded as</SortButton>
                <SortButton sortKey="classes" state={sort} onToggle={toggle} align="right">Classes</SortButton>
                <SortButton sortKey="last" state={sort} onToggle={toggle}>Last seen</SortButton>
                <TableHead className="min-w-64">Link to an existing instructor</TableHead>
                <TableHead className="text-right">Or</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((n) => (
                <TableRow key={n.name}>
                  <TableCell className="font-medium">{n.name}</TableCell>
                  <TableNum>{n.classes}</TableNum>
                  <TableCell className="whitespace-nowrap">{pretty(n.last)}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Typeahead
                        options={options}
                        value={picks[n.name] ?? null}
                        onChange={(v) => setPicks((p) => ({ ...p, [n.name]: v }))}
                        placeholder="Type a name…"
                        ariaLabel={`Instructor for ${n.name}`}
                        className="w-56"
                        disabled={pending}
                      />
                      <Button type="button" size="sm" variant="outline" onClick={() => link(n)} disabled={pending || !picks[n.name]}>
                        Add alias
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button type="button" size="sm" variant="ghost" onClick={() => create(n)} disabled={pending}>
                      Create instructor
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {visible.length > 30 && (
            <div className="border-t px-4 py-2.5">
              <button type="button" onClick={() => setShowAll((v) => !v)} className="text-primary text-[12px] font-medium hover:underline">
                {showAll ? "Show first 30" : `Show all ${visible.length}`}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
