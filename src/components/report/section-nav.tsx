"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { SECTIONS } from "@/lib/data";
import { cx } from "../ui";

const GROUPS = SECTIONS.reduce<{ label: string; items: { k: string; label: string; star: boolean; num: string }[] }[]>((acc, s, i) => {
  let g = acc.find((x) => x.label === s.g);
  if (!g) acc.push((g = { label: s.g, items: [] }));
  g.items.push({ k: s.k, label: s.label, star: "star" in s && s.star, num: String(i + 1).padStart(2, "0") });
  return acc;
}, []);

export function SectionNav() {
  const { caseId, section } = useParams<{ caseId: string; section: string }>();
  return (
    <nav aria-label="Report sections" className="sticky top-[88px] flex flex-col gap-[18px] max-lg:static">
      {GROUPS.map((grp) => (
        <div key={grp.label} className="flex flex-col gap-0.5">
          <span className="px-3 pb-1.5 text-[11.5px] font-medium tracking-[.06em] text-muted-3 uppercase">{grp.label}</span>
          {grp.items.map((s) => {
            const on = s.k === section;
            return (
              <Link
                key={s.k}
                href={`/cases/${caseId}/${s.k}`}
                aria-current={on ? "page" : undefined}
                className={cx(
                  "flex min-h-[42px] w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left hover:no-underline",
                  on ? "bg-white" : "bg-transparent hover:bg-white/60",
                )}
              >
                <span className={cx("w-[18px] flex-none font-mono text-xs font-medium", on ? "text-blue" : "text-faint")}>{s.num}</span>
                <span className={cx("flex-1 text-sm leading-[1.3] font-medium", on ? "text-ink" : "text-body-3")}>{s.label}</span>
                {s.star && <span className="size-1.5 flex-none rounded-full bg-blue" />}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
