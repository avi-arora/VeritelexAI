import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { TONE, type Tone } from "@/lib/data";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export const btn = {
  primary: "bg-navy text-white rounded-lg font-semibold hover:bg-navy-hover disabled:opacity-60",
  outline: "bg-white text-ink border border-field rounded-lg font-medium hover:border-blue",
  accent: "bg-blue text-white rounded-lg font-semibold hover:bg-blue-hover",
  link: "bg-transparent p-0 font-medium text-blue hover:underline",
};

export const card = "bg-white border border-line rounded-xl";

export const input =
  "h-[46px] rounded-lg border border-field bg-white px-3.5 text-[15px] text-ink focus:border-blue focus:shadow-[0_0_0_3px_var(--color-focus)] focus:outline-none";

export function Button({ variant = "primary", className, type = "button", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof btn }) {
  return <button type={type} className={cx(btn[variant], className)} {...rest} />;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-block size-3.5 flex-none animate-spin-fast rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}

/** Small rounded status label. Pass a tone, or explicit colours. */
export function Badge({ tone, fg, bg, className, children }: { tone?: Tone; fg?: string; bg?: string; className?: string; children: ReactNode }) {
  const t = tone ? TONE[tone] : undefined;
  return (
    <span className={cx("rounded-[5px] font-semibold", className ?? "px-2 py-[3px] text-[11.5px] whitespace-nowrap")} style={{ color: fg ?? t?.fg, background: bg ?? t?.bg }}>
      {children}
    </span>
  );
}

/** Square coloured monogram used for models and connectors. */
export function Monogram({ m, c, size = 36, radius = 8, fontSize = 13, title }: { m: string; c: string; size?: number; radius?: number; fontSize?: number; title?: string }) {
  return (
    <span
      title={title}
      className="flex flex-none items-center justify-center font-semibold text-white"
      style={{ width: size, height: size, borderRadius: radius, background: c, fontSize }}
    >
      {m}
    </span>
  );
}

/** Grey track with a white raised option, e.g. Active / Past / All. */
export function Segmented<K extends string>({
  options,
  value,
  onChange,
  itemClassName = "h-[38px] px-4 text-[13px]",
  className,
}: {
  options: readonly { k: K; label: string }[];
  value: K;
  onChange: (k: K) => void;
  itemClassName?: string;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap rounded-lg bg-seg p-[3px]", className)} role="tablist">
      {options.map((o) => {
        const on = o.k === value;
        return (
          <button
            key={o.k}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.k)}
            className={cx(
              "rounded-md font-medium whitespace-nowrap",
              itemClassName,
              on ? "bg-white text-ink shadow-[0_1px_2px_rgba(0,0,0,.08)]" : "bg-transparent text-muted-2",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Rounded chip that turns navy when selected. */
export function Chip({ on, onClick, className, children }: { on: boolean; onClick: () => void; className?: string; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cx(
        "border font-medium",
        className ?? "h-9 rounded-[18px] px-3.5 text-[13px]",
        on ? "border-navy bg-navy text-white" : "border-chip bg-white text-body-2",
      )}
    >
      {children}
    </button>
  );
}

export function Switch({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onClick}
      className={cx("flex h-[26px] w-11 flex-none rounded-[13px] p-[3px] transition-colors", on ? "justify-end bg-blue" : "justify-start bg-toggle-off")}
    >
      <span className="size-5 rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,.2)]" />
    </button>
  );
}

export function Dot({ color, size = 10, square, style }: { color: string; size?: number; square?: boolean; style?: CSSProperties }) {
  return <span className="flex-none" style={{ width: size, height: size, borderRadius: square ? 2 : "50%", background: color, ...style }} />;
}

/** "— point" list used for submissions and steel-man columns. */
export function DashList({ items }: { items: string[] }) {
  return (
    <>
      {items.map((pt) => (
        <div key={pt} className="flex gap-3">
          <span className="flex-none pt-[3px] font-mono text-[13px] font-medium text-muted-3">—</span>
          <p className="m-0 font-serif text-[15.5px] leading-[1.65] text-prose">{pt}</p>
        </div>
      ))}
    </>
  );
}

export function GroundTags({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((g) => (
        <span key={g} className="rounded bg-[#e9f3ec] px-2 py-[3px] text-xs leading-[1.4] text-[#24543e]">
          ✓ {g}
        </span>
      ))}
    </div>
  );
}

/** A/B reading marker used in the council views. */
export function ReadingTag({ v, className }: { v: "A" | "B"; className?: string }) {
  return (
    <span
      className={cx("flex-none rounded-[3px] px-[5px] py-px text-[11px] font-semibold", v === "A" ? "bg-blue-tint text-blue" : "bg-[#f7f0e0] text-amber", className)}
    >
      {v}
    </span>
  );
}
