"use client";

import { useStore } from "@/lib/store";

export function Toast() {
  const { toast } = useStore();
  if (!toast) return null;
  return (
    <div
      role="status"
      className="fixed bottom-6 left-1/2 z-60 flex -translate-x-1/2 items-center gap-3 rounded-[10px] bg-navy px-5 py-3.5 text-white shadow-[0_12px_30px_rgba(0,0,0,.25)]"
    >
      <span className="flex size-5 items-center justify-center rounded-full bg-[#3f8a66] text-[11px] font-semibold">✓</span>
      <span className="text-sm font-medium">{toast}</span>
    </div>
  );
}
