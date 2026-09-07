"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableNum, TableRow } from "@/components/ui/table";
import type { CourseRow, RawTopic, TopicAliasRow, TopicRow } from "@/lib/admin";
import { mapTopicAlias, removeTopicAlias } from "@/app/(app)/c/[course]/settings/actions";
import { Typeahead, type TypeaheadOption } from "../typeahead";

/** Modules = canonical names for the class names the sheet records. Left: raw names not yet
 *  mapped, each with a typeahead over this course's modules (or "Create …"). Right: the aliases
 *  already in place. */
export function ModulesTab({
  course,
  topics,
  aliases,
  raw,
  canEdit,
  error,
}: {
  course: CourseRow;
  topics: TopicRow[];
  aliases: TopicAliasRow[];
  raw: RawTopic[];
  canEdit: boolean;
  error: string | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [picks, setPicks] = React.useState<Record<string, TypeaheadOption | null>>({});
  const [creating, setCreating] = React.useState<Record<string, string>>({});
  const [gone, setGone] = React.useOptimistic<Set<string>, string>(new Set(), (p, k) => new Set(p).add(k));
  const options = React.useMemo(() => topics.map((t) => ({ id: t.id, label: t.name })), [topics]);
  const aliased = new Set(aliases.map((a) => a.alias.toLowerCase()));
  const topicName = (id: string) => topics.find((t) => t.id === id)?.name ?? "module";
  const unmapped = raw.filter((r) => !aliased.has(r.topic.toLowerCase()) && !gone.has(r.topic) && !topics.some((t) => t.name.toLowerCase() === r.topic.toLowerCase()));

  const map = (r: RawTopic) => {
    const pick = picks[r.topic];
    const newName = creating[r.topic];
    if (!pick && !newName) return;
    startTransition(async () => {
      setGone(r.topic);
      const res = await mapTopicAlias({ courseId: course.id, alias: r.topic, topicId: pick?.id ?? null, newTopicName: pick ? null : newName });
      if (!res.ok) {
        toast.error("Could not map", { description: res.error });
        return;
      }
      toast.success(`“${r.topic}” → ${pick?.label ?? newName}`);
      router.refresh();
    });
  };

  const remove = (a: TopicAliasRow) =>
    startTransition(async () => {
      const res = await removeTopicAlias({ courseId: course.id, id: a.id });
      if (!res.ok) {
        toast.error("Could not remove", { description: res.error });
        return;
      }
      toast.success("Alias removed");
      router.refresh();
    });

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        <div className="px-4 pt-4 pb-3">
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">
            Class names without a module <span className="text-muted-foreground font-normal">· {unmapped.length}</span>
          </h3>
          <p className="text-muted-foreground text-[11.5px]">As recorded on rated classes in the last 12 months. Map each to a module once — it sticks for every sync.</p>
        </div>
        {error && <p className="text-muted-foreground border-t px-4 py-2 text-[12px]">Modules are not available yet ({error}) — they arrive with migration 0017.</p>}
        {unmapped.length === 0 ? (
          <p className="text-muted-foreground border-t px-4 py-6 text-center text-[13px]">Every class name maps to a module.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Recorded name</TableHead>
                <TableHead className="text-right">Classes</TableHead>
                {canEdit && <TableHead className="min-w-64">Module</TableHead>}
                {canEdit && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {unmapped.slice(0, 60).map((r) => (
                <TableRow key={r.topic}>
                  <TableCell className="max-w-72 truncate font-medium" title={r.topic}>{r.topic}</TableCell>
                  <TableNum>{r.classes}</TableNum>
                  {canEdit && (
                    <TableCell>
                      <Typeahead
                        options={options}
                        value={picks[r.topic] ?? null}
                        onChange={(v) => {
                          setPicks((p) => ({ ...p, [r.topic]: v }));
                          if (v) setCreating((c) => ({ ...c, [r.topic]: "" }));
                        }}
                        onCreate={(t) => {
                          setPicks((p) => ({ ...p, [r.topic]: null }));
                          setCreating((c) => ({ ...c, [r.topic]: t }));
                        }}
                        placeholder="Pick or type a module…"
                        ariaLabel={`Module for ${r.topic}`}
                        disabled={pending || !!error}
                      />
                      {creating[r.topic] && !picks[r.topic] && <span className="text-muted-foreground block text-[11px]">Will create “{creating[r.topic]}”</span>}
                    </TableCell>
                  )}
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button type="button" size="sm" variant="outline" onClick={() => map(r)} disabled={pending || !!error || (!picks[r.topic] && !creating[r.topic])}>
                        Map
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
        <div className="px-4 pt-4 pb-3">
          <h3 className="text-[13px] font-semibold tracking-[-0.01em]">
            Modules and aliases <span className="text-muted-foreground font-normal">· {topics.length} modules · {aliases.length} aliases</span>
          </h3>
        </div>
        {aliases.length === 0 ? (
          <p className="text-muted-foreground border-t px-4 py-6 text-center text-[13px]">No aliases yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Alias</TableHead>
                <TableHead>Module</TableHead>
                {canEdit && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {aliases.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="max-w-72 truncate" title={a.alias}>{a.alias}</TableCell>
                  <TableCell className="font-medium">{a.topic_name ?? topicName(a.topic_id)}</TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button type="button" size="sm" variant="ghost" onClick={() => remove(a)} disabled={pending}>
                        Remove
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
