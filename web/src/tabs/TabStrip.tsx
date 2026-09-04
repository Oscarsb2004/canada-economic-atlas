/**
 * TabStrip.tsx — the pinned views, and the control that creates them.
 *
 * The strip only appears once something is pinned: an empty tab bar is chrome
 * that teaches nothing.
 *
 * Renaming is inline via double-click rather than a modal — a tab's name is a
 * two-word label, and a dialog for two words is heavier than the task.
 * Reordering is by keyboard-reachable buttons rather than drag: drag-and-drop
 * without a keyboard equivalent is exactly the kind of interaction that works
 * for some readers and not others.
 */

import { useEffect, useRef, useState } from "react";

import { useTabs, type Pin, type PinKind } from "./store";

export function PinButton({
  kind,
  params,
  defaultLabel,
}: {
  kind: PinKind;
  params: Pin["params"];
  defaultLabel: string;
}) {
  const add = useTabs((s) => s.add);
  const pins = useTabs((s) => s.pins);
  const isPinned = useTabs((s) => s.isPinned);
  // Recomputed from `pins` so the button updates when a pin is removed
  // elsewhere; `pins` is referenced to make that dependency explicit.
  const pinned = pins.length >= 0 && isPinned(kind, params);

  return (
    <button
      type="button"
      onClick={() => add({ kind, label: defaultLabel, params })}
      disabled={pinned}
      aria-label={pinned ? `${defaultLabel} is pinned` : `Pin ${defaultLabel}`}
      title={pinned ? "Already pinned" : "Pin this view"}
      style={{
        minHeight: 24,
        padding: "2px 9px",
        borderRadius: 999,
        cursor: pinned ? "default" : "pointer",
        font: "inherit",
        fontSize: "var(--fs-small)",
        border: "var(--hairline)",
        background: "transparent",
        color: pinned ? "var(--ink-muted)" : "var(--ink-secondary)",
        opacity: pinned ? 0.7 : 1,
      }}
    >
      {pinned ? "Pinned" : "Pin"}
    </button>
  );
}

export function TabStrip() {
  const { pins, activeId, activate, remove, rename, move } = useTabs();
  const [editing, setEditing] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  if (pins.length === 0) return null;

  return (
    <div
      role="tablist"
      aria-label="Pinned views"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
        alignItems: "center",
        padding: "var(--sp-2) 0",
        borderBottom: "var(--hairline)",
        marginBottom: "var(--sp-3)",
      }}
    >
      <span
        className="muted"
        style={{ fontSize: "var(--fs-micro)", textTransform: "uppercase", letterSpacing: "0.05em", marginRight: 4 }}
      >
        Pinned
      </span>

      <button
        type="button"
        role="tab"
        aria-selected={activeId === null}
        onClick={() => activate(null)}
        style={chip(activeId === null)}
      >
        Overview
      </button>

      {pins.map((p, i) => {
        const active = activeId === p.id;
        return (
          <span key={p.id} style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
            {editing === p.id ? (
              <input
                ref={inputRef}
                defaultValue={p.label}
                onBlur={(e) => {
                  rename(p.id, e.target.value);
                  setEditing(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                  if (e.key === "Escape") setEditing(null);
                }}
                aria-label={`Rename ${p.label}`}
                style={{
                  ...chip(true),
                  minWidth: 90,
                  font: "inherit",
                  fontSize: "var(--fs-small)",
                }}
              />
            ) : (
              <button
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => activate(p.id)}
                onDoubleClick={() => setEditing(p.id)}
                title={`${p.label} — double-click to rename`}
                style={chip(active)}
              >
                {p.label}
              </button>
            )}

            {active && (
              <>
                <IconBtn label={`Move ${p.label} left`} onClick={() => move(p.id, -1)} disabled={i === 0}>
                  ‹
                </IconBtn>
                <IconBtn
                  label={`Move ${p.label} right`}
                  onClick={() => move(p.id, 1)}
                  disabled={i === pins.length - 1}
                >
                  ›
                </IconBtn>
                <IconBtn label={`Unpin ${p.label}`} onClick={() => remove(p.id)}>
                  ✕
                </IconBtn>
              </>
            )}
          </span>
        );
      })}
    </div>
  );
}

function chip(active: boolean): React.CSSProperties {
  return {
    minHeight: 24,
    padding: "2px 9px",
    borderRadius: 999,
    cursor: "pointer",
    font: "inherit",
    fontSize: "var(--fs-small)",
    border: active ? "1px solid var(--accent)" : "var(--hairline)",
    background: active ? "color-mix(in oklab, var(--accent) 18%, transparent)" : "transparent",
    color: active ? "var(--ink-primary)" : "var(--ink-secondary)",
  };
}

function IconBtn({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      style={{
        // 24px minimum, even though the glyph is small — a pinpoint control is
        // one nobody hits reliably.
        minWidth: 24,
        minHeight: 24,
        padding: 0,
        borderRadius: 4,
        border: "none",
        background: "transparent",
        color: disabled ? "var(--ink-gridline)" : "var(--ink-muted)",
        cursor: disabled ? "default" : "pointer",
        font: "inherit",
        lineHeight: 1,
      }}
    >
      {children}
    </button>
  );
}
