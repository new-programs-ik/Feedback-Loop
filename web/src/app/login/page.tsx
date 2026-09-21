import { Suspense } from "react";
import { RefreshCw } from "lucide-react";
import { LoginForm } from "./login-form";

function BrandMark({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="from-primary flex size-10 items-center justify-center rounded-xl bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-white shadow-lg">
        <RefreshCw className="size-5" strokeWidth={2.5} />
      </div>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight">Feedback Loop</div>
        <div className="text-muted-foreground text-xs">Interview Kickstart · New Programs</div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="bg-background min-h-screen lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      {/* ── the scene ─────────────────────────────────────────────────────────── */}
      <section
        aria-label="Feedback Loop"
        className="bg-background relative h-64 overflow-hidden sm:h-80 lg:h-auto lg:min-h-screen lg:border-r"
      >
        {/* the gradient backdrop */}
        <div aria-hidden className="bg-mesh absolute inset-0" />
        <div
          aria-hidden
          className="absolute inset-0 bg-[radial-gradient(60%_55%_at_50%_48%,color-mix(in_oklch,var(--primary)_13%,transparent),transparent_72%)]"
        />
        <BrandMark className="absolute top-6 left-6 lg:top-10 lg:left-10" />

        {/* the three-beat pitch */}
        <div className="pointer-events-none absolute inset-x-6 bottom-6 hidden sm:block lg:inset-x-10 lg:bottom-12">
          <p className="max-w-[32ch] text-[clamp(1.5rem,2.3vw,2.4rem)] leading-[1.08] font-semibold tracking-[-0.025em]">
            A low-rated class →<br />
            an AI-drafted,{" "}
            {/* inline clip: the compiled .text-gradient loses its background-clip (the shorthand
                lands after the longhands in the built CSS), and inline styles beat any cascade */}
            <span
              className="text-gradient whitespace-nowrap"
              style={{ WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent" }}
            >
              human-approved
            </span>{" "}
            note
            <br />
            in five minutes.
          </p>
          <p className="text-muted-foreground mt-4 max-w-[48ch] text-sm">
            Every class rating lands here within the hour. The ones under the bar get a transcript read, a draft, and a
            person&apos;s signature — before the next session.
          </p>
        </div>
      </section>

      {/* ── the form ──────────────────────────────────────────────────────────── */}
      <section className="flex items-center justify-center px-4 py-8 sm:px-6 lg:min-h-screen lg:px-12">
        <div className="animate-in-up w-full max-w-sm">
          {/* on the wide layout the brand mark already lives in the scene */}
          <div className="mb-6 flex flex-col items-center gap-3 text-center lg:hidden">
            <div className="text-xl font-semibold tracking-tight">Welcome back</div>
          </div>
          <div className="mb-6 hidden lg:block">
            <div className="text-2xl font-semibold tracking-tight">Welcome back</div>
            <div className="text-muted-foreground mt-1 text-sm">Your @interviewkickstart.com Google account, or email and password.</div>
          </div>
          <Suspense>
            <LoginForm />
          </Suspense>
          <p className="text-muted-foreground/80 mt-6 text-center text-xs">
            AI drafts the feedback · a human approves everything
          </p>
        </div>
      </section>
    </div>
  );
}
