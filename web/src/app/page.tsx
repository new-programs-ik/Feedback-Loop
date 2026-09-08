import { redirect } from "next/navigation";
import { requireUser } from "@/lib/session";
import { getDefaultWorkspace, workspaceHome } from "@/lib/workspace";

/** `/` → your last workspace, or your first course, or the team level. */
export default async function Home() {
  const user = await requireUser();
  const slug = await getDefaultWorkspace(user);
  redirect(workspaceHome(slug));
}
