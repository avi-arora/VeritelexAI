import { Suspense, type ComponentType } from "react";
import { SECTIONS, type SectionKey } from "@/lib/data";
import { AskCouncil } from "./ask";
import { Background, Documents, Gaps, Issues, Mapping, Submissions } from "./core-sections";
import { CouncilPreAnalysis } from "./council";
import { Grounding } from "./grounding";
import { Matrix } from "./matrix";
import { CounselQuestions } from "./questions";

const BODY: Record<SectionKey, ComponentType> = {
  background: Background,
  matrix: Matrix,
  mapping: Mapping,
  issues: Issues,
  subs: Submissions,
  tools: Grounding,
  gaps: Gaps,
  council: CouncilPreAnalysis,
  ask: AskCouncil,
  questions: CounselQuestions,
  docs: Documents,
};

export function ReportSection({ section }: { section: SectionKey }) {
  const idx = SECTIONS.findIndex((s) => s.k === section);
  const cur = SECTIONS[idx];
  const Body = BODY[section];
  const pad = (n: number) => String(n).padStart(2, "0");

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-col gap-3 border-b border-line pb-5">
        <span className="font-mono text-[13px] font-medium text-muted-3">{pad(idx + 1)} / {pad(SECTIONS.length)}</span>
        <h2 className="m-0 font-serif text-[26px] leading-[1.25] font-semibold">{cur.title}</h2>
        <p className="m-0 max-w-[760px] text-[15px] leading-[1.6] text-muted-2">{cur.desc}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="text-[12.5px] font-medium text-muted">Grounded in</span>
          {cur.src.map((g) => (
            <span key={g} className="rounded-[14px] border border-[#e2dfd9] bg-white px-[11px] py-1 text-[12.5px] font-medium text-body-2">{g}</span>
          ))}
        </div>
      </div>
      {/* Submissions reads ?issue= via useSearchParams, which needs a Suspense boundary. */}
      <Suspense>
        <Body />
      </Suspense>
    </div>
  );
}
