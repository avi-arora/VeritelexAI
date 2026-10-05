"use client";

import Link from "next/link";
import type { CouncilMemberStatus } from "@/lib/api";
import { CONNECTORS, POLICIES, SETTINGS_TABS, type SettingsTab, type Tone } from "@/lib/data";
import { fmtDateTime } from "@/lib/format";
import { useStore } from "@/lib/store";
import { ExternalLink } from "./report/council-ui";
import { Badge, Button, Monogram, Spinner, Switch, card, cx } from "./ui";

export function Settings({ tab }: { tab: SettingsTab }) {
  return (
    <div className="mx-auto grid max-w-[1180px] grid-cols-[220px_minmax(0,1fr)] items-start gap-9 px-7 pt-9 pb-16 max-md:grid-cols-1">
      <nav className="sticky top-[88px] flex flex-col gap-1 max-md:static">
        <h1 className="mt-0 mb-[18px] font-serif text-[26px] font-semibold">Settings</h1>
        {SETTINGS_TABS.map((t) => {
          const on = t.k === tab;
          return (
            <Link
              key={t.k}
              href={`/settings/${t.k}`}
              aria-current={on ? "page" : undefined}
              className={cx("rounded-lg px-3.5 py-[11px] text-left text-sm font-medium hover:no-underline", on ? "bg-white text-ink hover:text-ink" : "text-muted-2 hover:text-ink")}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      <div className="flex min-w-0 flex-col gap-[22px]">
        {tab === "connectors" && <Connectors />}
        {tab === "council" && <Council />}
        {tab === "policy" && <Policy />}
      </div>
    </div>
  );
}

function Heading({ title, children }: { title: string; children: string }) {
  return (
    <div>
      <h2 className="mt-0 mb-2 font-serif text-[22px] font-semibold">{title}</h2>
      <p className="m-0 max-w-[680px] text-[15px] leading-[1.6] text-muted-2">{children}</p>
    </div>
  );
}

function Connectors() {
  const { conn, toggleConn } = useStore();
  return (
    <>
      <Heading title="Connectors">
        Sources the analysis may use for grounding. Authorise a connector with your organisation&apos;s account; results from it are always labelled in the report.
      </Heading>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3.5">
        {CONNECTORS.map((c) => {
          const locked = !c.available;
          const on = !locked && conn[c.id];
          const stFg = on ? "#2E6B4F" : "#9aa0a8";
          return (
            <div key={c.id} className="flex flex-col gap-3.5 rounded-xl border bg-white p-5" style={{ borderColor: on ? "#e7e4df" : "#ece9e4" }}>
              <div className="flex items-center gap-3">
                <Monogram m={c.m} c={c.mono} size={40} radius={9} fontSize={14} />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[15px] font-semibold">{c.name}</span>
                  <span className="text-[12.5px] text-muted">{c.by}</span>
                </div>
              </div>
              <p className="m-0 flex-1 text-[13.5px] leading-[1.55] text-body-3">{c.desc}</p>
              <div className="flex items-center justify-between gap-2.5">
                <span className="flex items-center gap-[7px] text-[13px] font-medium" style={{ color: stFg }}>
                  <span className="size-2 rounded-full" style={{ background: stFg }} />
                  {locked ? "Not available in this pilot" : on ? "Connected" : "Not connected"}
                </span>
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => toggleConn(c.id)}
                  className={cx(
                    "h-9 rounded-lg border px-3.5 text-[13px] font-semibold disabled:cursor-default",
                    locked ? "border-sand bg-sand text-muted-3" : on ? "border-field bg-white text-ink hover:border-blue" : "border-navy bg-navy text-white hover:bg-navy-hover",
                  )}
                >
                  {locked ? "Coming soon" : on ? "Disconnect" : "Authorise"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

const MEMBER_STATUS: Record<CouncilMemberStatus, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "green" },
  fallback: { label: "Using fallback model", tone: "amber" },
  unavailable: { label: "Not enabled", tone: "grey" },
  error: { label: "Error", tone: "red" },
  unknown: { label: "Not checked", tone: "grey" },
};

function Council() {
  const { council, councilError, councilChecking, refreshCouncil, members, isOn, toggleModel, askIds, anon } = useStore();
  const usable = members.filter((m) => m.status !== "unavailable");
  const chair = (council?.chair ?? []).map((id) => members.find((m) => m.id === id)).find((m) => m && m.status !== "unavailable");
  const checked = members.map((m) => m.checkedAt).filter((t): t is string => !!t);
  const lastChecked = checked.length ? [...checked].sort().at(-1) : undefined;

  return (
    <>
      <Heading title="Model council">
        The same question is put to each switched-on model independently. Their answers are shown side by side, then compared for agreement, divergence and unverified citations.
      </Heading>
      <div className="grid grid-cols-3 gap-3.5 max-md:grid-cols-1">
        <Stat label="Council size" value={council ? `${askIds.length} of ${members.length} models` : "—"} note={`At least ${Math.min(2, usable.length || 2)} stay switched on`} big />
        <Stat label="Synthesis by" value={chair?.name ?? "—"} note="Compares answers; adds no new law" />
        <Stat label="Runs" value="On every new report" note="And on demand from a case" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-[13px] text-muted">
          {lastChecked ? `Model Garden last checked ${fmtDateTime(lastChecked)}` : council ? "Model Garden has not been checked yet" : ""}
        </span>
        <Button variant="outline" className="flex h-9 items-center gap-2 px-3.5 text-[13px] disabled:opacity-60" disabled={councilChecking} onClick={() => void refreshCouncil(true)}>
          {councilChecking && <Spinner />}
          {councilChecking ? "Checking…" : "Check again"}
        </Button>
      </div>

      {councilError && (
        <p role="alert" className="m-0 text-sm text-red">
          {council ? "Could not check the models again" : "Could not load the council members"}: {councilError.message}
        </p>
      )}
      {!council && !councilError && (
        <span className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Loading the council…
        </span>
      )}

      {council && (
        <div className={cx(card, "overflow-x-auto")}>
          <ul role="list" className="m-0 list-none p-0">
            {members.map((m) => {
              const unavailable = m.status === "unavailable";
              const on = isOn(m.id) && !unavailable;
              const st = MEMBER_STATUS[m.status] ?? MEMBER_STATUS.unknown;
              return (
                <li
                  key={m.id}
                  className="grid min-w-[760px] grid-cols-[44px_minmax(0,1fr)_230px_220px_52px] items-start gap-4 border-b border-line-4 px-[22px] py-4 transition-opacity last:border-b-0"
                  style={{ opacity: on ? 1 : 0.7 }}
                >
                  <Monogram m={m.m} c={/^#[0-9a-f]{3,8}$/i.test(m.c) ? m.c : "#5c646d"} />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-[15px] font-semibold">{m.name}</span>
                    <span className="text-[13px] text-muted">{m.vendor}</span>
                  </div>
                  <div className="flex min-w-0 flex-col gap-0.5 text-[13px]">
                    <span className="text-body-3">{m.host}</span>
                    <span className="truncate font-mono text-xs text-muted" title={m.models.join(" → ")}>
                      {m.activeModel ? m.activeModel : m.models[0] ? `Preferred: ${m.models[0]}` : ""}
                    </span>
                  </div>
                  <div className="flex min-w-0 flex-col items-start gap-1">
                    <Badge tone={st.tone}>{st.label}</Badge>
                    {m.detail && <span className="text-xs leading-[1.45] break-words text-muted">{m.detail}</span>}
                    {unavailable && (
                      <ExternalLink href={m.consoleUrl} className="text-[12.5px] font-medium">
                        Enable in Model Garden
                      </ExternalLink>
                    )}
                  </div>
                  <Switch
                    on={on}
                    disabled={unavailable}
                    onClick={() => toggleModel(m.id)}
                    label={`Use ${m.name}`}
                  />
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {council && anon && (
        <p className="m-0 text-[13px] text-muted">
          The policy “Show model names in the council” is off, so the council screens label these models Model A, B, C in this order.
        </p>
      )}
    </>
  );
}

function Stat({ label, value, note, big }: { label: string; value: string; note: string; big?: boolean }) {
  return (
    <div className={cx(card, "px-5 py-[18px]")}>
      <span className="text-[13px] text-muted">{label}</span>
      <div className={big ? "mt-1.5 font-serif text-[28px] font-semibold" : "mt-2.5 text-[17px] font-semibold"}>{value}</div>
      <span className="text-[12.5px] text-muted-3">{note}</span>
    </div>
  );
}

function Policy() {
  const { policy, togglePolicy } = useStore();
  return (
    <>
      <Heading title="Grounding policy">Rules every report follows, whichever models and connectors are used.</Heading>
      <div className={cx(card, "overflow-hidden")}>
        {POLICIES.map(([t, b], i) => (
          <div key={t} className="flex items-center gap-5 border-b border-line-4 px-[22px] py-[18px]">
            <div className="flex flex-1 flex-col gap-[3px]">
              <span className="text-[14.5px] font-semibold">{t}</span>
              <span className="text-[13.5px] leading-normal text-muted">{b}</span>
            </div>
            <Switch on={policy[i]} onClick={() => togglePolicy(i)} label={t} />
          </div>
        ))}
      </div>
    </>
  );
}
