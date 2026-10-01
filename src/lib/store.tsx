"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { MODELS, type ConnectorId, type CaseStatus, type ModelId } from "./data";

type NewCase = { status: CaseStatus; pct: number; ticks: number };

type Store = {
  models: Record<ModelId, boolean>;
  toggleModel: (id: ModelId) => void;
  enabledIds: ModelId[];
  /** Display name for a model, anonymised when the policy says so. */
  nm: (id: ModelId) => string;

  conn: Record<ConnectorId, boolean>;
  toggleConn: (id: ConnectorId) => void;

  policy: boolean[];
  togglePolicy: (i: number) => void;

  newCase: NewCase | null;
  createCase: () => void;

  toast: string;
  showToast: (msg: string) => void;

  exportOpen: boolean;
  setExportOpen: (open: boolean) => void;
  exportSel: boolean[];
  toggleExport: (i: number) => void;

  pinned: Record<number, boolean>;
  togglePin: (i: number) => void;
};

const StoreContext = createContext<Store | null>(null);

const MIN_MODELS = 2;
const MAX_MODELS = 6;

export function StoreProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<Record<ModelId, boolean>>({ claude: true, gpt: true, gemini: true, llama: false, mistral: false, jais: false });
  const [conn, setConn] = useState<Record<ConnectorId, boolean>>({ difc: true, google: true, bing: true, harvey: true, scc: true, bailii: true, westlaw: true, lexis: true, vlex: false, manupatra: false });
  const [policy, setPolicy] = useState([true, true, true, false, true]);
  const [newCase, setNewCase] = useState<NewCase | null>(null);
  const [toast, setToast] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportSel, setExportSel] = useState([true, true, true, true, true, false, false]);
  const [pinned, setPinned] = useState<Record<number, boolean>>({ 0: true, 3: true });

  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const showToast = useCallback((msg: string) => {
    clearTimeout(toastTimer.current);
    setToast(msg);
    toastTimer.current = setTimeout(() => setToast(""), 4200);
  }, []);

  // Simulated processing pipeline for the newly created case.
  const running = newCase !== null && newCase.status !== "ready";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      setNewCase((nc) => {
        if (!nc) return nc;
        let n = { ...nc, ticks: nc.ticks + 1 };
        if (n.status === "queued" && n.ticks >= 2) n = { ...n, status: "ingesting", pct: 0 };
        else if (n.status === "ingesting") {
          n.pct += 20;
          if (n.pct >= 100) n = { ...n, status: "ai", pct: 0 };
        } else if (n.status === "ai") {
          n.pct += 15;
          if (n.pct >= 100) n = { ...n, status: "ready", pct: 100 };
        }
        return n;
      });
    }, 800);
    return () => clearInterval(timer);
  }, [running]);

  const prevStatus = useRef<CaseStatus | null>(null);
  useEffect(() => {
    const status = newCase?.status ?? null;
    if (status === "ready" && prevStatus.current !== "ready") showToast("Report ready · CFI-142/2026");
    prevStatus.current = status;
  }, [newCase?.status, showToast]);

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const createCase = useCallback(() => {
    setNewCase({ status: "queued", pct: 0, ticks: 0 });
    showToast("Case CFI-142/2026 created · analysis started");
  }, [showToast]);

  const value = useMemo<Store>(() => {
    const enabledIds = MODELS.filter((m) => models[m.id]).map((m) => m.id);
    const anon = !policy[4];
    return {
      models,
      enabledIds,
      toggleModel: (id) =>
        setModels((cur) => {
          const cnt = Object.values(cur).filter(Boolean).length;
          if (cur[id] && cnt <= MIN_MODELS) return cur;
          if (!cur[id] && cnt >= MAX_MODELS) return cur;
          return { ...cur, [id]: !cur[id] };
        }),
      nm: (id) => {
        const i = MODELS.findIndex((m) => m.id === id);
        return anon ? "Model " + "ABCDEF"[i] : MODELS[i].name;
      },
      conn,
      toggleConn: (id) => setConn((cur) => ({ ...cur, [id]: !cur[id] })),
      policy,
      togglePolicy: (i) => setPolicy((cur) => cur.map((v, j) => (j === i ? !v : v))),
      newCase,
      createCase,
      toast,
      showToast,
      exportOpen,
      setExportOpen,
      exportSel,
      toggleExport: (i) => setExportSel((cur) => cur.map((v, j) => (j === i ? !v : v))),
      pinned,
      togglePin: (i) => setPinned((cur) => ({ ...cur, [i]: !cur[i] })),
    };
  }, [models, policy, conn, newCase, createCase, toast, showToast, exportOpen, exportSel, pinned]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const s = useContext(StoreContext);
  if (!s) throw new Error("useStore must be used inside <StoreProvider>");
  return s;
}
