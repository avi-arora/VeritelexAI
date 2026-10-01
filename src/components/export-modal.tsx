"use client";

import { useEffect } from "react";
import { EXPORT_SECTIONS } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Button } from "./ui";

export function ExportModal() {
  const { exportOpen, setExportOpen, exportSel, toggleExport } = useStore();
  const close = () => setExportOpen(false);

  useEffect(() => {
    if (!exportOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExportOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [exportOpen, setExportOpen]);

  if (!exportOpen) return null;

  const pages = EXPORT_SECTIONS.reduce((a, [, pp], i) => a + (exportSel[i] ? pp : 0), 0);

  return (
    <div onClick={close} className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(13,26,38,.45)] p-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-title"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[560px] overflow-hidden rounded-[14px] bg-white shadow-[0_24px_60px_rgba(0,0,0,.25)]"
      >
        <div className="flex items-center justify-between border-b border-line-2 px-[26px] py-[22px]">
          <div>
            <h3 id="export-title" className="mb-1 font-serif text-xl font-semibold">Export or print</h3>
            <span className="text-[13.5px] text-muted">CFI-114/2026 · every page carries its citations</span>
          </div>
          <button type="button" aria-label="Close" onClick={close} className="size-9 rounded-lg bg-sand text-lg text-muted-2">
            ×
          </button>
        </div>
        <div className="px-[26px] py-2.5">
          {EXPORT_SECTIONS.map(([t, pp], i) => {
            const on = exportSel[i];
            return (
              <button
                key={t}
                type="button"
                role="checkbox"
                aria-checked={on}
                onClick={() => toggleExport(i)}
                className="flex w-full items-center gap-3.5 border-b border-line-4 bg-transparent py-3 text-left"
              >
                <span
                  className="flex size-5 flex-none items-center justify-center rounded-[5px] border-[1.5px] text-xs font-semibold text-white"
                  style={{ borderColor: on ? "#10202e" : "#cfcbc4", background: on ? "#10202e" : "#fff" }}
                >
                  {on ? "✓" : ""}
                </span>
                <span className="flex-1 text-[14.5px] font-medium text-ink">{t}</span>
                <span className="text-[13px] text-muted-3">{pp} pp</span>
              </button>
            );
          })}
        </div>
        <div className="flex justify-end gap-2.5 border-t border-line-2 bg-panel px-[26px] pt-[18px] pb-[22px]">
          <Button variant="outline" className="h-[42px] px-4 text-sm" onClick={close}>Print</Button>
          <Button variant="outline" className="h-[42px] px-4 text-sm" onClick={close}>Word (.docx)</Button>
          <Button className="h-[42px] px-[18px] text-sm" onClick={close}>Download PDF · {pages} pages</Button>
        </div>
      </div>
    </div>
  );
}
