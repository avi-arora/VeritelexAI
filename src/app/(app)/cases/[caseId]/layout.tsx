import { CaseHeader } from "@/components/report/case-header";
import { SectionNav } from "@/components/report/section-nav";

export default function CaseLayout({ children }: LayoutProps<"/cases/[caseId]">) {
  return (
    <div>
      <CaseHeader />
      <div className="mx-auto grid max-w-[1320px] grid-cols-[240px_minmax(0,1fr)] items-start gap-9 px-7 pt-7 pb-[72px] max-lg:grid-cols-1">
        <SectionNav />
        {children}
      </div>
    </div>
  );
}
