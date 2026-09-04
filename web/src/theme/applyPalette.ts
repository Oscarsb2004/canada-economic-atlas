/**
 * applyPalette.ts — turn the validated palette into CSS custom properties.
 *
 * The colour system is an artifact, not a preference: `registry/palette.yaml`
 * was produced by converting every Radix dark step to OKLCH, filtering to the
 * dark lightness band, and running the dataviz validator on candidate sets. The
 * recorded result is in that file.
 *
 * So the app READS it rather than restating it. Nothing in `web/src` hardcodes
 * a data colour. If a hex needs to change, it changes in the registry, the
 * validator runs again, and the app picks it up — an edit here would silently
 * un-validate a palette that was checked by script.
 *
 * CHROME vs DATA — the rule that keeps the validation meaningful.
 *
 * `--accent-*` is UI chrome: buttons, links, focus rings, the selected pin's
 * halo. A later accent picker may remap it to any Radix hue at runtime.
 * `--series-*` is data, and the accent picker must never touch it. If accents
 * repainted series, "colour follows the entity" would break and a validated
 * palette would become unvalidated on every accent change.
 */

import type { Palette } from "../data/bundle";

export function applyPalette(p: Palette): void {
  const root = document.documentElement.style;

  root.setProperty("--surface-page", p.surface.page);
  root.setProperty("--surface-chart", p.surface.chart);

  root.setProperty("--ink-primary", p.ink.primary);
  root.setProperty("--ink-secondary", p.ink.secondary);
  root.setProperty("--ink-muted", p.ink.muted);
  root.setProperty("--ink-gridline", p.ink.gridline);
  root.setProperty("--ink-axis", p.ink.axis);

  // Data slots, in the fixed validated order. Assigned in sequence, never
  // cycled: a 6th series is not a generated hue, it folds into "Other" or
  // faceting. Five is the hard cap — the all-pairs normal-vision margin is 15.9
  // against a floor of 15.
  p.categorical.forEach((c) => root.setProperty(`--series-${c.slot}`, c.hex));

  root.setProperty("--seq-lo", p.sequential.steps[0]);
  root.setProperty("--seq-hi", p.sequential.steps[p.sequential.steps.length - 1]);
  root.setProperty("--diverging-mid", p.diverging.midpoint);
  root.setProperty("--de-emphasis", String(p.roles.de_emphasis ?? p.ink.axis));

  Object.entries(p.status).forEach(([k, v]) => root.setProperty(`--status-${k}`, v));

  // UI chrome starts on slot 1 and is the only thing an accent picker may move.
  root.setProperty("--accent", p.categorical[0].hex);
}

/** The sequential ramp, for choropleth interpolation. */
export function sequentialStops(p: Palette): string[] {
  return p.sequential.steps;
}
