import { redirect } from "next/navigation";

/** Old placeholder URL — users, roles and course ownership now live at /admin/people. */
export default function Page() {
  redirect("/admin/people");
}
