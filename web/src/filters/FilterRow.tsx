/**
 * FilterRow.tsx — one row, above everything it scopes.
 *
 * Filters are standard UI, not chart marks. The only rule the visualisation
 * layer adds is compositional, and it is the one violated most often:
 *
 *     ONE row, above the content. Never inside a chart card, never per-chart.
 *     Every chart, stat and table below re-renders against the same slice, so
 *     the numbers on screen always agree with each other.
 *
 * A dashboard where one chart has its own date range is a dashboard where two
 * numbers disagree and neither is wrong.
 *
 * The view switcher lives here rather than as tabs on each chart for the same
 * reason: it scopes everything below it.
 */

import { useI18n } from "../i18n";

export type SectorView = "composition" | "ranking" | "growth" | "trends" | "heatmap";

/**
 * `usesRange` says whether the time window means anything for a view.
 *
 * Two of these read a single latest period — "size now", "growth against a year
 * ago" — and a window never moves the latest period, so Range genuinely cannot
 * change what they show. Offering a control that silently does nothing is worse
 * than not offering it: the reader concludes the data is broken, not the UI.
 *
 * A Record over the view ids, so a new view without a range rule fails the
 * build. Labels and hints live in `i18n.tsx`, keyed the same way. The key order
 * here is the order the chips appear in.
 */
export const VIEWS: Record<SectorView, { usesRange: boolean }> = {
  composition: { usesRange: true },
  ranking: { usesRange: false },
  growth: { usesRange: false },
  trends: { usesRange: true },
  heatmap: { usesRange: true },
};

export const RANGES = [
  { id: "5y", months: 60 },
  { id: "10y", months: 120 },
  { id: "all", months: 0 },
] as const;

export type RangeId = (typeof RANGES)[number]["id"];

interface Props {
  view: SectorView;
  onView: (v: SectorView) => void;
  range: RangeId;
  onRange: (r: RangeId) => void;
  /** False on views that read a single latest period. */
  rangeApplies: boolean;
}

export function FilterRow({ view, onView, range, onRange, rangeApplies }: Props) {
  const { s } = useI18n();
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "var(--sp-3)",
        alignItems: "center",
        padding: "var(--sp-2) 0 var(--sp-3)",
        borderBottom: "var(--hairline)",
        marginBottom: "var(--sp-4)",
      }}
    >
      <Group label={s.filterView}>
        {(Object.keys(VIEWS) as SectorView[]).map((id) => (
          <Chip key={id} active={view === id} onClick={() => onView(id)} title={s.views[id].hint}>
            {s.views[id].label}
          </Chip>
        ))}
      </Group>

      {/* Shown disabled rather than removed, so the row does not reflow as you
          switch views — but disabled, because on these views it cannot do
          anything and a live-looking dead control is a bug report waiting to
          happen. The title says why. */}
      <Group label={s.filterRange}>
        {RANGES.map((r) => (
          <Chip
            key={r.id}
            active={range === r.id}
            onClick={() => onRange(r.id)}
            disabled={!rangeApplies}
            title={rangeApplies ? undefined : s.rangeInapplicable}
          >
            {s.ranges[r.id]}
          </Chip>
        ))}
      </Group>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
      <span
        className="muted"
        style={{ fontSize: "var(--fs-micro)", textTransform: "uppercase", letterSpacing: "0.05em" }}
      >
        {label}
      </span>
      <div style={{ display: "flex", gap: 4 }} role="group" aria-label={label}>
        {children}
      </div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
  title,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      aria-pressed={active}
      style={{
        // 24px minimum hit target, per the interaction spec.
        minHeight: 24,
        padding: "2px 9px",
        borderRadius: 999,
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.45 : 1,
        font: "inherit",
        fontSize: "var(--fs-small)",
        border: active ? "1px solid var(--accent)" : "var(--hairline)",
        background: active ? "color-mix(in oklab, var(--accent) 18%, transparent)" : "transparent",
        color: active ? "var(--ink-primary)" : "var(--ink-secondary)",
      }}
    >
      {children}
    </button>
  );
}
