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
 *
 * Every chart's `deps` includes `lang`. PlotFigure rebuilds only when its deps
 * change, so a chart without it would keep English sector labels and month
 * names after the reader switched to French — the same silent staleness the
 * heatmap once had with its Range control.
 */

import { useMemo, useState } from "react";

import { PlotFigure } from "../charts/Plot";
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
import { t, type Bundle, type Lang, type Series } from "../data/bundle";
import { fmtMoneyM, fmtPct, fmtPercent, useI18n } from "../i18n";
import { PinButton } from "../tabs/TabStrip";

/** Trim every series to the last N months. 0 means all of it. */
function windowed(series: Series[], months: number): Series[] {
  if (!months) return series;
  return series.map((x) => {
    const start = Math.max(0, x.periods.length - months);
    return { ...x, periods: x.periods.slice(start), values: x.values.slice(start) };
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
  const { lang, s } = useI18n();
  // Seeded from a pinned tab when one is open. The component is remounted on
  // pin change, so these are initial values rather than controlled props —
  // switching views inside a pinned tab is allowed and does not edit the pin.
  const [view, setView] = useState<SectorView>(initialView ?? "composition");
  const [range, setRange] = useState<RangeId>(initialRange ?? "10y");
  const [focus, setFocus] = useState<string>(initialFocus ?? "31-33");

  const months = RANGES.find((r) => r.id === range)!.months;
  const national = useMemo(() => windowed(bundle.national, months), [bundle.national, months]);
  const constant = useMemo(() => windowed(bundle.constant, months), [bundle.constant, months]);

  const sectors = useMemo(() => latestBySector(bundle.national, lang), [bundle.national, lang]);
  const growth = useMemo(() => yoyBySector(bundle.national, lang), [bundle.national, lang]);
  const meta = bundle.national.find((x) => x.geo === "CA" && x.code === "T001");
  // Both lookups are Records over `SectorView`, so every view has a range rule,
  // a label and a hint by construction. This replaced `VIEWS.find(...)!` on a
  // list nothing forced to be complete, where a missing id was a runtime crash.
  const current = s.views[view];
  const usesRange = VIEWS[view].usesRange;

  // StatCan's own names for the two aggregates, in the reader's language.
  const aggregateLabel = (code: string) =>
    t(bundle.constant.find((x) => x.geo === "CA" && x.code === code)?.label, lang);
  const focusLabel = sectors.find((x) => x.code === focus)?.label ?? focus;

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
            label={s.compositionFigure}
            deps={[constant, width, bundle.palette, lang]}
            spec={() => composition(constant, bundle.palette, width, lang)}
          />
          {/* Legend: always present for two or more series, because identity
              must never rest on colour-matching alone. */}
          <Legend
            items={[
              { label: aggregateLabel("T002"), color: bundle.palette.categorical[0].hex },
              { label: aggregateLabel("T003"), color: bundle.palette.categorical[1].hex },
            ]}
          />
          <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            {s.compositionNote}
          </p>
          <TableView
            caption={s.compositionCaption}
            columns={[s.colPeriod, s.colGoods, s.colServices]}
            rows={tableComposition(constant, lang)}
          />
        </>
    ),
    ranking: () => (
        <>
          <PlotFigure
            label={s.rankingFigure}
            deps={[national, width, bundle.palette, lang]}
            spec={() => ranking(national, bundle.palette, width, lang)}
          />
          {/* No legend: one series, one colour. A box with a single swatch
              restates the title and costs space. */}
          <TableView
            caption={s.rankingCaption(meta?.periods.at(-1) ?? "")}
            columns={[s.colSector, s.colNaics, s.colGdp]}
            rows={sectors.map((x) => [x.label, x.code, fmtMoneyM(x.value, lang)])}
            numericFrom={2}
          />
        </>
    ),
    growth: () => (
        <>
          <PlotFigure
            label={s.growthFigure}
            /* Deps and spec read the SAME value. They disagreed once — deps on
               the windowed series, spec on the unwindowed one — which made this
               re-render on every range change and produce an identical chart.
               y/y-at-latest-month has no window, so both use the full series and
               the Range control is disabled for this view. */
            deps={[bundle.national, width, bundle.palette, lang]}
            spec={() => growthBars(bundle.national, bundle.palette, width, lang)}
          />
          <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            {s.growthNote}
          </p>
          <TableView
            caption={s.growthCaption}
            columns={[s.colSector, s.colNaics, s.colYoy]}
            rows={growth.map((g) => [g.label, g.code, fmtPct(g.value, lang)])}
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
            label={s.trendsFigure}
            deps={[national, width, bundle.palette, lang]}
            spec={() => smallMultiples(national, bundle.palette, width, lang)}
          />
          <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            {s.trendsNote}
          </p>
        </>
    ),
    heatmap: () => (
        <>
          <PlotFigure
            label={s.heatmapFigure}
            /* `months` MUST be here: it changes the output, and PlotFigure
               re-runs its effect only when deps change. Omitting it left the
               Range control silently inert on this view — the closure was
               rebuilt with the new value and never executed. */
            deps={[bundle.national, width, bundle.palette, months, lang]}
            spec={() => growthHeatmap(bundle.national, bundle.palette, width, lang, months || 360)}
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
        rangeApplies={usesRange}
      />

      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--sp-3)" }}>
        <h2 style={{ fontSize: "var(--fs-lead)", margin: "0 0 2px", flex: 1 }}>
          {current.label}
        </h2>
        <PinButton
          kind="sector-view"
          params={{ view, range }}
          defaultLabel={`${current.label} · ${s.ranges[range]}`}
        />
      </div>
      <p className="muted" style={{ margin: "0 0 var(--sp-3)", fontSize: "var(--fs-small)" }}>
        {current.hint}
      </p>

      {VIEW_BODIES[view]()}

      {/* Emphasis sits below every view: pick a sector and see it against the
          other nineteen. This is the most underused form in the system and the
          honest answer to "which line is mine". */}
      <section style={{ marginTop: "var(--sp-5)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", marginBottom: "var(--sp-2)" }}>
          <h3 style={{ fontSize: "var(--fs-small)", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", margin: 0, flex: 1 }}>
            {s.focusHeading}
          </h3>
          <PinButton
            kind="sector-focus"
            params={{ code: focus }}
            defaultLabel={focusLabel}
          />
        </div>
        <select
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          aria-label={s.focusSelect}
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
          {sectors.map((x) => (
            <option key={x.code} value={x.code}>
              {x.label}
            </option>
          ))}
        </select>
        <PlotFigure
          label={s.focusFigure(focusLabel)}
          deps={[national, width, focus, bundle.palette, lang]}
          spec={() => emphasis(national, bundle.palette, width, focus, lang)}
        />
      </section>

      <section style={{ marginTop: "var(--sp-5)" }}>
        <CompanyPanel bundle={bundle} width={width} />
      </section>

      <footer className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-5) 0" }}>
        {s.sectorSource(meta?.source_table ?? "", meta?.release_time || "—")}
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
 * itself so this panel cannot render the numbers without it — and it is now
 * READ from the payload, in both languages. Until B1 the panel rendered its own
 * hardcoded English copy and dropped the payload's, which kept CLAUDE.md §9 in
 * spirit and broke it in fact.
 *
 * Company names and GICS sector names are carried in English only (B1a).
 */
function CompanyPanel({ bundle, width }: { bundle: Bundle; width: number }) {
  const { lang, s } = useI18n();
  return (
    <>
      <h3 style={{ fontSize: "var(--fs-small)", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", margin: "0 0 var(--sp-1)" }}>
        {s.companiesHeading}
      </h3>
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "0 0 var(--sp-2)" }}>
        {s.companiesIndex} {t(bundle.companiesCaveat, lang)}
      </p>
      <PlotFigure
        label={s.companiesFigure}
        deps={[bundle.companies, width, bundle.palette, lang]}
        spec={() => companyBars(bundle.companies, bundle.palette, width, lang)}
      />
      <TableView
        caption={s.companiesCaption}
        columns={[s.colCompany, s.colTicker, s.colGics, s.colWeight]}
        rows={bundle.companies
          .slice(0, 25)
          .map((c) => [c.name, c.ticker, c.gics_sector, fmtPercent(c.weight_pct ?? 0, lang, 2)])}
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
  const { s } = useI18n();
  const stops = [...palette.diverging.negative].reverse().concat(palette.diverging.midpoint, palette.diverging.positive);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", marginTop: "var(--sp-2)" }}>
      <span className="muted" style={{ fontSize: "var(--fs-micro)" }}>{s.contracting}</span>
      <span style={{ display: "flex", borderRadius: 2, overflow: "hidden" }} aria-hidden="true">
        {stops.map((c, i) => (
          <span key={i} style={{ width: 16, height: 8, background: c }} />
        ))}
      </span>
      <span className="muted" style={{ fontSize: "var(--fs-micro)" }}>{s.expanding}</span>
    </div>
  );
}

/** The composition chart's table twin: the last twelve periods, side by side. */
function tableComposition(constant: Series[], lang: Lang): (string | number)[][] {
  const goods = constant.find((x) => x.geo === "CA" && x.code === "T002");
  const services = constant.find((x) => x.geo === "CA" && x.code === "T003");
  if (!goods || !services) return [];
  const n = goods.periods.length;
  const rows: (string | number)[][] = [];
  for (let i = Math.max(0, n - 12); i < n; i++) {
    rows.push([
      goods.periods[i],
      goods.values[i] == null ? "—" : fmtMoneyM(goods.values[i]!, lang),
      services.values[i] == null ? "—" : fmtMoneyM(services.values[i]!, lang),
    ]);
  }
  return rows.reverse();
}
