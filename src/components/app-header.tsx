"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./ui";

const NAV = [
  { href: "/cases", label: "Cases", match: "/cases" },
  { href: "/upload", label: "Upload documents", match: "/upload" },
  { href: "/settings/connectors", label: "Settings", match: "/settings" },
];

export function AppHeader() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-8 border-b border-line bg-white px-7">
      <Link href="/cases" className="flex flex-none items-center gap-2.5 hover:no-underline">
        <span className="flex size-[30px] items-center justify-center rounded-md bg-navy font-serif text-sm font-semibold text-[#cfe0ee]">V</span>
        <span className="text-[15px] font-semibold whitespace-nowrap text-ink">VeriteLex AI</span>
      </Link>
      <nav className="flex h-full gap-1">
        {NAV.map((n) => {
          const on = path.startsWith(n.match);
          return (
            <Link
              key={n.href}
              href={n.href}
              aria-current={on ? "page" : undefined}
              className={cx(
                "flex h-full items-center border-b-2 px-3.5 text-sm font-medium whitespace-nowrap hover:no-underline",
                on ? "border-navy text-ink hover:text-ink" : "border-transparent text-muted-2 hover:text-ink",
              )}
            >
              {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="ml-auto flex flex-none items-center gap-3">
        <div className="flex flex-col items-end leading-[1.35] max-md:hidden">
          <span className="text-[13px] font-medium whitespace-nowrap text-ink">H.E. Justice Amina R. Farouk</span>
          <span className="text-xs text-muted">DIFC Courts · Chambers 4</span>
        </div>
        <span className="flex size-9 items-center justify-center rounded-full bg-focus text-[13px] font-semibold text-blue">AF</span>
      </div>
    </header>
  );
}
