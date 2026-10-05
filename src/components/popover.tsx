"use client";

import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "./ui";

const FOCUSABLE = 'a[href], button:not([disabled]):not([aria-disabled="true"])';
const GAP = 6;
const EDGE = 8;

const noSubscribe = () => () => {};
const popoverSupported = () => "popover" in HTMLElement.prototype;

/**
 * A button that opens a panel of actions or links (not an ARIA menu: items stay plain buttons and links).
 *
 * Uses the Popover API (`popover="auto"`), which gives light dismiss, Escape, focus return and
 * aria-expanded for free; browsers without it get the same behaviour from a state-driven panel.
 * Arrow keys, Home and End move between the items; on open, focus goes to the item marked
 * aria-current, else the first item. Activating any link or button inside the panel closes it.
 */
export function DropPanel({
  trigger,
  triggerClassName,
  triggerLabel,
  panelClassName,
  width = 340,
  children,
}: {
  trigger: ReactNode;
  triggerClassName?: string;
  /** Accessible name, when the trigger's text alone does not say what it opens. */
  triggerLabel?: string;
  panelClassName?: string;
  width?: number;
  children: ReactNode;
}) {
  const panelId = `drop-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  // The server and hydration render assume support; unsupported browsers switch to the fallback afterwards.
  const native = useSyncExternalStore(noSubscribe, popoverSupported, () => true);
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // The panel is position: fixed below the trigger, kept inside the viewport.
  const place = useCallback(() => {
    const b = btnRef.current;
    const p = panelRef.current;
    if (!b || !p) return;
    const r = b.getBoundingClientRect();
    const w = p.offsetWidth || width;
    const left = Math.max(EDGE, Math.min(r.left, window.innerWidth - w - EDGE));
    const top = r.bottom + GAP;
    p.style.left = `${left}px`;
    p.style.top = `${top}px`;
    p.style.maxHeight = `${Math.max(160, window.innerHeight - top - EDGE)}px`;
  }, [width]);

  const focusInitial = useCallback(() => {
    const p = panelRef.current;
    const el = p?.querySelector<HTMLElement>('[aria-current="true"]') ?? p?.querySelector<HTMLElement>(FOCUSABLE);
    el?.focus();
  }, []);

  const close = useCallback(() => {
    if (native) {
      panelRef.current?.hidePopover(); // focus returns to the trigger
    } else {
      setOpen(false);
      btnRef.current?.focus();
    }
  }, [native]);

  // While open: follow the trigger on scroll and resize.
  useEffect(() => {
    if (!open) return;
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, place]);

  // Fallback only: focus on open, close on outside pointer or Escape.
  useEffect(() => {
    if (native || !open) return;
    focusInitial();
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!panelRef.current?.contains(t) && !btnRef.current?.contains(t)) setOpen(false);
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      btnRef.current?.focus();
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [native, open, focusInitial]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    const items = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
    if (!items.length) return;
    e.preventDefault();
    const i = items.indexOf(document.activeElement as HTMLElement);
    const next =
      e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
    items[next].focus();
  };

  const panelClass = cx(
    "fixed m-0 overflow-auto rounded-xl border border-line bg-white p-0 text-ink shadow-[0_12px_32px_rgba(15,23,32,.16)]",
    "right-auto bottom-auto max-w-[calc(100vw-16px)]",
    panelClassName,
  );
  // Never put display utilities on the [popover] element itself: they would override the UA's display: none.
  const body = (
    <div
      onKeyDown={onKeyDown}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("a[href], button")) close();
      }}
    >
      {children}
    </div>
  );

  if (native) {
    return (
      <>
        <button ref={btnRef} type="button" popoverTarget={panelId} aria-label={triggerLabel} onClick={place} className={triggerClassName}>
          {trigger}
        </button>
        <div
          ref={panelRef}
          id={panelId}
          popover="auto"
          style={{ width }}
          className={panelClass}
          onToggle={(e) => {
            const isOpen = e.newState === "open";
            setOpen(isOpen);
            if (isOpen) {
              place();
              focusInitial();
            }
          }}
        >
          {body}
        </div>
      </>
    );
  }
  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label={triggerLabel}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className={triggerClassName}
      >
        {trigger}
      </button>
      {open && (
        <div ref={panelRef} id={panelId} style={{ width }} className={cx(panelClass, "z-50")}>
          {body}
        </div>
      )}
    </>
  );
}
