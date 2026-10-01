import { notFound } from "next/navigation";
import { ReportSection } from "@/components/report/report-section";
import { REPORT_CASE_ID, SECTIONS, type SectionKey } from "@/lib/data";

export function generateStaticParams() {
  return SECTIONS.map((s) => ({ caseId: REPORT_CASE_ID, section: s.k }));
}

export default async function SectionPage({ params }: PageProps<"/cases/[caseId]/[section]">) {
  const { caseId, section } = await params;
  if (caseId !== REPORT_CASE_ID || !SECTIONS.some((s) => s.k === section)) notFound();
  return <ReportSection section={section as SectionKey} />;
}
