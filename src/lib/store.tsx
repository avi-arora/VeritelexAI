"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type CouncilMember, type CouncilModels } from "./api";
import { CONNECTORS, type ConnectorId } from "./data";

/** How a council member is shown: its real name, or "Model A/B/C…" when the anonymisation policy is on. */
export type MemberLook = { name: string; m: string; c: string };
export type ToastTone = "ok" | "error";

type Store = {
  /** Live council members from GET /council/models; undefined until loaded. */
  council?: CouncilModels;
  councilError: Error | null;
  /** True while Model Garden is being probed again ("Check again"). */
  councilChecking: boolean;
  /** Reload the members; `recheck` asks the backend to probe Model Garden now instead of using its cached status. */
  refreshCouncil: (recheck?: boolean) => Promise<void>;
  members: CouncilMember[];
  member: (id: string) => CouncilMember | undefined;
  /** Client-side switch per member id (every member starts switched on). */
  models: Record<string, boolean>;
  isOn: (id: string) => boolean;
  toggleModel: (id: string) => void;
  /** Switched-on members, in council order. */
  enabledIds: string[];
  /** Switched-on members that are not unavailable: the members a question is put to. */
  askIds: string[];
  /** True when the policy hides model names. */
  anon: boolean;
  /** Display name for a member, anonymised when the policy says so. Unknown ids fall back to `fallback`, then the raw id. */
  nm: (id: string, fallback?: string) => string;
  /** Name, monogram and colour for a member, anonymised when the policy says so. */
  look: (id: string, fallback?: Partial<MemberLook>) => MemberLook;

  conn: Record<ConnectorId, boolean>;
  toggleConn: (id: ConnectorId) => void;

  policy: boolean[];
  togglePolicy: (i: number) => void;

  toast: string;
  toastTone: ToastTone;
  showToast: (msg: string, tone?: ToastTone) => void;

  exportOpen: boolean;
  setExportOpen: (open: boolean) => void;
  exportSel: boolean[];
  toggleExport: (i: number) => void;

  /** Counsel questions added to the bench note, by question id. */
  pinned: Record<string, boolean>;
  togglePin: (id: string) => void;
};

const StoreContext = createContext<Store | null>(null);

/** Keep at least this many usable members switched on (or all of them, if fewer exist). */
const MIN_MODELS = 2;
const ANON_COLOUR = "#5c646d";
/** Neutral greys for anonymised members, so colour does not hint at the vendor. */
const ANON_PALETTE = ["#5c646d", "#46505b", "#76808a", "#39424c", "#868d95"];
const COLOUR = /^#[0-9a-f]{3,8}$/i;
const safeColour = (...cs: (string | undefined)[]) => cs.find((c): c is string => !!c && COLOUR.test(c)) ?? ANON_COLOUR;
const letter = (i: number) => String.fromCharCode(65 + (i % 26)) + (i >= 26 ? String(Math.floor(i / 26)) : "");

export function StoreProvider({ children }: { children: ReactNode }) {
  const [council, setCouncil] = useState<CouncilModels>();
  const [councilError, setCouncilError] = useState<Error | null>(null);
  const [councilChecking, setCouncilChecking] = useState(false);
  // Members the user switched off; everything else is on, including members added later.
  const [off, setOff] = useState<Record<string, boolean>>({});
  // Only Grounding with Google Search is implemented; every other connector is off and locked.
  const [conn, setConn] = useState<Record<ConnectorId, boolean>>({ difc: false, google: true, bing: false, harvey: false, scc: false, bailii: false, westlaw: false, lexis: false, vlex: false, manupatra: false });
  const [policy, setPolicy] = useState([true, true, true, false, true]);
  const [toast, setToast] = useState("");
  const [toastTone, setToastTone] = useState<ToastTone>("ok");
  const [exportOpen, setExportOpen] = useState(false);
  const [exportSel, setExportSel] = useState([true, true, true, true, true, false, false]);
  const [pinned, setPinned] = useState<Record<string, boolean>>({});

  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const showToast = useCallback((msg: string, tone: ToastTone = "ok") => {
    clearTimeout(toastTimer.current);
    setToast(msg);
    setToastTone(tone);
    toastTimer.current = setTimeout(() => setToast(""), tone === "error" ? 7000 : 4200);
  }, []);

  useEffect(() => () => clearTimeout(toastTimer.current), []);

  const loadCouncil = useCallback(async (recheck: boolean) => {
    try {
      const d = await api.councilModels(recheck);
      setCouncil(d);
      setCouncilError(null);
    } catch (e) {
      setCouncilError(e as Error);
    }
  }, []);

  // Load the members once (retrying a few times if the backend is not reachable yet); state is set from
  // the promise callbacks, never synchronously in the effect.
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = (attempt: number) => {
      api.councilModels(false).then(
        (d) => {
          if (!live) return;
          setCouncil(d);
          setCouncilError(null);
        },
        (e: Error) => {
          if (!live) return;
          setCouncilError(e);
          if (attempt < 5) timer = setTimeout(() => load(attempt + 1), 15_000);
        },
      );
    };
    load(0);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, []);

  const refreshCouncil = useCallback(
    async (recheck = false) => {
      if (!recheck) return loadCouncil(false);
      setCouncilChecking(true);
      try {
        await loadCouncil(true);
      } finally {
        setCouncilChecking(false);
      }
    },
    [loadCouncil],
  );

  const value = useMemo<Store>(() => {
    const members = council?.members ?? [];
    const index = new Map(members.map((m, i) => [m.id, i]));
    const anon = !policy[4];
    const models = Object.fromEntries(members.map((m) => [m.id, !off[m.id]]));
    const isOn = (id: string) => !off[id];
    const enabledIds = members.filter((m) => !off[m.id]).map((m) => m.id);
    const askIds = members.filter((m) => !off[m.id] && m.status !== "unavailable").map((m) => m.id);

    const nm = (id: string, fallback?: string) => {
      const i = index.get(id);
      if (i !== undefined) return anon ? `Model ${letter(i)}` : members[i].name;
      // Not in the live list (or the list is still loading). Raw ids such as "gemini" name the vendor,
      // so never show them, or a fallback name, while anonymised.
      if (anon) return council ? "Unlisted model" : "Model";
      return fallback || id;
    };

    return {
      council,
      councilError,
      councilChecking,
      refreshCouncil,
      members,
      member: (id) => members.find((m) => m.id === id),
      models,
      isOn,
      toggleModel: (id) => {
        const mem = members.find((m) => m.id === id);
        if (!mem) return;
        // Unavailable members are effectively off and cannot be switched on; explain instead of toggling.
        if (mem.status === "unavailable") {
          showToast(`${mem.name} is not enabled in Model Garden, so it cannot be switched on.`, "error");
          return;
        }
        const on = !off[id];
        if (on) {
          const usable = members.filter((m) => m.status !== "unavailable");
          const min = Math.min(MIN_MODELS, usable.length);
          if (usable.filter((m) => !off[m.id]).length <= min) {
            showToast(`Keep at least ${min} ${min === 1 ? "model" : "models"} switched on.`, "error");
            return;
          }
        }
        setOff((cur) => ({ ...cur, [id]: on }));
      },
      enabledIds,
      askIds,
      anon,
      nm,
      look: (id, fallback) => {
        const i = index.get(id);
        const mem = i !== undefined ? members[i] : undefined;
        if (anon) return { name: nm(id), m: i !== undefined ? letter(i) : "?", c: i !== undefined ? ANON_PALETTE[i % ANON_PALETTE.length] : ANON_COLOUR };
        const m = (mem?.m || fallback?.m || id.slice(0, 1).toUpperCase() || "?").slice(0, 2);
        return { name: mem?.name || fallback?.name || id, m, c: safeColour(mem?.c, fallback?.c) };
      },
      conn,
      toggleConn: (id) => {
        if (!CONNECTORS.find((c) => c.id === id)?.available) return;
        setConn((cur) => ({ ...cur, [id]: !cur[id] }));
      },
      policy,
      togglePolicy: (i) => setPolicy((cur) => cur.map((v, j) => (j === i ? !v : v))),
      toast,
      toastTone,
      showToast,
      exportOpen,
      setExportOpen,
      exportSel,
      toggleExport: (i) => setExportSel((cur) => cur.map((v, j) => (j === i ? !v : v))),
      pinned,
      togglePin: (id) => setPinned((cur) => ({ ...cur, [id]: !cur[id] })),
    };
  }, [council, councilError, councilChecking, refreshCouncil, off, policy, conn, toast, toastTone, showToast, exportOpen, exportSel, pinned]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  const s = useContext(StoreContext);
  if (!s) throw new Error("useStore must be used inside <StoreProvider>");
  return s;
}
