/**
 * ProjectViewer.tsx — a project, in the government's own words.
 *
 * This is the "native viewer" the brief asked for: clicking a pin opens the
 * project here, in the page, rather than sending the reader to canada.ca.
 *
 * EVERY STRING IN THE BODY COMES FROM THE FEDERAL PAGE — except one section.
 *
 * Nothing here summarises, paraphrases, or rounds. In particular the dollar
 * figures and job counts stay inside their sentences — the pages say "Will
 * attract $5 billion in investment", and lifting that into a styled number
 * would be this app making a claim in a form the source never used. The only
 * text this component authors is its own section headings and the provenance
 * line, which are visibly ours and live in `i18n.tsx`.
 *
 * The exception is the industry section (BACKLOG C1). Which NAICS industry a
 * project belongs to is this atlas's reading, so it sits last, inside a dashed
 * frame with a "Derived" tag — the grammar a derived map pin already uses — and
 * it shows its working: the page's words for the asset and Statistics Canada's
 * words for the code.
 *
 * The source link is present but secondary. The point is that you do not have
 * to click it.
 */

import type {
  ConstructionListing, IndustriesDoc, Lang, Project, ProjectIndustries, Text, Update,
} from "../data/bundle";
import { assertNever, asset, safeExternalUrl, t } from "../data/bundle";
import { useI18n, type Strings } from "../i18n";
import { PinButton } from "../tabs/TabStrip";

interface Props {
  project: Project;
  industries: IndustriesDoc;
  onClose: () => void;
}

export function ProjectViewer({ project, industries, onClose }: Props) {
  const { lang, s } = useI18n();
  const hero = project.media.find((m) => m.role === "hero");
  const page = safeExternalUrl(t(project.page_url, lang));
  const verbatim = project.sources.find((x) => x.provenance === "page_verbatim");
  const benefits = benefitsFor(project, lang);
  const updates = updatesFor(project, lang);
  const placement = industries.projects.find((x) => x.slug === project.slug);

  return (
    <article style={{ padding: "var(--sp-4)" }}>
      <header style={{ display: "flex", alignItems: "start", gap: "var(--sp-3)" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: "var(--sp-2)", marginBottom: "var(--sp-2)" }}>
            {/* The MPO sector is carried in English only (BACKLOG B1a). */}
            <span className="tag">{project.sector}</span>
            {project.status.en && <span className="tag">{t(project.status, lang)}</span>}
          </div>
          <h1 style={{ fontSize: "var(--fs-title)", margin: 0, lineHeight: 1.25 }}>
            {t(project.name, lang)}
          </h1>
          <p className="secondary" style={{ margin: "var(--sp-2) 0 0" }}>
            {t(project.proponent, lang)}
          </p>
        </div>
        <PinButton
          kind="project"
          params={{ slug: project.slug }}
          defaultLabel={t(project.name, lang)}
        />
        <button
          type="button"
          onClick={onClose}
          aria-label={s.closeProject}
          style={{
            background: "transparent",
            border: "var(--hairline)",
            borderRadius: "var(--radius)",
            color: "var(--ink-secondary)",
            cursor: "pointer",
            fontSize: "var(--fs-body)",
            padding: "2px 8px",
          }}
        >
          ✕
        </button>
      </header>

      {hero?.web && (
        <img
          src={asset(hero.web)}
          alt={t(hero.alt, lang)}
          style={{
            width: "100%",
            borderRadius: "var(--radius)",
            margin: "var(--sp-4) 0 var(--sp-2)",
            display: "block",
          }}
        />
      )}

      {/* The location wording is the source's, carried in English only
          (BACKLOG B1a). The approximation caveat after it is ours: it restates
          the geometry's `approximate` flag, and is translated with the rest of
          the interface. */}
      <p className="muted" style={{ fontSize: "var(--fs-small)", margin: "0 0 var(--sp-4)" }}>
        {project.sites.map((x) => x.geometry.location_verbatim).filter(Boolean).join(" · ")}
        {project.sites.some((x) => x.geometry.approximate) && s.locationsApproximate}
      </p>

      <Section title={s.sectionDescription}>
        <p style={{ margin: 0 }}>{t(project.description, lang)}</p>
      </Section>

      {project.quick_facts.length > 0 && (
        <Section title={s.sectionQuickFacts}>
          <ul style={{ margin: 0, paddingLeft: "1.1em" }}>
            {project.quick_facts.map((f, i) => (
              <li key={i} style={{ marginBottom: "var(--sp-2)" }}>
                {f.label.en && <strong>{t(f.label, lang)}: </strong>}
                {t(f.body, lang)}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {benefits.length > 0 && (
        <Section title={s.sectionBenefits}>
          <ul style={{ margin: 0, paddingLeft: "1.1em" }}>
            {benefits.map((b, i) => (
              <li key={i} style={{ marginBottom: "var(--sp-2)" }}>
                {t(b, lang)}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {updates.length > 0 && (
        <Section title={s.sectionUpdates}>
          <ol style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {updates.map((u, i) => (
              <li
                key={i}
                style={{
                  borderLeft: "2px solid var(--ink-axis)",
                  paddingLeft: "var(--sp-3)",
                  marginBottom: "var(--sp-3)",
                }}
              >
                {/* Each page's own wording of the date: the French page
                    writes "19 mai, 2026", and showing the English date inside
                    a French entry would put words in it the page did not use. */}
                {((lang === "fr" && u.date_verbatim_fr) || u.date_verbatim || u.date_verbatim_fr) && (
                  <div className="muted" style={{ fontSize: "var(--fs-small)" }}>
                    {(lang === "fr" && u.date_verbatim_fr) || u.date_verbatim || u.date_verbatim_fr}
                  </div>
                )}
                <div>{t(u.body, lang)}</div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {project.sites.length > 1 && (
        <Section title={s.sectionSites}>
          <ul style={{ margin: 0, paddingLeft: "1.1em" }}>
            {project.sites.map((x, i) => (
              <li key={i}>{t(x.name, lang)}</li>
            ))}
          </ul>
        </Section>
      )}

      <IndustrySection placement={placement} doc={industries} lang={lang} s={s} />

      <footer
        style={{
          marginTop: "var(--sp-5)",
          paddingTop: "var(--sp-3)",
          borderTop: "var(--hairline)",
          fontSize: "var(--fs-small)",
        }}
        className="muted"
      >
        <div>{s.verbatimFooter(verbatim?.retrieved_at?.slice(0, 10) ?? "")}</div>
        {page && (
          <div style={{ marginTop: "var(--sp-1)" }}>
            <a href={page} target="_blank" rel="noreferrer noopener">
              {s.officialPage}
            </a>
          </div>
        )}
      </footer>
    </article>
  );
}

/**
 * Where this atlas places the project in NAICS, and why.
 *
 * Every placement shows the two quotes it rests on, so a reader can disagree
 * with the reading without taking anything on trust. A project with no
 * placement still renders the section and says so: `verify/` gates that all
 * eighteen are placed, and if that ever fails the viewer should show the gap
 * rather than quietly omit a section.
 */
function IndustrySection({
  placement,
  doc,
  lang,
  s,
}: {
  placement: ProjectIndustries | undefined;
  doc: IndustriesDoc;
  lang: Lang;
  s: Strings;
}) {
  return (
    <Section
      className="derived-block"
      title={
        <>
          {s.sectionIndustry} <span className="tag tag--derived">{s.derivedTag}</span>
        </>
      }
    >
      {!placement ? (
        <p className="muted" style={{ margin: 0 }}>{s.industryMissing}</p>
      ) : (
        <>
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {placement.operating.map((a) => (
              <li key={a.code} style={{ marginBottom: "var(--sp-4)" }}>
                <div><strong>{s.industryCode(a.code, t(a.title, lang))}</strong></div>
                <div className="secondary" style={{ fontSize: "var(--fs-small)" }}>
                  {s.industrySector(a.sector, t(a.sector_title, lang))}
                </div>
                <Quote text={s.quoted(t(a.asset, lang))} cite={s.industryAssetCite} />
                {a.evidence.map((e, i) => (
                  <Quote
                    key={i}
                    text={s.quoted(t(e.text, lang))}
                    cite={s.industryEvidenceCite(s.evidenceKinds[e.kind], e.code)}
                  />
                ))}
                {t(a.note, lang) && (
                  <p className="muted" style={{ fontSize: "var(--fs-small)", margin: "var(--sp-2) 0 0" }}>
                    {t(a.note, lang)}
                  </p>
                )}
              </li>
            ))}
          </ul>
          <p style={{ margin: 0 }}>{constructionLine(placement.construction, lang, s)}</p>
          {t(placement.construction.note, lang) && (
            <p className="muted" style={{ fontSize: "var(--fs-small)", margin: "var(--sp-1) 0 0" }}>
              {t(placement.construction.note, lang)}
            </p>
          )}
        </>
      )}
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "var(--sp-3) 0 0" }}>
        {t(doc.method, lang)} {s.industrySources}
      </p>
    </Section>
  );
}

/**
 * The construction listing as one sentence. Exhaustive over `basis`, because
 * "not in the inventory" and "not under construction" are different claims and
 * a new basis must not fall into either by default (CLAUDE.md §2b).
 */
function constructionLine(c: ConstructionListing, lang: Lang, s: Strings): string {
  const sector = t(c.sector_title, lang);
  switch (c.basis) {
    case "under_construction":
      return s.constructionListed(c.sector, sector, c.status?.status_field ?? "", t(c.status?.status, lang));
    case "not_under_construction":
      return s.constructionNotListed(c.sector, sector, c.status?.status_field ?? "", t(c.status?.status, lang));
    case "not_in_inventory":
      return s.constructionNotPublished(c.sector, sector);
    default:
      return assertNever(c.basis);
  }
}

function Quote({ text, cite }: { text: string; cite: string }) {
  return (
    <figure style={{ margin: "var(--sp-2) 0 0" }}>
      <blockquote
        style={{ margin: 0, paddingLeft: "var(--sp-3)", borderLeft: "2px solid var(--ink-axis)" }}
      >
        {text}
      </blockquote>
      <figcaption className="muted" style={{ fontSize: "var(--fs-micro)", paddingLeft: "var(--sp-3)" }}>
        {cite}
      </figcaption>
    </figure>
  );
}

/**
 * The Benefits bullets that belong to `lang`.
 *
 * Usually every bullet carries both languages and this is the whole list. It is
 * not when the two federal pages disagree on how many bullets they publish —
 * the French Taltson page has a fifth the English page omits. The pipeline
 * refuses to pair those positionally (a French sentence shown under an
 * unrelated English one would look perfectly correct), and instead carries each
 * page's list whole, tagged by the language it came from. Selecting on the
 * active language is what turns that back into one honest list per reader.
 *
 * The fallback matters: `t()` renders English when French is missing, so a
 * project with no French page at all would filter to nothing under `fr`. There,
 * showing the English is better than showing an empty section.
 */
function benefitsFor(project: Project, lang: Lang): Text[] {
  const own = project.benefits.filter((b) => (lang === "fr" ? b.fr : b.en));
  return own.length > 0 ? own : project.benefits;
}

/**
 * The Latest-updates entries that belong to `lang` — the same rule as
 * `benefitsFor`. Where the two pages list different entries the pipeline carries
 * both lists unpaired, so each reader sees their own page's complete list.
 */
function updatesFor(project: Project, lang: Lang): Update[] {
  const own = project.updates.filter((u) => (lang === "fr" ? u.body.fr : u.body.en));
  return own.length > 0 ? own : project.updates;
}

function Section({
  title,
  children,
  className,
}: {
  title: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={className} style={{ marginBottom: "var(--sp-5)" }}>
      <h2
        style={{
          fontSize: "var(--fs-small)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--ink-muted)",
          margin: "0 0 var(--sp-2)",
          fontWeight: 600,
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}
