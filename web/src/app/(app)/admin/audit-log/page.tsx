import { redirect } from "next/navigation";

/** Old placeholder URL — the audit log now lives at /admin/audit. */
export default function Page() {
  redirect("/admin/audit");
}
