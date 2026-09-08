/**
 * CorridorPanel.tsx — what a trade corridor actually is, in Transport Canada's words.
 *
 * The map could draw trade infrastructure and could not say what any of it was
 * FOR. This is the answer, and every sentence in it is the government's:
 * Transport Canada's annual report names five corridors, describes each, and
 * lists the ports, railways, highways and border crossings that constitute it.
 *
 * WHAT THIS COMPONENT AUTHORS: its own section headings and the provenance
 * lines, which are visibly ours. Nothing else.
 *
 * THE NUMBERS STAY IN THE PARAGRAPH. Transport Canada's description says
 * "$249 billion", "158 million tonnes", "55% by pipeline". They render as part
 * of the sentence they were written in, never lifted into a styled figure —
 * a stat tile would be this project restating a federal claim in a form the
 * source never used, and would sit beside StatCan figures as though it were one.
 */

import type { Bundle, CorridorNodeKind, Lang, TradeCorridor } from "../data/bundle";
import { t } from "../data/bundle";
import { PinButton } from "../tabs/TabStrip";

/**
 * How each node kind is described. Keyed on the kind, so a new one is a compile
 * error rather than a node that renders with no label.
 */
const NODE_HEADING: Record<CorridorNodeKind, { en: string; fr: string }> = {
  port: { en: "Ports", fr: "Ports" },
  border_crossing: { en: "Border crossings", fr: "Postes frontaliers" },
};

const NODE_ORDER = Object.keys(NODE_HEADING) as CorridorNodeKind[];

export function CorridorPanel({ bundle, lang }: { bundle: Bundle; lang: Lang }) {
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
        Trade corridors · {bundle.corridors.length}
      </h2>
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "0 0 var(--sp-3)" }}>
        Transport Canada's national trade corridors, in its own words. The
        corridors <strong>do not partition Canada</strong> — the Northern
        Corridor is defined by latitude and overlaps the four described by
        province.
      </p>
      {bundle.corridors.map((c) => (
        <Corridor key={c.corridor_id} corridor={c} lang={lang} />
      ))}
    </section>
  );
}

function Corridor({ corridor, lang }: { corridor: TradeCorridor; lang: Lang }) {
  const byKind = (kind: CorridorNodeKind) => corridor.nodes.filter((n) => n.kind === kind);

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
            that answers "what IS this corridor" concretely. */}
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

        {NODE_ORDER.map((kind) => {
          const nodes = byKind(kind);
          if (nodes.length === 0) return null;
          // `NODE_HEADING` is a Record over the kind, so this cannot be
          // undefined — the totality guard is the type, not a runtime check.
          const heading = NODE_HEADING[kind];
          return (
            <div key={kind} style={{ marginTop: "var(--sp-3)" }}>
              <div
                className="muted"
                style={{ fontSize: "var(--fs-micro)", textTransform: "uppercase", letterSpacing: "0.04em" }}
              >
                {lang === "fr" ? heading.fr : heading.en} · on the map
              </div>
              <p style={{ margin: "2px 0 0", fontSize: "var(--fs-small)" }}>
                {nodes.map((n) => t(n.name, lang)).join(" · ")}
              </p>
            </div>
          );
        })}

        <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-3)" }}>
          Description and infrastructure reproduced verbatim from Transport Canada ·
          Open Government Licence – Canada. Province mapping and node positions are
          derived by this project: Transport Canada names these facilities and
          publishes no coordinates for them.
        </p>
      </div>
    </details>
  );
}
