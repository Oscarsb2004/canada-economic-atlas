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

import type { RangeId, SectorView } from "../filters/FilterRow";

/** What a pin can point at. */
export type PinKind = "sector-view" | "sector-focus" | "project";

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

/** Two pins are the same if they ask the same question. */
function sameQuestion(a: Pin["params"], b: Pin["params"], kind: PinKind): boolean {
  if (kind === "project") return a.slug === b.slug;
  if (kind === "sector-focus") return a.code === b.code;
  return a.view === b.view && a.range === b.range;
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
      partialize: (s) => ({ pins: s.pins }) as TabsState,
      version: 1,
    },
  ),
);
