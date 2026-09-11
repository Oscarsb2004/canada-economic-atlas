/**
 * CorridorPanel.tsx — what a trade corridor actually is, in Transport Canada's words.
 *
 * The map could draw trade infrastructure and could not say what any of it was
 * FOR. This is the answer, and every sentence in it is the government's:
 * Transport Canada's annual report names five corridors, describes each, and
 * lists the ports, railways, highways and border crossings that constitute it.
 *
 * WHAT THIS COMPONENT AUTHORS: its own section headings and the provenance
 * lines, which are visibly ours and live in `i18n.tsx`. Nothing else.
 *
 * THE NUMBERS STAY IN THE PARAGRAPH. Transport Canada's description says
 * "$249 billion", "158 million tonnes", "55% by pipeline". They render as part
 * of the sentence they were written in, never lifted into a styled figure —
 * a stat tile would be this project restating a federal claim in a form the
 * source never used, and would sit beside StatCan figures as though it were one.
 */

import type { Bundle, CorridorNodeKind, TradeCorridor } from "../data/bundle";
import { t } from "../data/bundle";
import { useI18n } from "../i18n";
import { PinButton } from "../tabs/TabStrip";

export function CorridorPanel({ bundle }: { bundle: Bundle }) {
  const { s } = useI18n();
  if (bundle.corridors.length === 0) return null;
  return (
    <section style={{ marginTop: "var(--sp-5)" }}>
      <h2
        style={{
          fontSize: "var(--fs-small)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--ink-muted)",
          margin: "0 0 var(--sp-1)",
        }}
      >
        {s.corridorsHeading(bundle.corridors.length)}
      </h2>
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "0 0 var(--sp-3)" }}>
        {s.corridorsIntroBefore}
        <strong>{s.corridorsIntroStrong}</strong>
        {s.corridorsIntroAfter}
      </p>
      {bundle.corridors.map((c) => (
        <Corridor key={c.corridor_id} corridor={c} />
      ))}
    </section>
  );
}

function Corridor({ corridor }: { corridor: TradeCorridor }) {
  const { lang, s } = useI18n();
  const byKind = (kind: CorridorNodeKind) => corridor.nodes.filter((n) => n.kind === kind);
  // `nodeKinds` satisfies a Record over the kind, so a new kind without a
  // heading is a build failure rather than a node rendered with no label.
  const nodeOrder = Object.keys(s.nodeKinds) as CorridorNodeKind[];

  return (
    <details
      style={{
        border: "var(--hairline)",
        borderRadius: "var(--radius)",
        padding: "var(--sp-2) var(--sp-3)",
        marginBottom: "var(--sp-2)",
      }}
    >
      <summary style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
        <span style={{ flex: 1 }}>{t(corridor.name, lang)}</span>
        <span className="muted" style={{ fontSize: "var(--fs-micro)" }}>
          {corridor.provinces.join(" · ")}
        </span>
      </summary>

      <div style={{ marginTop: "var(--sp-2)" }}>
        <PinButton
          kind="corridor"
          params={{ corridor: corridor.corridor_id }}
          defaultLabel={t(corridor.name, lang)}
        />

        {/* Transport Canada's own paragraph, including its figures. */}
        <p style={{ margin: "var(--sp-2) 0 0" }}>{t(corridor.description, lang)}</p>

        {/* The overlap, stated. A partial provincial mapping rendered silently
            reads as a complete one, and the Northern Corridor's is partial by
            construction — it is defined by latitude, not by province. */}
        {corridor.overlaps_provinces && t(corridor.unmapped_note, lang) && (
          <p
            className="muted"
            style={{
              fontSize: "var(--fs-micro)",
              margin: "var(--sp-2) 0 0",
              borderLeft: "2px solid var(--ink-axis)",
              paddingLeft: "var(--sp-2)",
            }}
          >
            {t(corridor.unmapped_note, lang)}
          </p>
        )}

        {/* The infrastructure list, mode by mode, verbatim. This is the part
            that answers "what IS this corridor" concretely. Where the two
            pages publish different bullet counts the pipeline carries them
            unpaired, so each language shows its own complete list. */}
        {corridor.modes.map((m, i) => {
          const items = m.items.filter((x) => (lang === "fr" ? x.fr : x.en));
          const shown = items.length > 0 ? items : m.items;
          if (shown.length === 0) return null;
          return (
            <div key={i} style={{ marginTop: "var(--sp-3)" }}>
              <div
                className="muted"
                style={{ fontSize: "var(--fs-micro)", textTransform: "uppercase", letterSpacing: "0.04em" }}
              >
                {t(m.label, lang)}
              </div>
              <ul style={{ margin: "2px 0 0", paddingLeft: "1.1em" }}>
                {shown.map((x, j) => (
                  <li key={j}>{t(x, lang)}</li>
                ))}
              </ul>
            </div>
          );
        })}

        {nodeOrder.map((kind) => {
          const nodes = byKind(kind);
          if (nodes.length === 0) return null;
          return (
            <div key={kind} style={{ marginTop: "var(--sp-3)" }}>
              <div
                className="muted"
                style={{ fontSize: "var(--fs-micro)", textTransform: "uppercase", letterSpacing: "0.04em" }}
              >
                {s.nodeKinds[kind]} · {s.onTheMap}
              </div>
              <p style={{ margin: "2px 0 0", fontSize: "var(--fs-small)" }}>
                {nodes.map((n) => t(n.name, lang)).join(" · ")}
              </p>
            </div>
          );
        })}

        <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-3)" }}>
          {s.corridorProvenance}
        </p>
      </div>
    </details>
  );
}
