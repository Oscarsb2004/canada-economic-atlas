/**
 * store.ts — pinned views, persisted locally.
 *
 * A pinned tab is a DESCRIPTOR, not a snapshot: `{kind, params, label}` plus the
 * filter state that was active when it was pinned. Reopening one re-renders it
 * against whatever data is current, so a tab pinned last month shows this
 * month's figures rather than a fossil.
 *
 * That distinction is the whole design. Storing rendered output would make
 * every tab a stale copy of the bundle and would grow localStorage without
 * bound; storing the question instead keeps a tab a few dozen bytes and always
 * correct.
 *
 * Persistence is `localStorage` via zustand's `persist`. It is per-browser and
 * per-device by nature — that is the right scope for "the four views I keep
 * coming back to", and there is no server here to make it anything else.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { assertNever } from "../data/bundle";
import type { RangeId, SectorView } from "../filters/FilterRow";

/** What a pin can point at. */
export type PinKind = "sector-view" | "sector-focus" | "project" | "corridor";

export interface Pin {
  /** Stable id so reorder and rename do not depend on array position. */
  id: string;
  kind: PinKind;
  /** The user-facing name. Editable; falls back to `defaultLabel`. */
  label: string;
  /** What was on screen: enough to reconstruct the view exactly. */
  params: {
    view?: SectorView;
    range?: RangeId;
    /** NAICS code for a focused sector. */
    code?: string;
    /** Project slug. */
    slug?: string;
    /** Trade corridor id. */
    corridor?: string;
  };
  pinnedAt: string;
}

interface TabsState {
  pins: Pin[];
  /** Which pin is currently open, or null for the default view. */
  activeId: string | null;

  add: (pin: Omit<Pin, "id" | "pinnedAt">) => void;
  remove: (id: string) => void;
  rename: (id: string, label: string) => void;
  move: (id: string, direction: -1 | 1) => void;
  activate: (id: string | null) => void;
  /** True when an equivalent pin already exists — so the UI can show pinned state. */
  isPinned: (kind: PinKind, params: Pin["params"]) => boolean;
}

/**
 * Two pins are the same if they ask the same question.
 *
 * A `switch` with `assertNever`, not a chain of `if`s with a fallthrough. The
 * fallthrough version compared `view` and `range` for any kind it did not name,
 * so a new `PinKind` — and `corridor` is one — would dedupe on two fields it
 * never sets. Both would be `undefined`, every corridor pin would compare equal
 * to every other, and **the first corridor pinned would silently block all the
 * rest**. `add()` treats a match as a no-op, so nothing would even error.
 *
 * The same reasoning as CLAUDE.md §2b: a decision over an open enum has to be
 * exhaustive, or the member nobody thought about gets the wrong branch.
 */
function sameQuestion(a: Pin["params"], b: Pin["params"], kind: PinKind): boolean {
  switch (kind) {
    case "project":
      return a.slug === b.slug;
    case "sector-focus":
      return a.code === b.code;
    case "corridor":
      return a.corridor === b.corridor;
    case "sector-view":
      return a.view === b.view && a.range === b.range;
    default:
      return assertNever(kind);
  }
}

export const useTabs = create<TabsState>()(
  persist(
    (set, get) => ({
      pins: [],
      activeId: null,

      add: (pin) =>
        set((s) => {
          // Pinning the same question twice is a no-op rather than a duplicate:
          // the pin control is on every view and double-clicking is easy.
          if (s.pins.some((p) => p.kind === pin.kind && sameQuestion(p.params, pin.params, pin.kind))) {
            return s;
          }
          const id = `${pin.kind}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
          return { pins: [...s.pins, { ...pin, id, pinnedAt: new Date().toISOString() }] };
        }),

      remove: (id) =>
        set((s) => ({
          pins: s.pins.filter((p) => p.id !== id),
          activeId: s.activeId === id ? null : s.activeId,
        })),

      rename: (id, label) =>
        set((s) => ({
          pins: s.pins.map((p) => (p.id === id ? { ...p, label: label.trim() || p.label } : p)),
        })),

      move: (id, direction) =>
        set((s) => {
          const i = s.pins.findIndex((p) => p.id === id);
          const j = i + direction;
          if (i < 0 || j < 0 || j >= s.pins.length) return s;
          const pins = [...s.pins];
          [pins[i], pins[j]] = [pins[j], pins[i]];
          return { pins };
        }),

      activate: (id) => set({ activeId: id }),

      isPinned: (kind, params) =>
        get().pins.some((p) => p.kind === kind && sameQuestion(p.params, params, kind)),
    }),
    {
      name: "atlas.pins.v1",
      // Only the pins persist. `activeId` is session state: reopening the app
      // on the default view is less surprising than landing inside whatever was
      // last clicked days ago.
      // Only the pins are persisted, so the partialized shape is genuinely a
      // subset — typed as such rather than cast to the full state, which was a
      // false assertion the compiler had no way to catch.
      partialize: (s): Pick<TabsState, "pins"> => ({ pins: s.pins }),
      version: 1,
    },
  ),
);
