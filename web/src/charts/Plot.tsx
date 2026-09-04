/**
 * Plot.tsx — one wrapper, then every chart is a spec.
 *
 * Observable Plot renders imperatively into a DOM node, so this component owns
 * the ref/effect dance once and nothing else in the app has to. That is the
 * whole reason Plot was chosen over a JSX chart library: faceting and small
 * multiples are a parameter here, and "compare all twenty sectors" is a line of
 * config rather than a hand-written loop.
 *
 * THE MARK SPECS LIVE HERE, NOT IN EACH CHART.
 *
 * Bar thickness, line width, marker size, gridline weight, the surface gap —
 * these are fixed across every chart in the product, so they are applied once
 * in `chartDefaults()` and inherited. A chart that wants a heavier line is
 * almost always a chart that should have picked a different form.
 *
 * Two rules from the design system that are easy to violate by accident and are
 * enforced by construction below:
 *
 *   Text never wears the data colour. Marks carry the series hue; labels,
 *   values, legends and axis text use ink tokens. A light categorical hue is
 *   illegible as text on the surface.
 *
 *   Gridlines are solid hairlines one step off the surface. Never dashed —
 *   dashing reads as "projection" or "threshold" when it is just a grid.
 */

import { useEffect, useRef } from "react";
import * as Plot from "@observablehq/plot";

/** Read a CSS custom property set by applyPalette(). */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Mark specs, fixed across the product. */
export const MARK = {
  lineWidth: 2,
  barMaxWidth: 24,
  dotRadius: 4,
  /** A 2px gap in the surface colour separates touching marks. Never a stroke. */
  gap: 2,
  areaOpacity: 0.1,
} as const;

/**
 * Plot options every chart starts from.
 *
 * `style` sets the surface and ink so Plot's own text inherits the theme rather
 * than defaulting to black-on-white, which is what an unstyled Plot does inside
 * a dark app.
 */
export function chartDefaults(height = 200): Plot.PlotOptions {
  return {
    height,
    marginLeft: 52,
    marginRight: 16,
    marginTop: 12,
    marginBottom: 28,
    style: {
      background: "transparent",
      color: token("--ink-secondary"),
      fontFamily: "var(--font-ui)",
      fontSize: "10px",
      overflow: "visible",
    },
    x: { grid: false, tickSize: 0, label: null },
    y: {
      grid: true,
      tickSize: 0,
      label: null,
      // Hairline, solid, one step off the surface. Recessive by construction.
      ...({ } as object),
    },
  };
}

interface Props {
  /** Build the plot. Returning null renders nothing, for empty states. */
  spec: () => (SVGSVGElement | HTMLElement) | null;
  /** Changing any of these rebuilds the chart. */
  deps: unknown[];
  /** Accessible name; a chart with no name is unusable to a screen reader. */
  label: string;
  className?: string;
}

export function PlotFigure({ spec, deps, label, className }: Props) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const node = spec();
    if (node) {
      // Plot's own SVG is decorative to assistive tech; the figure's aria-label
      // and the table twin carry the meaning.
      node.setAttribute("aria-hidden", "true");
      el.append(node);
    }
    return () => {
      if (node) node.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return (
    <div
      ref={host}
      className={className}
      role="img"
      aria-label={label}
      style={{ overflowX: "auto" }}
    />
  );
}

/**
 * A recessive hairline grid, applied as a Plot mark rather than an axis option
 * so its colour comes from the theme.
 */
export function gridY(options: Plot.GridYOptions = {}) {
  return Plot.gridY({ stroke: token("--ink-gridline"), strokeOpacity: 1, strokeWidth: 1, ...options });
}

export function axisY(options: Plot.AxisYOptions = {}) {
  return Plot.axisY({ tickSize: 0, fill: token("--ink-muted"), ...options });
}

export function axisX(options: Plot.AxisXOptions = {}) {
  return Plot.axisX({ tickSize: 0, fill: token("--ink-muted"), ...options });
}

/** Compact currency for axis ticks and labels: 2,369,309 (millions) → $2.4T. */
export function fmtMoneyM(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}T`;
  if (abs >= 1_000) return `$${(v / 1_000).toFixed(0)}B`;
  return `$${v.toFixed(0)}M`;
}

export function fmtPct(v: number, digits = 1): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}
