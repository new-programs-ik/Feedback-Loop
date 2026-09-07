"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { ScoringConfigRow } from "@/lib/admin";
import { BandMix } from "./band-mix";

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" }) : "—";

/** Every stored version: number, key, name, status, who/when, and the band mix it produced when
 *  it was applied (from class_score_history). Row actions depend on status. */
export function VersionsTable({
  versions,
  selectedId,
  mode,
  busy,
  onOpen,
  onNewDraftFrom,
  onRollback,
  onDelete,
}: {
  versions: ScoringConfigRow[];
  selectedId: string | null;
  mode: "admin" | "whatif";
  busy: boolean;
  onOpen: (v: ScoringConfigRow) => void;
  onNewDraftFrom: (v: ScoringConfigRow) => void;
  onRollback: (v: ScoringConfigRow) => void;
  onDelete: (v: ScoringConfigRow) => void;
}) {
  return (
    <div className="bg-card shadow-soft overflow-hidden rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-14">Ver.</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>By · when</TableHead>
            <TableHead className="min-w-40">Band mix at activation</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((v) => {
            const selected = v.id === selectedId;
            return (
              <TableRow key={v.id} className={cn(selected && "bg-primary/[0.04]")} data-state={selected ? "selected" : undefined}>
                <TableCell data-numeric className="font-medium">v{v.version}</TableCell>
                <TableCell className="max-w-72">
                  <button type="button" onClick={() => onOpen(v)} className="hover:text-primary truncate text-left font-medium hover:underline">
                    {v.name}
                  </button>
                  <div className="text-muted-foreground truncate text-[11px]">
                    {v.key ? <code className="font-mono">{v.key}</code> : null}
                    {v.note ? `${v.key ? " · " : ""}${v.note}` : ""}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={v.status === "active" ? "success" : v.status === "draft" ? "soft" : "outline"} className="capitalize">
                    {v.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-[12px] whitespace-nowrap">
                  <div>{v.created_by_name ?? "—"}</div>
                  <div className="text-muted-foreground text-[11px]">
                    {v.status === "active" ? `activated ${when(v.activated_at)}` : v.status === "retired" ? `retired ${when(v.retired_at)}` : `created ${when(v.created_at)}`}
                  </div>
                </TableCell>
                <TableCell>
                  {v.band_mix ? <BandMix counts={v.band_mix} compact /> : <span className="text-muted-foreground text-[11px]">never applied</span>}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <div className="inline-flex items-center gap-1">
                    <Button type="button" variant="ghost" size="sm" onClick={() => onOpen(v)} disabled={busy}>
                      {v.status === "draft" && mode === "admin" ? "Edit" : "Open"}
                    </Button>
                    {mode === "admin" && (
                      <>
                        <Button type="button" variant="ghost" size="sm" onClick={() => onNewDraftFrom(v)} disabled={busy}>
                          New draft
                        </Button>
                        {v.status === "retired" && (
                          <Button type="button" variant="outline" size="sm" onClick={() => onRollback(v)} disabled={busy}>
                            Roll back to this
                          </Button>
                        )}
                        {v.status === "draft" && (
                          <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => onDelete(v)} disabled={busy}>
                            Delete
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
