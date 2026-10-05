"use client";

import { useStore } from "@/lib/store";

export function Toast() {
  const { toast, toastTone } = useStore();
  const error = toastTone === "error";
  // The live region stays mounted so screen readers announce each new message.
  return (
    <div role="status" aria-live="polite">
      {toast && (
        <div className="fixed bottom-6 left-1/2 z-60 flex max-w-[min(640px,calc(100vw-32px))] -translate-x-1/2 items-center gap-3 rounded-[10px] bg-navy px-5 py-3.5 text-white shadow-[0_12px_30px_rgba(0,0,0,.25)]">
          <span
            aria-hidden
            className="flex size-5 flex-none items-center justify-center rounded-full text-[11px] font-semibold"
            style={{ background: error ? "#b4473c" : "#3f8a66" }}
          >
            {error ? "!" : "✓"}
          </span>
          <span className="text-sm font-medium">{toast}</span>
        </div>
      )}
    </div>
  );
}
