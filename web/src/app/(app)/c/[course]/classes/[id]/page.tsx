import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { PrintButton } from "@/components/ui/print-button";
import { ClassDetail, loadClassDetail } from "@/components/score/class-detail";
import { fetchClass } from "@/lib/ratings";
import { getActiveConfig } from "@/lib/scoring";
import { requireUser } from "@/lib/session";
import { hrefIn, resolveWorkspace } from "@/lib/workspace";

type Props = { params: Promise<{ course: string; id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const row = await fetchClass(id);
  return { title: row ? row.topic || row.session_kind : "Class" };
}

/** The class as a page of its own — the same content as the drawer, for printing and deep links. */
export default async function ClassPage({ params }: Props) {
  const { course, id } = await params;
  const [ws] = await Promise.all([resolveWorkspace(course), requireUser()]);
  const [detail, active] = await Promise.all([loadClassDetail(id, ws.courseId), getActiveConfig()]);
  if (!detail) notFound();
  const classesHref = hrefIn(ws.slug, "/classes");

  return (
    <div>
      <PageHeader
        title={detail.row.topic || detail.row.session_kind}
        description={`${detail.row.course_name ?? detail.row.course_label} · ${detail.row.class_date} · ${detail.row.session_kind}`}
        actions={
          <>
            <Button asChild variant="ghost" size="sm">
              <Link href={`${classesHref}?class=${detail.row.id}`}>
                <ArrowLeft aria-hidden /> All classes
              </Link>
            </Button>
            <PrintButton />
          </>
        }
      />
      <div className="bg-card shadow-soft rounded-xl border p-5 sm:p-6">
        <ClassDetail data={detail} cfg={active.config} version={active.version} slug={ws.slug} full />
      </div>
    </div>
  );
}
