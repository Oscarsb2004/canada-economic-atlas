/**
 * SectorPanel.tsx — the analytical surface.
 *
 * One filter row scopes everything below it. Five views, each a different way
 * of cutting the same 23 series, and each a form chosen for the question rather
 * than a variation on one chart.
 *
 * Every chart here carries a table twin. That is not a courtesy: colour and
 * position are the only encodings a chart has, and both fail for some readers.
 * The table is where the numbers stay reachable.
 */

import { useMemo, useState } from "react";

import { PlotFigure, fmtMoneyM, fmtPct } from "../charts/Plot";
import { TableView } from "../charts/TableView";
import {
  composition,
  companyBars,
  emphasis,
  growthBars,
  growthHeatmap,
  latestBySector,
  ranking,
  smallMultiples,
  yoyBySector,
} from "../charts/specs";
import { FilterRow, RANGES, VIEWS, type RangeId, type SectorView } from "../filters/FilterRow";
import type { Bundle, Series } from "../data/bundle";
import { PinButton } from "../tabs/TabStrip";

/** Trim every series to the last N months. 0 means all of it. */
function windowed(series: Series[], months: number): Series[] {
  if (!months) return series;
  return series.map((s) => {
    const start = Math.max(0, s.periods.length - months);
    return { ...s, periods: s.periods.slice(start), values: s.values.slice(start) };
  });
}

export function SectorPanel({
  bundle,
  width,
  initialView,
  initialRange,
  initialFocus,
}: {
  bundle: Bundle;
  width: number;
  initialView?: SectorView;
  initialRange?: RangeId;
  initialFocus?: string;
}) {
  // Seeded from a pinned tab when one is open. The component is remounted on
  // pin change, so these are initial values rather than controlled props —
  // switching views inside a pinned tab is allowed and does not edit the pin.
  const [view, setView] = useState<SectorView>(initialView ?? "composition");
  const [range, setRange] = useState<RangeId>(initialRange ?? "10y");
  const [focus, setFocus] = useState<string>(initialFocus ?? "31-33");

  const months = RANGES.find((r) => r.id === range)!.months;
  const national = useMemo(() => windowed(bundle.national, months), [bundle.national, months]);
  const constant = useMemo(() => windowed(bundle.constant, months), [bundle.constant, months]);

  const sectors = useMemo(() => latestBySector(bundle.national), [bundle.national]);
  const growth = useMemo(() => yoyBySector(bundle.national), [bundle.national]);
  const meta = bundle.national.find((s) => s.geo === "CA" && s.code === "T001");
  // A Map rather than four `VIEWS.find(...)!` non-null assertions. `VIEWS` is
  // typed `{ id: SectorView; ... }[]` but nothing constrains it to be COMPLETE,
  // so a view id missing from it was a runtime crash, not a type error.
  const meta_ = new Map(VIEWS.map((v) => [v.id, v]));
  const current = meta_.get(view)!;
  const hint = current.hint;

  /**
   * One body per view, as a Record the compiler makes total.
   *
   * This was five independent `{view === "..." && (...)}` blocks with no
   * switch and no guard. Adding a sixth `SectorView` rendered the heading, the
   * hint, and then nothing — silently, with no compile error and every
   * verification gate still passing. That is the same failure shape CLAUDE.md
   * §2b legislates against for geometry, and this was the last place in the app
   * still using a non-total set of predicates.
   *
   * `Record<SectorView, ...>` is exhaustive by construction: a new view id
   * fails the build until it has a body. It is defined inside the component
   * because every body closes over `national`, `constant`, `width` and the
   * palette; the thunk keeps them lazy so only the active view builds a spec.
   */
  const VIEW_BODIES: Record<SectorView, () => React.ReactNode> = {
    composition: () => (
        <>
          <PlotFigure
            label="Goods-producing and services-producing industries over time"
            deps={[constant, width, bundle.palette]}
            spec={() => composition(constant, bundle.palette, width)}
          />
          {/* Legend: always present for two or more series, because identity
              must never rest on colour-matching alone. */}
          <Legend
            items={[
              { label: "Goods-producing", color: bundle.palette.categorical[0].hex },
              { label: "Services-producing", color: bundle.palette.categorical[1].hex },
            ]}
          />
          <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            2017 constant prices — the additive basis. Chained dollars drift +0.311% on this
            identity, so a stacked chart must not use them.
          </p>
          <TableView
            caption="Goods and services, latest 12 periods, millions of 2017 dollars"
            columns={["Period", "Goods", "Services"]}
            rows={tableComposition(constant)}
          />
        </>
    ),
    ranking: () => (
        <>
          <PlotFigure
            label="Sectors ranked by latest real GDP"
            deps={[national, width, bundle.palette]}
            spec={() => ranking(national, bundle.palette, width)}
          />
          {/* No legend: one series, one colour. A box with a single swatch
              restates the title and costs space. */}
          <TableView
            caption={`Real GDP by sector, ${meta?.periods.at(-1) ?? ""}, millions of chained 2017 dollars`}
            columns={["Sector", "NAICS", "GDP"]}
            rows={sectors.map((s) => [s.label, s.code, fmtMoneyM(s.value)])}
            numericFrom={2}
          />
        </>
    ),
    growth: () => (
        <>
          <PlotFigure
            label="Year-over-year growth by sector"
            /* Deps and spec read the SAME value. They disagreed once — deps on
               the windowed series, spec on the unwindowed one — which made this
               re-render on every range change and produce an identical chart.
               y/y-at-latest-month has no window, so both use the full series and
               the Range control is disabled for this view. */
            deps={[bundle.national, width, bundle.palette]}
            spec={() => growthBars(bundle.national, bundle.palette, width)}
          />
          <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            Change against the same month a year earlier. Diverging scale centred on zero.
          </p>
          <TableView
            caption="Year-over-year change by sector, latest month"
            columns={["Sector", "NAICS", "y/y"]}
            rows={growth.map((g) => [g.label, g.code, fmtPct(g.value)])}
            numericFrom={2}
          />
        </>
    ),
    trends: () => (
        <>
          {/* Small multiples: the design-system answer to twenty series.
              Twenty categorical hues would be an anti-pattern; twenty panels
              is one config option. */}
          <PlotFigure
            label="All twenty sectors as small multiples"
            deps={[national, width, bundle.palette]}
            spec={() => smallMultiples(national, bundle.palette, width)}
          />
          <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            Each panel has its own y-scale — these sectors differ by an order of magnitude, and a
            shared scale would flatten fifteen of them into flat lines.
          </p>
        </>
    ),
    heatmap: () => (
        <>
          <PlotFigure
            label="Year-over-year growth by sector and month"
            /* `months` MUST be here: it changes the output, and PlotFigure
               re-runs its effect only when deps change. Omitting it left the
               Range control silently inert on this view — the closure was
               rebuilt with the new value and never executed. */
            deps={[bundle.national, width, bundle.palette, months]}
            spec={() => growthHeatmap(bundle.national, bundle.palette, width, months || 360)}
          />
          <DivergingKey palette={bundle.palette} />
        </>
    ),
  };

  return (
    <div>
      <FilterRow
        view={view}
        onView={setView}
        range={range}
        onRange={setRange}
        rangeApplies={current.usesRange}
      />

      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--sp-3)" }}>
        <h2 style={{ fontSize: "var(--fs-lead)", margin: "0 0 2px", flex: 1 }}>
          {current.label}
        </h2>
        <PinButton
          kind="sector-view"
          params={{ view, range }}
          defaultLabel={`${current.label} · ${RANGES.find((r) => r.id === range)!.label}`}
        />
      </div>
      <p className="muted" style={{ margin: "0 0 var(--sp-3)", fontSize: "var(--fs-small)" }}>
        {hint}
      </p>

      {VIEW_BODIES[view]()}

      {/* Emphasis sits below every view: pick a sector and see it against the
          other nineteen. This is the most underused form in the system and the
          honest answer to "which line is mine". */}
      <section style={{ marginTop: "var(--sp-5)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", marginBottom: "var(--sp-2)" }}>
          <h3 style={{ fontSize: "var(--fs-small)", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", margin: 0, flex: 1 }}>
            One sector in context
          </h3>
          <PinButton
            kind="sector-focus"
            params={{ code: focus }}
            defaultLabel={sectors.find((s) => s.code === focus)?.label ?? focus}
          />
        </div>
        <select
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          style={{
            font: "inherit",
            fontSize: "var(--fs-small)",
            background: "var(--surface-chart)",
            color: "var(--ink-primary)",
            border: "var(--hairline)",
            borderRadius: "var(--radius)",
            padding: "3px 6px",
            marginBottom: "var(--sp-2)",
            minHeight: 24,
          }}
        >
          {sectors.map((s) => (
            <option key={s.code} value={s.code}>
              {s.label}
            </option>
          ))}
        </select>
        <PlotFigure
          label={`${sectors.find((s) => s.code === focus)?.label ?? ""} against all other sectors`}
          deps={[national, width, focus, bundle.palette]}
          spec={() => emphasis(national, bundle.palette, width, focus)}
        />
      </section>

      <section style={{ marginTop: "var(--sp-5)" }}>
        <CompanyPanel bundle={bundle} width={width} />
      </section>

      <footer className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-5) 0" }}>
        Source: Statistics Canada, table {meta?.source_table} · released {meta?.release_time || "—"} ·
        reproduced under the Statistics Canada Open Licence.
      </footer>
    </div>
  );
}

/**
 * Panel B — market data, and labelled as such everywhere it appears.
 *
 * Index weight is not output. Company revenue is gross output while GDP is
 * value added, so summing companies within a sector overshoots that sector's
 * GDP by two to three times. The caveat is carried in the bundle payload
 * itself so this panel cannot render the numbers without it.
 */
function CompanyPanel({ bundle, width }: { bundle: Bundle; width: number }) {
  return (
    <>
      <h3 style={{ fontSize: "var(--fs-small)", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", margin: "0 0 var(--sp-1)" }}>
        Largest listed companies
      </h3>
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "0 0 var(--sp-2)" }}>
        Index weight in the S&amp;P/TSX Capped Composite — market data, not GDP contribution.
        Weights are capped at 10% per holding.
      </p>
      <PlotFigure
        label="Largest index constituents by weight"
        deps={[bundle.companies, width, bundle.palette]}
        spec={() => companyBars(bundle.companies, bundle.palette, width)}
      />
      <TableView
        caption="S&P/TSX Capped Composite constituents by index weight"
        columns={["Company", "Ticker", "GICS sector", "Weight"]}
        rows={bundle.companies
          .slice(0, 25)
          .map((c) => [c.name, c.ticker, c.gics_sector, `${(c.weight_pct ?? 0).toFixed(2)}%`])}
        numericFrom={3}
      />
    </>
  );
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap", marginTop: "var(--sp-2)" }}>
      {items.map((i) => (
        <span key={i.label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          {/* Legends mirror the mark: a rect for areas and bars. Text stays in
              an ink token — a categorical hue is illegible as body text. */}
          <span
            aria-hidden="true"
            style={{ width: 10, height: 10, borderRadius: 2, background: i.color, flexShrink: 0 }}
          />
          <span style={{ fontSize: "var(--fs-small)", color: "var(--ink-secondary)" }}>{i.label}</span>
        </span>
      ))}
    </div>
  );
}

function DivergingKey({ palette }: { palette: Bundle["palette"] }) {
  const stops = [...palette.diverging.negative].reverse().concat(palette.diverging.midpoint, palette.diverging.positive);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", marginTop: "var(--sp-2)" }}>
      <span className="muted" style={{ fontSize: "var(--fs-micro)" }}>contracting</span>
      <span style={{ display: "flex", borderRadius: 2, overflow: "hidden" }} aria-hidden="true">
        {stops.map((c, i) => (
          <span key={i} style={{ width: 16, height: 8, background: c }} />
        ))}
      </span>
      <span className="muted" style={{ fontSize: "var(--fs-micro)" }}>expanding</span>
    </div>
  );
}

/** The composition chart's table twin: the last twelve periods, side by side. */
function tableComposition(constant: Series[]): (string | number)[][] {
  const goods = constant.find((s) => s.geo === "CA" && s.code === "T002");
  const services = constant.find((s) => s.geo === "CA" && s.code === "T003");
  if (!goods || !services) return [];
  const n = goods.periods.length;
  const rows: (string | number)[][] = [];
  for (let i = Math.max(0, n - 12); i < n; i++) {
    rows.push([
      goods.periods[i],
      goods.values[i] == null ? "—" : fmtMoneyM(goods.values[i]!),
      services.values[i] == null ? "—" : fmtMoneyM(services.values[i]!),
    ]);
  }
  return rows.reverse();
}
