/**
 * specs.ts — the chart forms, chosen before their colours.
 *
 * Each builder answers one question with the form that question deserves. The
 * mapping is deliberate and is the reason there is no "sector chart" that tries
 * to do everything:
 *
 *   part-to-whole over time  → stacked area, TWO series
 *   compare magnitude        → horizontal bar, ONE hue
 *   many series at once      → small multiples, ONE hue
 *   above/below a baseline   → diverging bar / heatmap
 *   one series is the point  → emphasis: accent against de-emphasis grey
 *
 * WHY THE COMPOSITION CHART HAS TWO SERIES AND NOT TWENTY
 *
 * The obvious chart — twenty NAICS sectors stacked over time — is an
 * anti-pattern twice over: it cycles categorical hues past the eight the
 * palette defines, and it puts more than ~7 colour classes on screen carrying
 * meaning, past which adjacent classes blur. The taxonomy already solves it:
 * goods-producing plus services-producing equals all industries exactly, so the
 * composition runs on two slots and the twenty sectors get forms where their
 * count is not a colour problem.
 *
 * AND WHY IT READS THE CONSTANT-PRICE SERIES
 *
 * Chained dollars are not additive — measured at +0.311% drift on 2026-06,
 * against +0.000% for 2017 constant prices. A stacked chart asserts that the
 * parts make the whole, so it must read the basis where they actually do.
 */

import * as Plot from "@observablehq/plot";

import type { Company, Palette, Series } from "../data/bundle";
import { MARK, axisX, axisY, chartDefaults, fmtMoneyM, gridY, token } from "./Plot";

/**
 * Tooltip styling, shared.
 *
 * An HTML chart is interactive by default — the hover layer is part of the
 * deliverable, not an upgrade. Two rules from the interaction spec are encoded
 * here: the value leads and the series name follows (the reader already has the
 * series and wants the number), and the tip never becomes the ONLY way to read
 * a value, which is what the table twins are for.
 */
const TIP = {
  fill: "var(--surface-chart)",
  stroke: "var(--ink-axis)",
  textPadding: 6,
  fontSize: 11,
} as const;

export interface Row {
  code: string;
  label: string;
  period: string;
  date: Date;
  value: number;
}

const AGGREGATES = new Set(["T001", "T002", "T003"]);

/** StatCan periods are "1997-01" (monthly) or "1997" (annual). */
function toDate(period: string): Date {
  const [y, m] = period.split("-");
  return new Date(Number(y), m ? Number(m) - 1 : 0, 1);
}

/** Series to tidy rows, dropping nulls — a suppressed period is not a zero. */
export function toRows(series: Series[], codes?: Set<string>): Row[] {
  const out: Row[] = [];
  for (const s of series) {
    if (codes && !codes.has(s.code)) continue;
    for (let i = 0; i < s.periods.length; i++) {
      const v = s.values[i];
      if (v == null) continue;
      out.push({ code: s.code, label: s.label.en, period: s.periods[i], date: toDate(s.periods[i]), value: v });
    }
  }
  return out;
}

export function sectorsOnly(series: Series[]): Series[] {
  return series.filter((s) => s.geo === "CA" && !AGGREGATES.has(s.code));
}

/** Most recent non-null value per series. */
export function latestBySector(series: Series[]): { code: string; label: string; value: number }[] {
  return sectorsOnly(series)
    .map((s) => {
      const i = lastRealIndex(s.values);
      return i < 0 ? null : { code: s.code, label: s.label.en, value: s.values[i]! };
    })
    .filter((x): x is { code: string; label: string; value: number } => x != null)
    .sort((a, b) => b.value - a.value);
}

/** How many observations make a year, for this series' frequency. */
function periodsPerYear(frequency: string): number {
  switch (frequency) {
    case "monthly": return 12;
    case "quarterly": return 4;
    case "annual": return 1;
    default: return 12;
  }
}

/** Index of the last non-null value, or -1. */
function lastRealIndex(values: (number | null)[]): number {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] != null) return i;
  return -1;
}

/**
 * Year-over-year percent change per sector, at each sector's own latest
 * published period.
 *
 * Two things this gets right that the obvious version does not.
 *
 * It walks back to the last NON-NULL observation rather than reading
 * `values[n-1]`. StatCan routinely publishes one sector a month behind the
 * rest, and suppression happens too — reading the final index would make such a
 * sector vanish from this chart while still appearing in the ranking chart,
 * with nothing on screen to explain the discrepancy.
 *
 * And it derives the step from the series' own `frequency` instead of assuming
 * 12. Called with the annual provincial series, a hardcoded 12 would compare
 * 2025 against 2013 and label the result "year over year".
 *
 * A sector whose comparison period is itself null is dropped rather than
 * compared against some other period: a y/y number measured over the wrong
 * interval is worse than an absent one.
 */
export function yoyBySector(series: Series[]): { code: string; label: string; value: number }[] {
  return sectorsOnly(series)
    .map((s) => {
      const i = lastRealIndex(s.values);
      const j = i - periodsPerYear(s.frequency);
      if (i < 0 || j < 0) return null;
      const now = s.values[i];
      const then = s.values[j];
      if (now == null || then == null || then === 0) return null;
      return { code: s.code, label: s.label.en, value: ((now - then) / then) * 100 };
    })
    .filter((x): x is { code: string; label: string; value: number } => x != null)
    .sort((a, b) => b.value - a.value);
}

// ── 1. Composition over time ───────────────────────────────────────────────────

export function composition(constant: Series[], palette: Palette, width: number) {
  const rows = toRows(constant.filter((s) => s.geo === "CA"), new Set(["T002", "T003"]));
  const colors = [palette.categorical[0].hex, palette.categorical[1].hex];

  return Plot.plot({
    ...chartDefaults(190),
    width,
    marginLeft: 46,
    color: { domain: ["Goods-producing industries", "Services-producing industries"], range: colors },
    y: { label: null, tickFormat: (d: number) => fmtMoneyM(d) },
    marks: [
      gridY(),
      // A WASH, not a block. Two large areas at full chroma read loud and
      // childish at this size, which is the single most common way a dashboard
      // chart looks wrong. The fill is faint and identity comes from the crisp
      // boundary line drawn over it.
      Plot.areaY(rows, {
        x: "date",
        y: "value",
        fill: "label",
        fillOpacity: 0.18,
      }),
      // The band boundary at full strength: a 2px line is the mark spec, and a
      // sharp top edge is what makes a faint fill still legible.
      Plot.lineY(rows, {
        x: "date",
        y: "value",
        z: "label",
        stroke: "label",
        strokeWidth: MARK.lineWidth,
        strokeLinejoin: "round",
      }),
      axisY({ ticks: 4, tickFormat: (d: number) => fmtMoneyM(d as number) }),
      axisX({ ticks: 6 }),
      Plot.ruleY([0], { stroke: token("--ink-axis") }),
      // The crosshair finds the X: a hairline snaps to the nearest date, so the
      // reader aims at a month rather than at a 2px line.
      //
      // A bare pointer-driven rule, NOT Plot.crosshairX. The crosshair mark
      // also prints its own x and y readouts, which arrive unformatted — a raw
      // "2021-06-01T05:00Z" beside the tip's "Aug 2021 · $1.6T". Two readouts,
      // one of them wrong-looking, is worse than one.
      Plot.ruleX(rows, Plot.pointerX({ x: "date", stroke: token("--ink-secondary"), strokeWidth: 1 })),
      Plot.tip(
        rows,
        Plot.pointerX({
          x: "date",
          y: "value",
          ...TIP,
          format: {
            x: (d: Date) => d.toLocaleDateString("en-CA", { year: "numeric", month: "short" }),
            y: (d: number) => fmtMoneyM(d),
            z: true,
          },
        }),
      ),
    ],
  });
}

// ── 2. Sector ranking ──────────────────────────────────────────────────────────

export function ranking(series: Series[], palette: Palette, width: number) {
  const data = latestBySector(series);

  return Plot.plot({
    ...chartDefaults(Math.max(260, data.length * 17)),
    width,
    // Long sector names need the room; this is why the ranking is horizontal.
    marginLeft: 168,
    x: { grid: true, label: null, tickFormat: (d: number) => fmtMoneyM(d) },
    y: { label: null, domain: data.map((d) => d.label) },
    marks: [
      Plot.gridX({ stroke: token("--ink-gridline"), strokeWidth: 1 }),
      // ONE hue for every bar. Magnitude is not identity: colouring each bar by
      // its own value would double-encode what bar length already shows and
      // spend the only free channel on nothing.
      // On bars the MARK is the hit target — no crosshair. Each bar carries its
      // own tooltip and lifts slightly on hover so the reader sees it respond.
      Plot.barX(data, {
        x: "value",
        y: "label",
        fill: palette.categorical[0].hex,
        // 4px rounded data-end, square at the baseline.
        rx1: 4,
        insetTop: 1.5,
        insetBottom: 1.5,
        tip: { ...TIP, format: { x: (d: number) => fmtMoneyM(d), y: true } },
      }),
      axisY({ fontSize: 10 }),
      axisX({ ticks: 4, tickFormat: (d: number) => fmtMoneyM(d as number) }),
      Plot.ruleX([0], { stroke: token("--ink-axis") }),
    ],
  });
}

// ── 3. All-sector trends: small multiples ──────────────────────────────────────

export function smallMultiples(series: Series[], palette: Palette, width: number) {
  const rows = toRows(sectorsOnly(series));

  return Plot.plot({
    ...chartDefaults(560),
    width,
    marginLeft: 34,
    // Faceting is why Plot was chosen. Twenty sectors as twenty panels is the
    // design-system answer to "too many series", and here it is one option.
    fy: { label: null },
    facet: { data: rows, y: "label", marginRight: 4 },
    y: { label: null, ticks: 2, tickFormat: (d: number) => fmtMoneyM(d) },
    x: { label: null, ticks: 4 },
    marks: [
      gridY({ ticks: 2 }),
      Plot.lineY(rows, {
        x: "date",
        y: "value",
        stroke: palette.categorical[0].hex,
        strokeWidth: MARK.lineWidth - 0.6,
        curve: "linear",
      }),
    ],
  });
}

// ── 4. Growth heatmap ──────────────────────────────────────────────────────────

export function growthHeatmap(series: Series[], palette: Palette, width: number, months = 60) {
  const sectors = sectorsOnly(series);
  const rows: { label: string; date: Date; pct: number }[] = [];

  for (const s of sectors) {
    const n = s.periods.length;
    for (let i = Math.max(12, n - months); i < n; i++) {
      const now = s.values[i];
      const prev = s.values[i - 12];
      if (now == null || prev == null || prev === 0) continue;
      rows.push({ label: s.label.en, date: toDate(s.periods[i]), pct: ((now - prev) / prev) * 100 });
    }
  }

  const order = latestBySector(series).map((d) => d.label);
  const span = Math.max(6, ...rows.map((r) => Math.abs(r.pct)));

  return Plot.plot({
    ...chartDefaults(Math.max(260, sectors.length * 16)),
    width,
    marginLeft: 168,
    // Diverging: two hues that read as opposite, with a NEUTRAL midpoint.
    // Growth has a real zero, so the colour has to say which side of it a cell
    // is on — a sequential ramp here would hide the sign.
    color: {
      type: "diverging",
      scheme: undefined,
      range: [palette.diverging.negative[1], palette.diverging.midpoint, palette.diverging.positive[1]],
      domain: [-span, span],
      pivot: 0,
      label: "y/y %",
    },
    y: { label: null, domain: order },
    // `interval: "month"` is required, not cosmetic. A cell mark puts x on a
    // BAND scale, and handing a band scale raw Dates makes every distinct
    // timestamp its own category — Plot warns about exactly this. Declaring the
    // interval tells it these are monthly buckets, which is what they are.
    x: { label: null, ticks: 5, interval: "month" },
    marks: [
      Plot.cell(rows, {
        x: "date",
        y: "label",
        fill: "pct",
        inset: 0.5,
        tip: {
          ...TIP,
          format: {
            fill: (d: number) => `${d >= 0 ? "+" : ""}${d.toFixed(1)}%`,
            x: (d: Date) => d.toLocaleDateString("en-CA", { year: "numeric", month: "short" }),
            y: true,
          },
        },
      }),
      axisY({ fontSize: 10 }),
      axisX({ ticks: 5 }),
    ],
  });
}

// ── 5. Emphasis: one sector against the rest ───────────────────────────────────

export function emphasis(series: Series[], palette: Palette, width: number, selectedCode: string) {
  const rows = toRows(sectorsOnly(series));
  const others = rows.filter((r) => r.code !== selectedCode);
  const chosen = rows.filter((r) => r.code === selectedCode);

  return Plot.plot({
    ...chartDefaults(210),
    width,
    marginLeft: 52,
    y: { label: null, tickFormat: (d: number) => fmtMoneyM(d) },
    marks: [
      gridY(),
      // The nineteen others in de-emphasis grey: context, not competition.
      Plot.lineY(others, {
        x: "date",
        y: "value",
        z: "code",
        stroke: String(palette.roles.de_emphasis ?? palette.ink.axis),
        strokeWidth: 1,
      }),
      // The one that is the point, in the accent.
      Plot.lineY(chosen, {
        x: "date",
        y: "value",
        stroke: palette.categorical[0].hex,
        strokeWidth: MARK.lineWidth,
        strokeLinejoin: "round",
        strokeLinecap: "round",
      }),
      // A single end-dot, ringed in the surface colour so it stays legible
      // where it crosses the grey lines.
      Plot.dot(chosen.slice(-1), {
        x: "date",
        y: "value",
        r: MARK.dotRadius,
        fill: palette.categorical[0].hex,
        stroke: token("--surface-page"),
        strokeWidth: MARK.gap,
      }),
      axisY({ ticks: 4, tickFormat: (d: number) => fmtMoneyM(d as number) }),
      axisX({ ticks: 6 }),
      Plot.ruleX(chosen, Plot.pointerX({ x: "date", stroke: token("--ink-secondary"), strokeWidth: 1 })),
      Plot.tip(
        chosen,
        Plot.pointerX({
          x: "date",
          y: "value",
          ...TIP,
          format: {
            x: (d: Date) => d.toLocaleDateString("en-CA", { year: "numeric", month: "short" }),
            y: (d: number) => fmtMoneyM(d),
          },
        }),
      ),
    ],
  });
}

// ── 6. Contribution to growth ──────────────────────────────────────────────────

export function growthBars(series: Series[], palette: Palette, width: number) {
  const data = yoyBySector(series);
  const span = Math.max(...data.map((d) => Math.abs(d.value)), 3);

  return Plot.plot({
    ...chartDefaults(Math.max(260, data.length * 17)),
    width,
    marginLeft: 168,
    x: { label: null, domain: [-span, span], tickFormat: (d: number) => `${d > 0 ? "+" : ""}${d}%` },
    y: { label: null, domain: data.map((d) => d.label) },
    color: {
      type: "diverging",
      range: [palette.diverging.negative[1], palette.diverging.midpoint, palette.diverging.positive[1]],
      domain: [-span, span],
      pivot: 0,
    },
    marks: [
      Plot.gridX({ stroke: token("--ink-gridline"), strokeWidth: 1 }),
      Plot.barX(data, {
        x: "value",
        y: "label",
        fill: "value",
        insetTop: 1.5,
        insetBottom: 1.5,
        tip: { ...TIP, format: { x: (d: number) => `${d >= 0 ? "+" : ""}${d.toFixed(1)}%`, y: true, fill: false } },
      }),
      axisY({ fontSize: 10 }),
      axisX({ ticks: 5 }),
      // The baseline a diverging bar diverges from. Solid, one step off surface.
      Plot.ruleX([0], { stroke: token("--ink-axis"), strokeWidth: 1 }),
    ],
  });
}

// ── 7. Companies ───────────────────────────────────────────────────────────────

export function companyBars(companies: Company[], palette: Palette, width: number, top = 12) {
  const data = companies
    .filter((c) => c.weight_pct != null)
    .slice(0, top)
    .map((c) => ({ name: c.name, ticker: c.ticker, weight: c.weight_pct! }));

  return Plot.plot({
    ...chartDefaults(Math.max(180, data.length * 19)),
    width,
    marginLeft: 150,
    x: { label: null, tickFormat: (d: number) => `${d}%` },
    y: { label: null, domain: data.map((d) => d.name) },
    marks: [
      Plot.gridX({ stroke: token("--ink-gridline"), strokeWidth: 1 }),
      Plot.barX(data, {
        x: "weight",
        y: "name",
        fill: palette.categorical[0].hex,
        rx1: 4,
        insetTop: 2,
        insetBottom: 2,
        tip: { ...TIP, format: { x: (d: number) => `${d.toFixed(2)}%`, y: true } },
      }),
      axisY({ fontSize: 10 }),
      axisX({ ticks: 4 }),
      Plot.ruleX([0], { stroke: token("--ink-axis") }),
    ],
  });
}
