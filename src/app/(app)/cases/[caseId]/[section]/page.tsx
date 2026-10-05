import { notFound } from "next/navigation";
import { ReportSection } from "@/components/report/report-section";
import { SECTIONS, type SectionKey } from "@/lib/data";

// Case ids come from Firestore, so sections render on demand (no static params).
export default async function SectionPage({ params }: PageProps<"/cases/[caseId]/[section]">) {
  const { section } = await params;
  if (!SECTIONS.some((s) => s.k === section)) notFound();
  return <ReportSection section={section as SectionKey} />;
}
