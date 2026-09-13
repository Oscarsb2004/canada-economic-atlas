/**
 * ProvincePanel — one province or territory in depth (BACKLOG R6).
 *
 * The page the reader reaches by clicking a province. Its first screen must
 * show three things together, as the owner asked: the flag, the name (with its
 * motto), and the largest sectors. Below them, how the jurisdiction's finances
 * have gone, as Finance Canada publishes them.
 *
 * WHOSE WORDS AND FIGURES
 *
 * - Sector shares: Statistics Canada's own percentages (36-10-0400). Listing
 *   them largest first is a sort of published figures, not a ranking of ours.
 * - Finances: Finance Canada's Fiscal Reference Tables, every column the
 *   jurisdiction's table publishes, under its own heading. Two are charted,
 *   picked by their English headings — the deficit-or-surplus column and the
 *   net debt column (Alberta's is "Net financial debt / assets (-)").
 * - The motto and the flag's description: Canadian Heritage, verbatim.
 * - The flag and coat of arms: Wikimedia Commons files, each credited with the
 *   licence and artist Commons records for it, linked to its file page.
 *
 * Nothing is summed, averaged or scored. Figures are formatted by the reader's
 * locale to at most two decimals, which also removes the binary-float noise the
 * workbook carries (a stored -163.92100000000028 reads -163.92).
 */

import { useEffect, useRef, useState } from "react";

import { PlotFigure } from "../charts/Plot";
import { TableView } from "../charts/TableView";
import { fiscalBars, fiscalLine } from "../charts/specs";
import { asset, safeExternalUrl, t, type Bundle, type CommonsImage } from "../data/bundle";
import { fmtPublished, useI18n } from "../i18n";
import type { ProvinceSummary } from "../map/Globe";

const TOP_SECTORS = 5;

export function ProvincePanel({
  bundle,
  province,
  onClose,
}: {
  bundle: Bundle;
  province: ProvinceSummary;
  onClose: () => void;
}) {
  const { lang, s } = useI18n();
  const name = t(province.name, lang);

  // Plot renders to a fixed pixel width, so the panel measures itself.
  const ref = useRef<HTMLElement>(null);
  const [width, setWidth] = useState(520);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const doc = bundle.provinceProfiles;
  const p = doc.provinces[province.code];

  const header = (flag: CommonsImage | null, motto: string) => (
    <header className="province-panel__header">
      <div className="province-panel__title">
        {flag && <img className="province-panel__flag" src={asset(flag.src)} alt={s.provinceFlagAlt(name)} />}
        <div>
          <p className="province-panel__eyebrow">{s.provinceEyebrow}</p>
          <h1>{name}</h1>
          {motto && <p className="province-panel__motto">{motto}</p>}
        </div>
      </div>
      <button type="button" className="province-panel__close" onClick={onClose}>
        {s.backToOverview}
      </button>
    </header>
  );

  if (!p) {
    return (
      <article className="province-panel" ref={ref}>
        {header(null, "")}
        <p className="muted">{s.provinceNoProfile}</p>
      </article>
    );
  }

  // ── Sectors: the latest period with a published All industries total ─────
  const periods = doc.sector_shares.periods;
  const total = p.sector_shares.T001 ?? [];
  let last = total.length - 1;
  while (last >= 0 && total[last] == null) last--;
  const shareYear = last >= 0 ? periods[last] : "";
  const shares = Object.entries(p.sector_shares)
    .filter(([code, values]) => code !== "T001" && last >= 0 && values[last] != null)
    .map(([code, values]) => ({ code, label: t(doc.sector_shares.industries[code], lang), value: values[last]! }))
    .sort((a, b) => b.value - a.value);

  // ── Finances ────────────────────────────────────────────────────────────
  const f = p.fiscal;
  const lastYear = f.years.length - 1;
  const balance = f.columns.find((c) => c.label.en.startsWith("Deficit"));
  const debt = f.columns.find((c) => c.label.en.startsWith("Net"));
  const notes = lang === "fr" ? f.notes.fr : f.notes.en;
  const insignia = [p.flag, p.arms].some((img) => img.restrictions.includes("insignia"));
  const heritage = safeExternalUrl(p.heritage_pages[lang]);
  const edition = safeExternalUrl(doc.fiscal.edition_page);

  const credit = (kind: string, img: CommonsImage) => {
    const href = safeExternalUrl(img.page_url);
    const text = s.provinceImageCredit(kind, img.title.replace(/^File:/, ""), img.licence, img.artist);
    return (
      <p className="province-panel__credit">
        {href ? <a href={href} target="_blank" rel="noreferrer">{text}</a> : text}
      </p>
    );
  };

  return (
    <article className="province-panel" ref={ref}>
      {header(p.flag, p.motto ? t(p.motto, lang) : "")}

      {/* The largest sectors, on the first screen with the flag and the name. */}
      <section className="province-panel__section">
        <h2>{s.provinceSectorsHeading(shareYear)}</h2>
        <ol className="province-panel__sectors">
          {shares.slice(0, TOP_SECTORS).map((x) => (
            <li key={x.code}>
              <span>{x.label}</span>
              <strong>{fmtPublished(x.value, lang)} %</strong>
            </li>
          ))}
        </ol>
        <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
          {s.provinceSectorsNote}
        </p>
        <TableView
          caption={s.provinceSectorsCaption(shareYear)}
          columns={[s.colSector, s.colNaics, s.colShare]}
          rows={shares.map((x) => [x.label, x.code, fmtPublished(x.value, lang)])}
          numericFrom={2}
        />
      </section>

      <section className="province-panel__section">
        <h2>{s.provinceFinanceHeading(f.years[lastYear] ?? "")}</h2>
        <p className="muted" style={{ fontSize: "var(--fs-micro)" }}>{s.provinceFinanceUnit}</p>
        <div className="province-panel__figures">
          {f.columns.map((c, i) => (
            <div key={i} className="province-panel__figure">
              <small>{t(c.label, lang)}</small>
              <strong>{c.values[lastYear] == null ? "—" : fmtPublished(c.values[lastYear]!, lang)}</strong>
            </div>
          ))}
        </div>

        {balance && (
          <>
            <h2 style={{ marginTop: "var(--sp-4)" }}>{t(balance.label, lang)}</h2>
            <PlotFigure
              label={s.provinceBalanceFigure(t(balance.label, lang))}
              deps={[f, width, bundle.palette, lang]}
              spec={() => fiscalBars(f.years, balance.values, bundle.palette, width, lang)}
            />
          </>
        )}
        {debt && (
          <>
            <h2 style={{ marginTop: "var(--sp-4)" }}>{t(debt.label, lang)}</h2>
            <PlotFigure
              label={s.provinceDebtFigure(t(debt.label, lang))}
              deps={[f, width, bundle.palette, lang]}
              spec={() => fiscalLine(f.years, debt.values, bundle.palette, width, lang)}
            />
          </>
        )}

        <TableView
          caption={s.provinceFinanceCaption(name)}
          columns={[s.colYear, ...f.columns.map((c) => t(c.label, lang))]}
          rows={f.years.map((year, i) => [
            year,
            ...f.columns.map((c) => (c.values[i] == null ? "—" : fmtPublished(c.values[i]!, lang))),
          ])}
          numericFrom={1}
        />
        {f.year_label_mismatches.map(([en, fr]) => (
          <p key={en} className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
            {s.provinceYearMismatch(en, fr)}
          </p>
        ))}
        {notes.length > 0 && (
          <details style={{ marginTop: "var(--sp-2)", fontSize: "var(--fs-small)" }}>
            <summary>{s.provinceFinanceNotes}</summary>
            {notes.map((note, i) => (
              <p key={i} className="muted" style={{ margin: "var(--sp-1) 0 0" }}>{note}</p>
            ))}
          </details>
        )}
        <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-2)" }}>
          {edition ? (
            <a href={edition} target="_blank" rel="noreferrer">
              {s.provinceFinanceSource(doc.fiscal.title, doc.fiscal.edition)}
            </a>
          ) : (
            s.provinceFinanceSource(doc.fiscal.title, doc.fiscal.edition)
          )}
        </p>
      </section>

      <section className="province-panel__section">
        <h2>{s.provinceIdentityHeading}</h2>
        <div className="province-panel__identity">
          <img className="province-panel__arms" src={asset(p.arms.src)} alt={s.provinceArmsAlt(name)} />
          <p style={{ fontSize: "var(--fs-small)" }}>{t(p.flag_description, lang)}</p>
        </div>
        <p className="province-panel__credit">
          {heritage ? (
            <a href={heritage} target="_blank" rel="noreferrer">{s.provinceFlagSource}</a>
          ) : (
            s.provinceFlagSource
          )}
        </p>
        {credit(s.provinceFlagWord, p.flag)}
        {credit(s.provinceArmsWord, p.arms)}
        {insignia && <p className="province-panel__credit">{s.provinceInsignia}</p>}
      </section>

      <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-4)" }}>{s.provinceNotYet}</p>
    </article>
  );
}
