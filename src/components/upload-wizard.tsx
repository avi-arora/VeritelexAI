"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CASE_FIELDS, CONNECTORS, MODELS, NEW_FILES, PIPELINE } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Button, card, cx, input } from "./ui";

const STEPS = ["Add documents", "Confirm case details", "Grounding and models"];

export function UploadWizard({ initialStep }: { initialStep: 1 | 2 | 3 }) {
  const router = useRouter();
  const { conn, models, createCase } = useStore();
  const [step, setStep] = useState(initialStep);

  const sources = CONNECTORS.filter((c) => c.builtin || conn[c.id]);
  const enabled = MODELS.filter((m) => models[m.id]);

  return (
    <div className="mx-auto grid max-w-[1180px] grid-cols-[minmax(0,1fr)_320px] items-start gap-8 px-7 pt-9 pb-16 max-lg:grid-cols-1">
      <div className="flex min-w-0 flex-col gap-6">
        <div>
          <h1 className="mb-2 font-serif text-[30px] leading-[1.2] font-semibold">New case from documents</h1>
          <p className="m-0 text-[15px] leading-[1.6] text-muted-2">
            Upload the case papers. We read them, propose the case details for you to confirm, and create the case entry.
          </p>
        </div>

        <ol className="m-0 flex list-none flex-wrap gap-2 p-0">
          {STEPS.map((label, i) => {
            const n = i + 1;
            const cur = step === n;
            const done = step > n;
            return (
              <li
                key={label}
                aria-current={cur ? "step" : undefined}
                className={cx("flex min-w-[180px] flex-1 items-center gap-3 rounded-[10px] border px-4 py-3.5", cur ? "border-blue bg-white" : "border-line bg-transparent")}
              >
                <span
                  className="flex size-7 flex-none items-center justify-center rounded-full text-[13px] font-semibold"
                  style={{ background: done ? "#2E6B4F" : cur ? "#245C86" : "#ecebe7", color: done || cur ? "#fff" : "#80878f" }}
                >
                  {done ? "✓" : n}
                </span>
                <span className={cx("text-sm font-medium", cur || done ? "text-ink" : "text-muted")}>{label}</span>
              </li>
            );
          })}
        </ol>

        {step === 1 && (
          <div className="flex flex-col gap-5">
            <div className="flex flex-col items-center gap-3 rounded-[14px] border-2 border-dashed border-[#cfcac3] bg-white px-8 py-12 text-center">
              <div className="flex size-[52px] items-center justify-center rounded-xl bg-blue-wash text-[26px] text-blue">↑</div>
              <span className="text-[17px] font-semibold text-ink">Drag files here</span>
              <span className="text-sm text-muted">PDF, Word, Excel or scanned images · up to 500 MB each</span>
              <div className="mt-2 flex flex-wrap justify-center gap-2.5">
                <Button className="h-[42px] px-[18px] text-sm">Choose files</Button>
                <Button variant="outline" className="h-[42px] px-[18px] text-sm">Import from DIFC eRegistry</Button>
              </div>
            </div>
            <div className={cx(card, "overflow-hidden")}>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-2 px-[22px] py-4">
                <span className="text-[15px] font-semibold">5 files added</span>
                <span className="text-[13px] text-muted">312 pages · document types detected automatically</span>
              </div>
              {NEW_FILES.map((f) => (
                <div key={f.n} className="grid grid-cols-[36px_minmax(0,1fr)_170px_80px_24px] items-center gap-3.5 border-b border-line-4 px-[22px] py-3.5 max-sm:grid-cols-[36px_minmax(0,1fr)_24px]">
                  <div className="flex h-[38px] w-8 items-end justify-center rounded border border-field bg-panel pb-1 font-mono text-[8px] font-semibold text-muted">{f.ext}</div>
                  <span className="truncate text-sm font-medium text-ink">{f.n}</span>
                  <span className="justify-self-start rounded-[5px] bg-blue-wash px-[9px] py-1 text-[12.5px] font-medium text-blue max-sm:hidden">{f.t}</span>
                  <span className="text-[13px] text-muted max-sm:hidden">{f.p}</span>
                  <button type="button" aria-label={`Remove ${f.n}`} className="text-base text-faint">×</button>
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <Button className="h-[46px] px-6 text-sm" onClick={() => setStep(2)}>Continue</Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-5">
            <div className="flex items-center gap-3 rounded-[10px] border border-[#cfe3d5] bg-[#eef6f0] px-[18px] py-3.5">
              <span className="flex size-[22px] flex-none items-center justify-center rounded-full bg-green text-xs font-semibold text-white">✓</span>
              <span className="text-sm leading-normal text-[#24543e]">
                We read the Claim Form and Particulars and filled in the details below. Check each one before the case is created.
              </span>
            </div>
            <div className={cx(card, "grid grid-cols-2 gap-x-6 gap-y-[22px] p-[26px] max-sm:grid-cols-1")}>
              {CASE_FIELDS.map((f) => (
                <label key={f.k} className={cx("flex flex-col gap-2", f.full && "col-span-full")}>
                  <span className="text-[13px] font-medium text-body-2">{f.k}</span>
                  <input defaultValue={f.v} className={input} />
                  <span className="text-xs text-muted-3">{f.src}</span>
                </label>
              ))}
            </div>
            <div className="flex justify-between">
              <Button variant="outline" className="h-[46px] px-5 text-sm" onClick={() => setStep(1)}>Back</Button>
              <Button className="h-[46px] px-6 text-sm" onClick={() => setStep(3)}>Continue</Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col gap-5">
            <div className={cx(card, "px-[26px] py-6")}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <h3 className="m-0 font-serif text-[17px] font-semibold">Ground the analysis in</h3>
                <Link href="/settings/connectors" className="text-[13px] font-medium">Manage connectors</Link>
              </div>
              <p className="mt-0 mb-4 text-[13.5px] text-muted">Only connected sources are listed. Every statement in the report will cite one of these or the case record.</p>
              <div className="grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
                {sources.map((g) => (
                  <div key={g.id} className="flex items-center gap-3 rounded-lg border border-line px-3.5 py-3">
                    <span className="flex size-[18px] flex-none items-center justify-center rounded bg-blue text-[11px] font-semibold text-white">✓</span>
                    <span className="text-sm font-medium">{g.name}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className={cx(card, "px-[26px] py-6")}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <h3 className="m-0 font-serif text-[17px] font-semibold">Model council</h3>
                <Link href="/settings/council" className="text-[13px] font-medium">Change models</Link>
              </div>
              <p className="mt-0 mb-4 text-[13.5px] text-muted">
                {enabled.length} models will answer the key questions independently, and their answers will be compared.
              </p>
              <div className="flex flex-wrap gap-2">
                {enabled.map((m) => (
                  <span key={m.id} className="rounded-md bg-sand px-3 py-[7px] text-[13px] font-medium">{m.name}</span>
                ))}
              </div>
            </div>
            <div className="flex justify-between">
              <Button variant="outline" className="h-[46px] px-5 text-sm" onClick={() => setStep(2)}>Back</Button>
              <Button
                variant="accent"
                className="h-[46px] px-6 text-sm"
                onClick={() => {
                  createCase();
                  router.push("/cases");
                }}
              >
                Create case and start analysis
              </Button>
            </div>
          </div>
        )}
      </div>

      <aside className={cx(card, "sticky top-[88px] p-6 max-lg:static")}>
        <h3 className="mb-1.5 font-serif text-base font-semibold">What happens next</h3>
        <p className="mt-0 mb-5 text-[13px] leading-[1.55] text-muted">You can follow each stage from the Cases list.</p>
        <div className="flex flex-col">
          {PIPELINE.map((p) => (
            <div key={p.t} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
              <div className="flex flex-col items-center">
                <span className="mt-1 size-3 flex-none rounded-full" style={{ background: p.c }} />
                <span className="min-h-5 w-0.5 flex-1 bg-line-2" />
              </div>
              <div className="pb-[18px]">
                <span className="mb-[3px] block text-sm font-semibold text-ink">{p.t}</span>
                <span className="text-[13px] leading-normal text-muted-2">{p.b}</span>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
