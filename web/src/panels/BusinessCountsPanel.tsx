/**
 * BusinessCountsPanel.tsx — how many business locations with employees a sector
 * has, and how big they are, as Statistics Canada counts them (BACKLOG Q2b).
 *
 * It replaced a list of named companies whose source forbade public reuse
 * (CLAUDE.md §9). The figures are StatCan's; nothing here is computed except
 * formatting. Size ranges are drawn in StatCan's own order, smallest first,
 * never sorted by count — a sort would be a ranking the table does not make.
 *
 * StatCan's notes travel with the chart, because the two that matter change how
 * the numbers read: these are LOCATIONS, not firms, and the size ranges must not
 * be used to estimate employees.
 */

import { useState } from "react";

import { PlotFigure } from "../charts/Plot";
import { TableView } from "../charts/TableView";
import { businessSizeBars } from "../charts/specs";
import { t, type Bundle } from "../data/bundle";
import { LOCALE, useI18n } from "../i18n";

export function BusinessCountsPanel({
  bundle,
  width,
  sector,
  sectorLabel,
}: {
  bundle: Bundle;
  width: number;
  sector: string;
  sectorLabel: string;
}) {
  const { lang, s } = useI18n();
  const doc = bundle.businessCounts;
  const [geo, setGeo] = useState("CA");

  const row = doc.counts[geo]?.[sector];
  const geoName = t(doc.geographies.find((g) => g.code === geo)?.name, lang);
  const count = new Intl.NumberFormat(LOCALE[lang]);
  // Index 0 is StatCan's "Total, with employees"; the ranges follow it. A null
  // range has no published row, and the pipeline has shown the total leaves
  // none for it — it draws as zero and is marked in the table.
  const bands = row
    ? doc.size_ranges.slice(1).map((range, i) => ({
        label: t(range, lang),
        value: row[i + 1] ?? 0,
        unpublished: row[i + 1] == null,
      }))
    : [];
  const anyUnpublished = bands.some((b) => b.unpublished);

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", marginBottom: "var(--sp-2)" }}>
        <h3 style={{ fontSize: "var(--fs-small)", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", margin: 0, flex: 1 }}>
          {s.businessHeading}
        </h3>
        <select
          value={geo}
          onChange={(e) => setGeo(e.target.value)}
          aria-label={s.businessGeo}
          style={{
            font: "inherit",
            fontSize: "var(--fs-small)",
            background: "var(--surface-chart)",
            color: "var(--ink-primary)",
            border: "var(--hairline)",
            borderRadius: "var(--radius)",
            padding: "3px 6px",
            minHeight: 24,
          }}
        >
          {doc.geographies.map((g) => (
            <option key={g.code} value={g.code}>
              {t(g.name, lang)}
            </option>
          ))}
        </select>
      </div>

      {row ? (
        <>
          <p style={{ margin: "0 0 var(--sp-2)", fontSize: "var(--fs-small)" }}>
            {s.businessTotal(count.format(row[0] ?? 0), sectorLabel, geoName)}
          </p>
          <PlotFigure
            label={s.businessFigure(sectorLabel, geoName)}
            deps={[doc.table, geo, sector, width, bundle.palette, lang]}
            spec={() => businessSizeBars(bands, bundle.palette, width, lang)}
          />
          <TableView
            caption={s.businessCaption(sectorLabel, geoName)}
            columns={[s.colSize, s.colLocations]}
            rows={bands.map((b) => [b.label, b.unpublished ? `${count.format(0)}*` : count.format(b.value)])}
            numericFrom={1}
          />
          {anyUnpublished && (
            <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-1) 0 0" }}>
              {s.businessUnpublished}
            </p>
          )}
        </>
      ) : (
        <p className="muted" style={{ fontSize: "var(--fs-small)" }}>{s.businessNone}</p>
      )}

      <details style={{ marginTop: "var(--sp-2)" }}>
        <summary className="muted" style={{ cursor: "pointer", fontSize: "var(--fs-micro)" }}>
          {s.businessNotes}
        </summary>
        <ol className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-1) 0 0", paddingLeft: "1.2em" }}>
          {doc.notes.map((n) => (
            <li key={n.id}>{t(n.text, lang)}</li>
          ))}
        </ol>
      </details>
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-2) 0 0" }}>
        {s.businessSource(t(doc.title, lang), doc.table, doc.release_time)}
      </p>
    </>
  );
}
