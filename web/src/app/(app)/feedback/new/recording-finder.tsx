"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { findRecording, type FindRecordingResult, type RecordingMatch } from "../recording-actions";

type ClassType = "live_class" | "ars";
type Connection = "ok" | "expired" | "not_set" | "unknown" | "error" | "empty";

const CATEGORY_LABEL: Record<string, string> = {
  live_class: "Live class",
  ars: "Assignment review",
  coaching: "Technical coaching",
};

const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" })
    : "no date";
const fmtDuration = (min: number | null) =>
  min == null ? null : min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min` : `${min} min`;

/** One recording is the clear answer when it matches strongly and nothing else comes close. Two
 *  recordings of the same class on the same day (two cohorts, or a re-upload) are not guessed
 *  between: the PM picks. */
function clearWinner(matches: RecordingMatch[]): RecordingMatch | null {
  const [top, second] = matches;
  if (!top || top.score < 0.9) return null;
  if (second && second.score > top.score - 0.25) return null;
  return top;
}

const MANUAL_STEPS = (
  <details className="mt-2 text-xs">
    <summary className="text-muted-foreground hover:text-foreground cursor-pointer">How to find the link by hand</summary>
    <ol className="text-muted-foreground mt-1.5 list-decimal space-y-0.5 pl-5">
      <li>Sign in to UpLevel and open <b>Videos</b>.</li>
      <li>Search the instructor&apos;s name (one word is enough).</li>
      <li>Pick the row whose class name, date and type (Live Class or Assignment Review) all match.</li>
      <li>Copy its Vimeo link and paste it below.</li>
    </ol>
  </details>
);

function MatchCard({
  m, chosen, onUse, expectedType,
}: { m: RecordingMatch; chosen: boolean; onUse: (link: string) => void; expectedType: ClassType }) {
  const wrongType = m.category && (m.category === "live_class" || m.category === "ars") && m.category !== expectedType;
  return (
    <div className={cn("bg-card rounded-md border p-2.5", chosen && "border-success/60")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[13px] leading-snug font-medium break-words">{m.name || m.topic}</div>
          <div className="text-muted-foreground mt-0.5 text-xs" data-numeric>
            {fmtDate(m.class_date)}
            {m.category && <> · {CATEGORY_LABEL[m.category] ?? m.category}</>}
            {fmtDuration(m.duration_min) && <> · {fmtDuration(m.duration_min)}</>}
            {" · "}
            <a href={m.vimeo_link} target="_blank" rel="noreferrer" className="text-primary hover:underline">
              vimeo.com/{m.vimeo_id}
            </a>
          </div>
          {wrongType && (
            <div className="text-warning mt-1 text-xs font-medium">
              This is a {CATEGORY_LABEL[m.category!]?.toLowerCase()} recording; the class is set as {CATEGORY_LABEL[expectedType].toLowerCase()}.
            </div>
          )}
        </div>
        {chosen ? (
          <span className="text-success flex shrink-0 items-center gap-1 text-xs font-medium">
            <CheckCircle2 className="size-3.5" aria-hidden /> In use
          </span>
        ) : (
          <Button type="button" size="sm" variant="outline" className="shrink-0" onClick={() => onUse(m.vimeo_link)}>
            Use this
          </Button>
        )}
      </div>
      {m.reasons.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {m.reasons.slice(0, 4).map((r) => (
            <span key={r} className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[11px]">{r}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/** The recording, found for you. Opened from the queue, the search starts by itself; typed by
 *  hand, it starts once the class name and date are filled and you stop typing. One clear match
 *  fills the Vimeo link and says which recording it is, so you can check it at a glance; several
 *  candidates are listed for you to pick. It never overwrites a link you typed yourself. */
export function RecordingFinder({
  topic, instructor, classDate, classType, connection, currentLink, onUse, isAdmin,
}: {
  topic: string;
  instructor: string;
  classDate: string;
  classType: ClassType;
  connection: Connection;
  currentLink: string;
  onUse: (link: string) => void;
  isAdmin: boolean;
}) {
  const [result, setResult] = React.useState<FindRecordingResult | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [slow, setSlow] = React.useState(false);
  const [showAll, setShowAll] = React.useState(false);
  const [searchedKey, setSearchedKey] = React.useState<string | null>(null);
  const requestId = React.useRef(0);
  const linkRef = React.useRef(currentLink);
  linkRef.current = currentLink;

  const key = `${topic.trim()}|${instructor.trim()}|${classDate}|${classType}`;
  const ready = topic.trim().length > 0 && classDate.length === 10;
  // Details already there when the form opens (a click from the queue): search at once. Typed by
  // hand: wait until typing stops, so a half-typed name is never searched.
  const openedWithDetails = React.useRef(ready);

  const search = React.useCallback(async () => {
    if (!ready) return;
    const id = ++requestId.current;
    openedWithDetails.current = false;
    setSearching(true);
    setSlow(false);
    setShowAll(false);
    setSearchedKey(key);
    const slowTimer = window.setTimeout(() => setSlow(true), 8000);
    const r = await findRecording({ topic, instructor, classDate, classType });
    window.clearTimeout(slowTimer);
    if (id !== requestId.current) return;                 // the details changed while we looked
    setSearching(false);
    setResult(r);
    const winner = r.status === "ok" ? clearWinner(r.matches) : null;
    if (winner && !linkRef.current.trim()) onUse(winner.vimeo_link);
  }, [ready, key, topic, instructor, classDate, classType, onUse]);

  // Search by itself once the details are there and have stopped changing, unless a link is
  // already in the box or the connection is known to be missing or expired.
  React.useEffect(() => {
    if (!ready || searchedKey === key || currentLink.trim()) return;
    if (connection === "not_set" || connection === "expired") return;
    const delay = openedWithDetails.current ? 0 : 900;
    const t = window.setTimeout(() => void search(), delay);
    return () => window.clearTimeout(t);
  }, [ready, key, searchedKey, currentLink, connection, search]);

  const winner = result?.status === "ok" ? clearWinner(result.matches) : null;
  const inUse = (m: RecordingMatch) => currentLink.trim() === m.vimeo_link;
  // The class details were changed after the lookup: whatever it found may no longer be this class.
  const stale = Boolean(result) && !searching && searchedKey !== null && searchedKey !== key;
  const neverConnected = connection === "not_set" || result?.status === "not_connected";

  const box = "rounded-lg border p-3 text-sm";
  const verb = neverConnected ? "connect" : "reconnect";
  const reconnect = isAdmin ? (
    <> <Link href="/admin/uplevel" className="text-primary font-medium hover:underline">{neverConnected ? "Connect" : "Reconnect"} it on Admin › UpLevel</Link> (two minutes).</>
  ) : (
    <> Ask an admin to {verb} it on Admin › UpLevel.</>
  );

  // Nothing to search with yet.
  if (!ready && !result) {
    return (
      <div className={cn(box, "text-muted-foreground bg-muted/30")}>
        <div className="flex items-center gap-2">
          <Search className="size-4" aria-hidden />
          Fill in the class name and date, and the recording is looked up in UpLevel for you.
        </div>
      </div>
    );
  }

  // The connection is missing or expired and nobody has tried since.
  if (!result && !searching && (connection === "not_set" || connection === "expired")) {
    return (
      <div className={cn(box, "bg-muted/30")} aria-live="polite">
        <div className="flex items-start gap-2">
          <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <div className="font-medium">
              {connection === "not_set" ? "Automatic lookup is off: UpLevel is not connected." : "The UpLevel connection has expired."}
            </div>
            <div className="text-muted-foreground mt-0.5 text-xs">
              Paste the link by hand for now.{reconnect}
              {connection === "expired" && (
                <> <button type="button" className="text-primary hover:underline" onClick={() => void search()}>Try anyway</button>.</>
              )}
            </div>
            {MANUAL_STEPS}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2" aria-live="polite">
      {stale && (
        <div className={cn(box, "border-warning/40 bg-warning/5 flex flex-wrap items-center justify-between gap-2")}>
          <span>
            You changed the class details after the lookup
            {currentLink.trim() ? ", so the link below may belong to a different class." : "."}
          </span>
          <Button type="button" size="sm" variant="outline" onClick={() => void search()}>
            <RefreshCw className="size-3.5" aria-hidden /> Search again
          </Button>
        </div>
      )}
      {searching && (
        <div className={cn(box, "bg-muted/30 flex items-start gap-2")}>
          <Loader2 className="text-muted-foreground mt-0.5 size-4 shrink-0 animate-spin" aria-hidden />
          <div>
            <div>
              Looking in UpLevel for <b>{topic.trim()}</b>
              {instructor.trim() && <> · {instructor.trim()}</>} · {fmtDate(classDate)}…
            </div>
            {slow && <div className="text-muted-foreground mt-0.5 text-xs">Waking the analysis service; this can take up to a minute.</div>}
          </div>
        </div>
      )}

      {!searching && result?.status === "ok" && winner && (
        <div className={cn(box, "border-success/40 bg-success/5")}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 font-medium">
              <CheckCircle2 className="text-success size-4" aria-hidden />
              {inUse(winner) ? "Found in UpLevel and filled in. Check it is the right class:" : "Found in UpLevel:"}
            </div>
            <Button type="button" size="sm" variant="ghost" onClick={() => void search()} aria-label="Search UpLevel again">
              <RefreshCw className="size-3.5" aria-hidden />
            </Button>
          </div>
          <MatchCard m={winner} chosen={inUse(winner)} onUse={onUse} expectedType={classType} />
          {result.matches.length > 1 && (
            <button type="button" className="text-muted-foreground hover:text-foreground mt-2 text-xs"
                    onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Hide the other recordings" : `Not this one? ${result.matches.length - 1} other recording${result.matches.length > 2 ? "s" : ""} came close`}
            </button>
          )}
          {showAll && (
            <div className="mt-2 space-y-1.5">
              {result.matches.slice(1).map((m) => (
                <MatchCard key={m.vimeo_id} m={m} chosen={inUse(m)} onUse={onUse} expectedType={classType} />
              ))}
            </div>
          )}
        </div>
      )}

      {!searching && result?.status === "ok" && !winner && (
        <div className={cn(box, "border-warning/40 bg-warning/5")}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="font-medium">
              {result.matches[0]?.score >= 0.9
                ? `${result.matches.filter((m) => m.score >= 0.9).length} recordings match this class on the same day. Pick the right one:`
                : "No certain match. These are the closest recordings; pick one only if it is the class:"}
            </div>
            <Button type="button" size="sm" variant="ghost" onClick={() => void search()} aria-label="Search UpLevel again">
              <RefreshCw className="size-3.5" aria-hidden />
            </Button>
          </div>
          <div className="space-y-1.5">
            {result.matches.slice(0, 4).map((m) => (
              <MatchCard key={m.vimeo_id} m={m} chosen={inUse(m)} onUse={onUse} expectedType={classType} />
            ))}
          </div>
        </div>
      )}

      {!searching && result && result.status !== "ok" && (
        <div className={cn(box, "bg-muted/30")}>
          <div className="flex items-start gap-2">
            <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-hidden />
            <div className="min-w-0">
              <div className="font-medium">
                {result.status === "none" && "No recording for this class in UpLevel yet."}
                {result.status === "not_connected" && "Automatic lookup is off: UpLevel is not connected."}
                {result.status === "expired" && "The UpLevel connection has expired."}
                {result.status === "unreachable" && "Could not look it up just now."}
                {result.status === "invalid" && (result.message ?? "The class details are not enough to search.")}
              </div>
              <div className="text-muted-foreground mt-0.5 text-xs">
                {result.status === "none" && <>Recordings usually appear a few hours after the class ends. Check the class name, date and instructor above, or paste the link by hand. </>}
                {(result.status === "not_connected" || result.status === "expired") && <>Paste the link by hand for now.{reconnect} </>}
                {result.status === "unreachable" && (
                  <>{result.message ? result.message.charAt(0).toUpperCase() + result.message.slice(1) : "Try again in a moment."} </>
                )}
                {result.status !== "invalid" && (
                  <button type="button" className="text-primary hover:underline" onClick={() => void search()}>Search again</button>
                )}
              </div>
              {result.status !== "unreachable" && result.status !== "invalid" && MANUAL_STEPS}
            </div>
          </div>
        </div>
      )}

      {!searching && !result && ready && (
        <Button type="button" size="sm" variant="outline" onClick={() => void search()}>
          <Search className="size-3.5" aria-hidden /> Find the recording in UpLevel
        </Button>
      )}
    </div>
  );
}
