"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "./ui";

/** Dark "jump to" strip from the prototype, handy for reviewing every screen. */
export function ProtoNav() {
  const path = usePathname();
  const links = [
    { href: "/login", label: "Login", on: path === "/login" },
    { href: "/cases", label: "Cases", on: path.startsWith("/cases") },
    { href: "/upload", label: "Upload", on: path === "/upload" },
    { href: "/settings/connectors", label: "Settings", on: path.startsWith("/settings") },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 bg-navy-deep px-5 py-[7px]">
      <span className="font-mono text-[10px] font-medium tracking-[.14em] text-[#6f8396]">PROTOTYPE · JUMP TO</span>
      <nav className="flex flex-wrap gap-1">
        {links.map((l) => (
          <Link
            key={l.label}
            href={l.href}
            className={cx(
              "rounded px-2.5 py-1 text-[11px] font-medium hover:no-underline",
              l.on ? "bg-[#e8eef3] text-navy-deep hover:text-navy-deep" : "text-[#9fb0c0] hover:text-white",
            )}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
