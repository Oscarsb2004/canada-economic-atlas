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

export type SectorView = "composition" | "ranking" | "growth" | "trends" | "heatmap";

/**
 * `usesRange` says whether the time window means anything for a view.
 *
 * Two of these read a single latest period — "size now", "growth against a year
 * ago" — and a window never moves the latest period, so Range genuinely cannot
 * change what they show. Offering a control that silently does nothing is worse
 * than not offering it: the reader concludes the data is broken, not the UI.
 */
export const VIEWS: { id: SectorView; label: string; hint: string; usesRange: boolean }[] = [
  { id: "composition", label: "Composition", hint: "Goods vs services over time", usesRange: true },
  { id: "ranking", label: "Size", hint: "Sectors by latest GDP", usesRange: false },
  { id: "growth", label: "Growth", hint: "Year-over-year change by sector", usesRange: false },
  { id: "trends", label: "Trends", hint: "All sectors as small multiples", usesRange: true },
  { id: "heatmap", label: "Heatmap", hint: "Growth by sector and month", usesRange: true },
];

export const RANGES = [
  { id: "5y", label: "5 years", months: 60 },
  { id: "10y", label: "10 years", months: 120 },
  { id: "all", label: "All", months: 0 },
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
      <Group label="View">
        {VIEWS.map((v) => (
          <Chip key={v.id} active={view === v.id} onClick={() => onView(v.id)} title={v.hint}>
            {v.label}
          </Chip>
        ))}
      </Group>

      {/* Shown disabled rather than removed, so the row does not reflow as you
          switch views — but disabled, because on these views it cannot do
          anything and a live-looking dead control is a bug report waiting to
          happen. The title says why. */}
      <Group label="Range">
        {RANGES.map((r) => (
          <Chip
            key={r.id}
            active={range === r.id}
            onClick={() => onRange(r.id)}
            disabled={!rangeApplies}
            title={rangeApplies ? undefined : "This view reads the latest period only"}
          >
            {r.label}
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
