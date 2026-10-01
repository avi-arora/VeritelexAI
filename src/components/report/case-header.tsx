"use client";

import Link from "next/link";
import { useStore } from "@/lib/store";
import { Button, btn, cx } from "../ui";

export function CaseHeader() {
  const { showToast, setExportOpen } = useStore();
  return (
    <div className="border-b border-line bg-white">
      <div className="mx-auto max-w-[1320px] px-7 pt-[22px] pb-6">
        <Link href="/cases" className="mb-3 inline-block text-[13px] font-medium">← All cases</Link>
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <span className="font-mono text-sm font-medium text-blue">CFI-114/2026</span>
              <span className="flex items-center gap-1.5 rounded-[5px] bg-[#e7f0ea] px-2.5 py-1 text-[12.5px] font-semibold text-green">
                <span>✓</span>Report ready · 29 Sep 2026
              </span>
            </div>
            <h1 className="text-pretty mb-2 font-serif text-[26px] leading-[1.3] font-semibold">Meridian Gulf Contracting LLC v Aurora Vertex Developments Ltd</h1>
            <span className="text-sm text-muted-2">Technology &amp; Construction Division · Delay, variations and liquidated damages · USD 48.2m claimed</span>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <Link href="/upload" className={cx(btn.outline, "flex h-10 items-center px-4 text-[13.5px] text-ink hover:text-ink hover:no-underline")}>
              Add documents
            </Link>
            <Button variant="outline" className="h-10 px-4 text-[13.5px]" onClick={() => showToast("Analysis re-run started for CFI-114/2026")}>
              Re-run analysis
            </Button>
            <Button className="h-10 px-[18px] text-[13.5px]" onClick={() => setExportOpen(true)}>Export / print</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
