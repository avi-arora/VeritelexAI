import { notFound } from "next/navigation";
import { CaseProvider } from "@/components/report/case-context";
import { CaseHeader } from "@/components/report/case-header";
import { SectionNav } from "@/components/report/section-nav";

export default async function CaseLayout({ children, params }: LayoutProps<"/cases/[caseId]">) {
  const { caseId } = await params;
  if (!/^c[0-9a-f]{12}$/.test(caseId)) notFound();
  return (
    <CaseProvider caseId={caseId}>
      <div>
        <CaseHeader />
        <div className="mx-auto grid max-w-[1320px] grid-cols-[240px_minmax(0,1fr)] items-start gap-9 px-7 pt-7 pb-[72px] max-lg:grid-cols-1">
          <SectionNav />
          {children}
        </div>
      </div>
    </CaseProvider>
  );
}
