"use client";

import Link from "next/link";
import { CONNECTORS, MODELS, POLICIES, SETTINGS_TABS, type SettingsTab } from "@/lib/data";
import { useStore } from "@/lib/store";
import { Monogram, Switch, card, cx } from "./ui";

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
          const on = !!c.builtin || conn[c.id];
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
                  {c.builtin ? "Built in" : on ? "Connected" : "Not connected"}
                </span>
                <button
                  type="button"
                  disabled={c.builtin}
                  onClick={() => toggleConn(c.id)}
                  className={cx(
                    "h-9 rounded-lg border px-3.5 text-[13px] font-semibold disabled:cursor-default",
                    c.builtin ? "border-sand bg-sand text-muted-3" : on ? "border-field bg-white text-ink hover:border-blue" : "border-navy bg-navy text-white hover:bg-navy-hover",
                  )}
                >
                  {c.builtin ? "Included" : on ? "Disconnect" : "Authorise"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function Council() {
  const { models, toggleModel, enabledIds } = useStore();
  return (
    <>
      <Heading title="Model council">
        The same question is put to each enabled model independently. Their answers are shown side by side, then compared for agreement, divergence and unverified citations.
      </Heading>
      <div className="grid grid-cols-3 gap-3.5 max-md:grid-cols-1">
        <Stat label="Council size" value={`${enabledIds.length} models`} note="Minimum 2 · maximum 6" big />
        <Stat label="Synthesis by" value="Claude Opus" note="Compares answers; adds no new law" />
        <Stat label="Runs" value="On every new report" note="And on demand from a case" />
      </div>
      <div className={cx(card, "overflow-x-auto")}>
        {MODELS.map((m) => {
          const on = models[m.id];
          return (
            <div
              key={m.id}
              className="grid min-w-[560px] grid-cols-[44px_minmax(0,1fr)_190px_120px_52px] items-center gap-4 border-b border-line-4 px-[22px] py-4 transition-opacity"
              style={{ opacity: on ? 1 : 0.6 }}
            >
              <Monogram m={m.m} c={m.c} />
              <div className="flex flex-col gap-0.5">
                <span className="text-[15px] font-semibold">{m.name}</span>
                <span className="text-[13px] text-muted">{m.vendor}</span>
              </div>
              <span className="text-[13px] text-body-3">{m.host}</span>
              <span className="text-[13px] text-muted">{m.lat}</span>
              <Switch on={on} onClick={() => toggleModel(m.id)} label={`Use ${m.name}`} />
            </div>
          );
        })}
      </div>
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
