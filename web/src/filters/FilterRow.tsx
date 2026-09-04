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

export const VIEWS: { id: SectorView; label: string; hint: string }[] = [
  { id: "composition", label: "Composition", hint: "Goods vs services over time" },
  { id: "ranking", label: "Size", hint: "Sectors by latest GDP" },
  { id: "growth", label: "Growth", hint: "Year-over-year change by sector" },
  { id: "trends", label: "Trends", hint: "All sectors as small multiples" },
  { id: "heatmap", label: "Heatmap", hint: "Growth by sector and month" },
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
}

export function FilterRow({ view, onView, range, onRange }: Props) {
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

      {/* Date range is the filter every reader reaches for, so it is present
          even where a view ignores it — a control that appears and disappears
          as you switch views is worse than one that is occasionally inert. */}
      <Group label="Range">
        {RANGES.map((r) => (
          <Chip key={r.id} active={range === r.id} onClick={() => onRange(r.id)}>
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
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      style={{
        // 24px minimum hit target, per the interaction spec.
        minHeight: 24,
        padding: "2px 9px",
        borderRadius: 999,
        cursor: "pointer",
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
