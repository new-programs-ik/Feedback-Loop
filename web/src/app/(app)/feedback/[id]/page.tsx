import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUser } from "@/lib/session";
import { createClient } from "@/lib/supabase/server";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, Loader2, AlertTriangle, SquarePlay } from "lucide-react";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { ReviewActions } from "./review-actions";
import { DeleteAnalysisButton, MarkSentButton, RetryButton } from "./action-buttons";
import { AutoRefresh } from "@/components/auto-refresh";
import { hrefIn } from "@/lib/workspace-shared";
import { confidenceLabel, findingLabel, reclassLabel, severityLabel } from "@/lib/labels";
import { CREDIT_BACK_MSG, NO_CREDIT_MSG, isCreditFailure } from "@/components/ai-credit-notice";
import { getIntegrationStatus } from "@/lib/integrations";

function sevVariant(s?: string): "destructive" | "warning" | "secondary" {
  return s === "major" ? "destructive" : s === "moderate" ? "warning" : "secondary";
}

type Evidence = { timestamp?: string; quote?: string; source?: string };
type Flag = { flag?: string; severity?: string; confidence?: string; evidence?: Evidence[] };
type ReviewRecord = {
  flag?: string; verdict?: string; from_severity?: string; to_severity?: string | null;
  anchor_rule?: string; reason?: string;
};
type VideoMeta = {
  video_used?: boolean; frames_analyzed?: number; frames_sampled?: number; video_error?: string | null;
};
type Result = {
  overall?: string;
  flags?: Flag[];
  feedback?: string;
  instructor_summary?: string;
  review?: ReviewRecord[];
  video?: VideoMeta;
  reclass?: { recommended?: string; reason?: string; deciding_flags?: string[]; softened_from?: string };
  // How much of the analysis was actually checked. Written by the engine into the result itself so
  // it reaches the database; a failed self-check used to be invisible here.
  verification?: {
    enabled?: boolean;
    ran?: boolean;
    findings_checked?: number;
    error?: string | null;
    second_vote_error?: string | null;
    prose_reconciled?: boolean;
    windows_lost?: number;
    replies_cut_off?: number;
  };
};

export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requireUser();
  const supabase = await createClient();
  // "Now" is read once per request.
  const nowMs = new Date().getTime();

  const { data: klass } = await supabase
    .from("classes")
    .select("*, courses(name, slug), instructors(name), analyses(*), feedback(*)")
    .eq("id", id)
    .single();
  if (!klass) notFound();

  let creator = "";
  if (klass.created_by) {
    const { data: p } = await supabase.from("profiles").select("full_name, email")
      .eq("user_id", klass.created_by as string).maybeSingle();
    creator = p?.full_name || (p?.email ?? "").split("@")[0] || "";
  }

  const analyses = (klass.analyses ?? []) as Array<Record<string, unknown>>;
  const analysis = analyses[analyses.length - 1];

  // `scheduled` = asked the worker, waiting for it to take the job; `analyzing` = the job is running.
  const inProgress = klass.status === "analyzing" || klass.status === "scheduled";
  let failReason = "";
  if (!analysis && !inProgress) {
    const { data: err } = await supabase
      .from("audit_log").select("detail").eq("class_id", id).eq("action", "error")
      .order("created_at", { ascending: false }).limit(1).maybeSingle();
    const d = (err?.detail ?? {}) as { message?: string; detail?: string };
    failReason = d.message || d.detail || "";
    // A refusal for want of Claude API credit: say whether the credit is still empty or is back,
    // so the page never tells a PM to recharge an account that has already been recharged.
    if (isCreditFailure(failReason)) {
      const credit = await getIntegrationStatus("claude_credit");
      failReason = credit?.state === "empty" ? NO_CREDIT_MSG : CREDIT_BACK_MSG;
    }
  }
  const feedbacks = (klass.feedback ?? []) as Array<Record<string, unknown>>;
  const feedback = feedbacks[feedbacks.length - 1];
  const result = (analysis?.result ?? {}) as Result;
  const draft = String(feedback?.edited_text ?? feedback?.draft_text ?? "");
  const summaryDraft = String(
    feedback?.summary_edited_text ?? feedback?.summary_draft_text ?? result.instructor_summary ?? "",
  );
  const fbStatus = String(feedback?.status ?? "draft");
  const done = fbStatus === "approved" || fbStatus === "sent";
  const wasSent = fbStatus === "sent";
  const ageMs = nowMs - new Date(String(klass.updated_at ?? klass.created_at)).getTime();
  const stuck =
    (klass.status === "analyzing" && ageMs > 30 * 60 * 1000) ||
    (klass.status === "scheduled" && ageMs > 10 * 60 * 1000);
  const canRetry = Boolean(klass.vimeo_link);
  const course = (klass.courses as { name?: string } | null)?.name ?? "—";
  const courseSlug = (klass.courses as { slug?: string } | null)?.slug ?? null;
  const instructor = (klass.instructors as { name?: string } | null)?.name ?? "—";
  const rating = klass.rating as number | null;
  const reclass = result.reclass;
  const flags = result.flags ?? [];
  const review = result.review ?? [];
  // Whether the self-check actually ran. Written into the result by the engine, so it
  // survives into the database - it used to live only in the worker's memory.
  const verification = result.verification;

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="icon">
          <Link href={courseSlug ? hrefIn(courseSlug, "/feedback") : "/feedback"} aria-label="Back to this course's analyses">
            <ArrowLeft className="size-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{String(klass.topic)}</h1>
            <Badge variant="outline">{klass.session_type === "ars" ? "ARS" : "Live"}</Badge>
            {/* Trust tag: was the recording actually part of this analysis? */}
            {analysis && (
              result.video?.video_used ? (
                <Badge variant="success" title={`${result.video.frames_analyzed} frames sampled from the recording`}>
                  🎬 Video verified · {result.video.frames_analyzed} frames
                </Badge>
              ) : (
                <Badge variant="outline"
                       title={result.video?.video_error ? `Video skipped: ${result.video.video_error}` : "The recording was not analyzed"}>
                  Transcript only
                </Badge>
              )
            )}
            {analysis && (
              verification?.ran ? (
                <Badge variant="secondary"
                       title={`${verification.findings_checked} finding(s) went through a second, adversarial review`}>
                  ✓ Self-checked
                </Badge>
              ) : verification?.error ? (
                <Badge variant="destructive"
                       title={`The self-check could not run: ${verification.error}. The findings below were NOT double-checked.`}>
                  Not self-checked
                </Badge>
              ) : verification && verification.findings_checked === 0 ? (
                <Badge variant="outline" title="No finding was serious enough to need a second review">
                  Nothing to self-check
                </Badge>
              ) : review.length > 0 ? (
                <Badge variant="secondary" title="Every serious finding got a second, adversarial review">
                  ✓ Self-checked
                </Badge>
              ) : null
            )}
            {verification?.prose_reconciled === false && (
              <Badge variant="warning"
                     title="The tidy-up that removes wording resting on a dropped finding did not run. Read the draft against the self-check list before sending it.">
                Draft not tidied
              </Badge>
            )}
            {verification?.windows_lost ? (
              <Badge variant="warning"
                     title={`${verification.windows_lost} part(s) of the class could not be read, so they were not analysed.`}>
                {verification.windows_lost} part(s) of the class unread
              </Badge>
            ) : null}
          </div>
          <p className="text-muted-foreground flex flex-wrap items-center gap-x-1.5 text-sm">
            <span>
              {course} · {instructor} · {String(klass.class_date)}
              {rating != null && <> · rating <strong>{Number(rating).toFixed(2)}</strong></>}
              {creator && <> · by {creator}</>}
            </span>
            {klass.vimeo_link && (
              <a
                href={String(klass.vimeo_link)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary inline-flex items-center gap-1 font-medium hover:underline"
                title="Open the class recording on Vimeo"
              >
                <SquarePlay className="size-3.5" /> Watch recording
              </a>
            )}
          </p>
        </div>
        <DeleteAnalysisButton classId={String(klass.id)} />
      </div>

      {!analysis ? (
        inProgress ? (
          <Card className="shadow-soft">
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <Loader2 className="text-muted-foreground size-7 animate-spin" />
              <div className="font-medium">
                {stuck ? "This analysis looks stuck" : klass.status === "scheduled" ? "Starting…" : "Analyzing…"}
              </div>
              <p className="text-muted-foreground max-w-md text-sm">
                {stuck && klass.status === "scheduled"
                  ? "The analysis service never picked this up — it was asked over 10 minutes ago. Retry to ask again."
                  : stuck
                    ? "It has been running for over 30 minutes — the background worker probably restarted mid-job. Retry to run it again (materials and video are not stored, so a retry is transcript-only)."
                    : klass.status === "scheduled"
                      ? "Waiting for the analysis service to take the job. Usually a few seconds; up to a minute if the service was asleep. If it could not be reached, it picks the class up on its own within a couple of minutes."
                      : "Fetching the transcript, reading your materials, and writing the feedback. A long class can take a few minutes — this page updates on its own, no need to refresh."}
              </p>
              {stuck && canRetry && <RetryButton classId={String(klass.id)} />}
              {!stuck && <AutoRefresh />}
            </CardContent>
          </Card>
        ) : (
          <Card className="shadow-soft">
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <AlertTriangle className="text-destructive size-7" />
              <div className="font-medium">The analysis didn&apos;t finish</div>
              <p className="text-muted-foreground max-w-md text-sm">
                {failReason ||
                  "Something went wrong — the video may have no captions, or a materials file couldn't be read. Retry, or delete this and create it again."}
              </p>
              {canRetry && <RetryButton classId={String(klass.id)} />}
              <p className="text-muted-foreground text-xs">
                A retry re-fetches the transcript from Vimeo. Materials and video are not stored, so it runs transcript-only.
              </p>
            </CardContent>
          </Card>
        )
      ) : (
        <>
          {result.overall && (
            <Reveal>
              <Card className="shadow-soft">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Overall</CardTitle>
                </CardHeader>
                <CardContent className="text-sm leading-relaxed">{result.overall}</CardContent>
              </Card>
            </Reveal>
          )}

          <Reveal delay={0.05}>
            <Card className="shadow-soft">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Flags ({flags.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {flags.length > 0 && (
                  <Stagger className="space-y-3" step={0.05}>
                    {flags.map((f, i) => (
                      <StaggerItem key={i} className="rounded-lg border p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{findingLabel(f.flag)}</span>
                          <Badge variant={sevVariant(f.severity)}>{severityLabel(f.severity)}</Badge>
                          <span className="text-muted-foreground text-xs">{confidenceLabel(f.confidence)}</span>
                        </div>
                        {(f.evidence ?? []).map((e, j) => (
                          <p key={j} className="text-muted-foreground mt-1.5 text-sm">
                            <span className="font-mono text-xs">[{e.timestamp}]</span>{" "}
                            {e.source === "video" && <Badge variant="outline" className="mr-1 align-middle">🎬 video</Badge>}
                            “{e.quote}”
                          </p>
                        ))}
                      </StaggerItem>
                    ))}
                  </Stagger>
                )}
                {flags.length === 0 && (
                  <p className="text-muted-foreground text-sm">No flags raised.</p>
                )}
                {result.video?.video_used ? (
                  <p className="text-muted-foreground text-xs">
                    🎬 Video analyzed: {result.video.frames_analyzed} frames sampled from the recording —
                    camera/screen/slides findings are evidence-based.
                  </p>
                ) : result.video?.video_error ? (
                  <p className="text-muted-foreground text-xs">
                    Video analysis skipped: {result.video.video_error} — findings are transcript-only.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </Reveal>

          {verification?.error && (
            <Reveal>
              <Card className="border-destructive/40 shadow-soft">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">The self-check did not run</CardTitle>
                </CardHeader>
                <CardContent className="text-muted-foreground space-y-1 text-sm">
                  <p>
                    Every finding below is the first draft. Nothing challenged it, so a finding may
                    rest on a misread quote or on something a learner said rather than the
                    instructor. Read it before you act on it, and re-run the analysis if you can.
                  </p>
                  <p className="font-mono text-xs">{verification.error}</p>
                </CardContent>
              </Card>
            </Reveal>
          )}

          {review.length > 0 && (
            <Reveal>
              <Card className="shadow-soft">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    Self-check
                    <Badge variant="secondary">the AI double-checked its own findings</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Stagger className="space-y-2" step={0.04}>
                    {review.map((r, i) => (
                      <StaggerItem key={i} className="flex items-start gap-2 text-sm">
                        <Badge
                          variant={r.verdict === "drop" ? "destructive" : r.verdict === "downgrade" ? "warning" : "secondary"}
                          className="mt-0.5 shrink-0"
                        >
                          {r.verdict === "drop" ? "removed" : r.verdict === "downgrade"
                            ? `${severityLabel(r.from_severity)} → ${severityLabel(r.to_severity)}` : "confirmed"}
                        </Badge>
                        <div>
                          <span className="font-medium">{findingLabel(r.flag)}</span>
                          <span className="text-muted-foreground"> — {r.reason}</span>
                        </div>
                      </StaggerItem>
                    ))}
                  </Stagger>
                  {result.reclass?.softened_from && (
                    <p className="text-muted-foreground text-xs">
                      ⚖️ The re-class call was auto-softened from <strong>yes</strong> to{" "}
                      <strong>maybe</strong> because no major content-delivery issue survived verification.
                    </p>
                  )}
                  <p className="text-muted-foreground text-xs">
                    Every serious finding gets a second, adversarial review before you see it — severities
                    are corrected and unsupported findings removed (shown here so nothing disappears silently).
                  </p>
                </CardContent>
              </Card>
            </Reveal>
          )}

          <Reveal>
            <Card className="shadow-soft">
              <CardHeader className="flex-row items-center justify-between pb-2">
                <CardTitle className="text-base">Instructor feedback — review &amp; approve</CardTitle>
                <span className="flex items-center gap-2">
                  {done && <Badge variant="success">{wasSent ? "Sent to instructor ✓" : "Approved"}</Badge>}
                  {done && !wasSent && <MarkSentButton classId={String(klass.id)} />}
                </span>
              </CardHeader>
              <CardContent>
                <ReviewActions
                  classId={String(klass.id)}
                  summaryInitial={summaryDraft}
                  feedbackInitial={draft}
                  done={done}
                />
              </CardContent>
            </Card>
          </Reveal>

          {reclass?.recommended && (
            <Reveal>
              <Card className="shadow-soft border-warning/50">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    Re-class recommendation
                    <Badge variant="outline">PM only — not shown to the instructor</Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={reclass.recommended === "yes" ? "destructive" : reclass.recommended === "maybe" ? "warning" : "secondary"}
                    >
                      {reclassLabel(reclass.recommended)}
                    </Badge>
                    {reclass.deciding_flags && reclass.deciding_flags.length > 0 && (
                      <span className="text-muted-foreground text-xs">
                        decided by: {reclass.deciding_flags.map(findingLabel).join(", ").toLowerCase()}
                      </span>
                    )}
                  </div>
                  <p className="text-muted-foreground">{reclass.reason}</p>
                </CardContent>
              </Card>
            </Reveal>
          )}
        </>
      )}
    </div>
  );
}
