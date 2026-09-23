"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2, PlugZap, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { connectUplevel, disconnectUplevel, testUplevel, type UplevelCheck } from "@/app/(app)/admin/actions";

const field =
  "border-input w-full rounded-md border bg-card px-3 py-2 font-mono text-xs shadow-sm outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-ring";

function say(check: UplevelCheck) {
  if (check.status === "ok") toast.success("UpLevel is connected", { description: "The New-analysis form will now find recordings by itself." });
  else if (check.status === "expired") toast.error("UpLevel did not accept this session", { description: "It has expired or its owner logged out. Sign in to UpLevel again and copy a fresh request." });
  else toast.message("Saved", { description: check.message || "It will be tested on the next lookup." });
}

/** Connect, test and disconnect. The pasted text is sent once and never shown back. */
export function UplevelConnect({ connected }: { connected: boolean }) {
  const router = useRouter();
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState<null | "save" | "test" | "remove">(null);

  const save = async () => {
    setBusy("save");
    const r = await connectUplevel(text);
    setBusy(null);
    if (!r.ok) {
      toast.error("Not saved", { description: r.error });
      return;
    }
    setText("");                                  // the session does not stay on screen
    say(r.data);
    router.refresh();
  };
  const test = async () => {
    setBusy("test");
    const r = await testUplevel();
    setBusy(null);
    if (!r.ok) toast.error("Could not test", { description: r.error });
    else say(r.data);
    router.refresh();
  };
  const remove = async () => {
    if (!window.confirm("Disconnect UpLevel? The form will ask for the link by hand until it is connected again.")) return;
    setBusy("remove");
    const r = await disconnectUplevel();
    setBusy(null);
    if (!r.ok) toast.error("Could not disconnect", { description: r.error });
    else toast.success("Disconnected");
    router.refresh();
  };

  return (
    <div className="space-y-4">
      <ol className="text-muted-foreground list-decimal space-y-1.5 pl-5 text-[13px] leading-relaxed">
        <li>In Chrome, sign in to <b className="text-foreground">UpLevel</b> as usual and open the <b className="text-foreground">Videos</b> page.</li>
        <li>Press <b className="text-foreground">F12</b> and click the <b className="text-foreground">Network</b> tab. Refresh the page (F5) so requests appear.</li>
        <li>Right-click any request in the list › <b className="text-foreground">Copy</b> › <b className="text-foreground">Copy as cURL (bash)</b>. (cmd, PowerShell or the raw headers work too.)</li>
        <li>Paste it below, unchanged, and press <b className="text-foreground">Save and test</b>.</li>
      </ol>
      <textarea
        className={field}
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"curl 'https://uplevel.interviewkickstart.com/videos/' \\\n  -b 'sessionid=…; csrftoken=…' …"}
        aria-label="The copied request"
        spellCheck={false}
        autoComplete="off"
      />
      <p className="text-muted-foreground text-xs">
        Only two cookies are kept (<code>sessionid</code> and <code>csrftoken</code>); everything else in the paste,
        including the refresh token, is thrown away. They are stored where no one signed in can read them, and are
        never shown again. Do not paste this anywhere else, including chat.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={save} disabled={!text.trim() || busy !== null}>
          {busy === "save" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <PlugZap className="size-4" aria-hidden />}
          Save and test
        </Button>
        {connected && (
          <>
            <Button type="button" variant="outline" onClick={test} disabled={busy !== null}>
              {busy === "test" && <Loader2 className="size-4 animate-spin" aria-hidden />} Test connection
            </Button>
            <Button type="button" variant="ghost" onClick={remove} disabled={busy !== null} className="text-muted-foreground">
              <Unplug className="size-4" aria-hidden /> Disconnect
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
