/**
 * SectorProjectsPanel.tsx — what is being built in a sector, and how big that
 * sector is (BACKLOG C4, goal G2).
 *
 * The question the whole layout implies and could not answer until the
 * projects were placed in NAICS (C1) and given NRCan's costs (C2). Three rules
 * shape it, each from a decision already on screen elsewhere:
 *
 * - A PLACEMENT IS DERIVED. Which sector a project belongs to is this atlas's
 *   reading, so the list sits in the dashed "Derived" frame the project viewer
 *   uses for the same placement.
 *
 * - COSTS ARE LISTED, NEVER SUMMED. Only some projects have a cost NRCan
 *   publishes, so a per-sector total would be a partial set read as the whole —
 *   the rule the project viewer states (C3). The panel counts projects; it does
 *   not add dollars.
 *
 * - COST AND GDP ARE DIFFERENT MEASURES. A cost is NRCan's figure for one
 *   project, in dollars; GDP is a yearly rate of output in chained 2017
 *   dollars. They sit side by side and are never added or divided.
 *
 * A project under construction is also counted in Construction (23), as C1
 * decided, so per-sector counts do not add up to the number of projects; the
 * table says so rather than hiding the double listing.
 */

import { TableView } from "../charts/TableView";
import { t, type Bundle, type Lang, type ProjectIndustries, type Series } from "../data/bundle";
import { fmtPublished, useI18n, type Strings } from "../i18n";

interface Member {
  slug: string;
  name: string;
  /** NAICS codes of the placements that put the project in this sector. */
  codes: string[];
  /** In this sector only because it is counted in construction while under construction. */
  construction: boolean;
  cost: string | null;
}

/** Index of the last non-null value, or -1. */
function lastRealIndex(values: (number | null)[]): number {
  for (let i = values.length - 1; i >= 0; i--) if (values[i] != null) return i;
  return -1;
}

/** The projects placed in `sector`: by an operating placement, or by the construction listing. */
function members(placements: ProjectIndustries[], names: Map<string, string>, sector: string,
                  lang: Lang, s: Strings): Member[] {
  const out: Member[] = [];
  for (const p of placements) {
    const codes = p.operating.filter((a) => a.sector === sector).map((a) => a.code);
    const construction = codes.length === 0 && p.construction.listed && p.construction.sector === sector;
    if (codes.length === 0 && !construction) continue;
    const status = p.construction.status;
    out.push({
      slug: p.slug,
      name: names.get(p.slug) ?? p.slug,
      codes,
      construction,
      cost: status && status.cost_musd != null
        ? s.costValue(t(status.cost_field, lang), fmtPublished(status.cost_musd, lang))
        : null,
    });
  }
  return out;
}

export function SectorProjectsPanel({
  bundle,
  sector,
  sectorLabel,
}: {
  bundle: Bundle;
  sector: string;
  sectorLabel: string;
}) {
  const { lang, s } = useI18n();
  const placements = bundle.industries.projects;
  const names = new Map(bundle.projects.map((p) => [p.slug, t(p.name, lang)]));
  const here = members(placements, names, sector, lang, s);
  const withCost = here.filter((m) => m.cost != null).length;

  // Every two-digit sector, in the order the StatCan cube publishes them — a
  // list, not a ranking.
  const sectorSeries = bundle.national.filter((x) => x.geo === "CA" && !x.code.startsWith("T"));
  const latest = (x: Series | undefined) => {
    const i = x ? lastRealIndex(x.values) : -1;
    return x && i >= 0 ? { value: x.values[i]!, period: x.periods[i] } : null;
  };
  const gdp = latest(sectorSeries.find((x) => x.code === sector));

  return (
    <section className="derived-block">
      <h3 style={{ fontSize: "var(--fs-small)", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-muted)", margin: "0 0 var(--sp-2)" }}>
        {s.sectorProjectsHeading} <span className="tag tag--derived">{s.derivedTag}</span>
      </h3>

      <p style={{ margin: 0, fontSize: "var(--fs-small)" }}>
        {here.length === 0 ? s.sectorProjectsNone(sectorLabel) : s.sectorProjectsCount(here.length, withCost)}
      </p>
      {gdp && (
        <p className="secondary" style={{ margin: "var(--sp-1) 0 0", fontSize: "var(--fs-small)" }}>
          {s.sectorProjectsGdp(fmtPublished(gdp.value, lang), gdp.period)}
        </p>
      )}

      {here.length > 0 && (
        <ul style={{ margin: "var(--sp-3) 0 0", padding: 0, listStyle: "none" }}>
          {here.map((m) => (
            <li key={m.slug} style={{ marginBottom: "var(--sp-2)", fontSize: "var(--fs-small)" }}>
              <strong>{m.name}</strong>
              <div className="secondary">
                {m.construction ? s.sectorProjectsConstruction : m.codes.map((c) => `NAICS ${c}`).join(" · ")}
                {" · "}
                {m.cost ?? s.sectorProjectsCostNone}
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-3) 0 0" }}>
        {s.sectorProjectsNote}
      </p>

      <TableView
        caption={s.sectorProjectsTable}
        columns={[s.colSector, s.colNaics, s.colProjects, s.colWithCost, s.colGdpLatest]}
        rows={sectorSeries.map((x) => {
          const m = members(placements, names, x.code, lang, s);
          const g = latest(x);
          return [
            t(x.label, lang),
            x.code,
            m.length,
            m.filter((y) => y.cost != null).length,
            g ? `${fmtPublished(g.value, lang)} (${g.period})` : "—",
          ];
        })}
        numericFrom={2}
      />
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-1) 0 0" }}>
        {s.sectorProjectsTableNote(placements.length)}
      </p>
    </section>
  );
}
