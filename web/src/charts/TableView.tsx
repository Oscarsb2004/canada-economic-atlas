/**
 * TableView.tsx — every chart's WCAG-clean twin.
 *
 * A tooltip must never be the only way to read a value, and colour must never
 * be the only encoding. So each chart ships with a table behind a disclosure:
 * the numbers stay reachable by keyboard, by screen reader, and by anyone who
 * cannot separate the hues.
 *
 * Collapsed by default because the chart is the primary reading. Present always,
 * because "the value is in the tooltip" is not an answer.
 *
 * `tabular-nums` is right HERE and wrong on a stat tile: these are columns that
 * must align vertically. On a large standalone figure the same setting makes
 * every digit as wide as a zero and the number reads loose.
 */

import type { ReactNode } from "react";

import { useI18n } from "../i18n";

interface Props {
  caption: string;
  columns: string[];
  rows: (string | number)[][];
  /** Right-align from this column index onward — the numeric ones. */
  numericFrom?: number;
  children?: ReactNode;
}

export function TableView({ caption, columns, rows, numericFrom = 1 }: Props) {
  const { s } = useI18n();
  return (
    <details style={{ marginTop: "var(--sp-2)" }}>
      <summary
        style={{
          cursor: "pointer",
          fontSize: "var(--fs-micro)",
          color: "var(--ink-muted)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {s.tableView(rows.length)}
      </summary>
      <div style={{ overflowX: "auto", marginTop: "var(--sp-2)" }}>
        <table
          style={{
            borderCollapse: "collapse",
            width: "100%",
            fontSize: "var(--fs-small)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          <caption
            style={{
              captionSide: "top",
              textAlign: "left",
              color: "var(--ink-muted)",
              fontSize: "var(--fs-micro)",
              paddingBottom: "var(--sp-1)",
            }}
          >
            {caption}
          </caption>
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th
                  key={c}
                  scope="col"
                  style={{
                    textAlign: i >= numericFrom ? "right" : "left",
                    borderBottom: "1px solid var(--ink-axis)",
                    padding: "3px 8px 3px 0",
                    color: "var(--ink-secondary)",
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                  }}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>
                {r.map((cell, ci) => (
                  <td
                    key={ci}
                    style={{
                      textAlign: ci >= numericFrom ? "right" : "left",
                      borderBottom: "1px solid var(--ink-gridline)",
                      padding: "3px 8px 3px 0",
                      whiteSpace: ci >= numericFrom ? "nowrap" : "normal",
                    }}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
