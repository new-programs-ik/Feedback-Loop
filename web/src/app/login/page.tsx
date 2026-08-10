import { Suspense } from "react";
import { RefreshCw } from "lucide-react";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      {/* soft brand backdrop */}
      <div className="bg-background absolute inset-0" />
      <div className="from-primary/10 absolute -top-40 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-gradient-to-b to-transparent blur-3xl" />

      <div className="animate-in-up relative w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <div className="from-primary flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br to-[oklch(0.62_0.2_300)] text-white shadow-lg">
            <RefreshCw className="size-6" strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-xl font-semibold tracking-tight">Feedback Loop</div>
            <div className="text-muted-foreground text-sm">Interview Kickstart · New Programs</div>
          </div>
        </div>
        <Suspense>
          <LoginForm />
        </Suspense>
        <p className="text-muted-foreground/80 mt-6 text-center text-xs">
          AI drafts the feedback · a human approves everything
        </p>
      </div>
    </div>
  );
}
