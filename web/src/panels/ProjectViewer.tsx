/**
 * ProjectViewer.tsx — a project, in the government's own words.
 *
 * This is the "native viewer" the brief asked for: clicking a pin opens the
 * project here, in the page, rather than sending the reader to canada.ca.
 *
 * EVERY STRING BELOW COMES FROM THE FEDERAL PAGE.
 *
 * Nothing here summarises, paraphrases, or rounds. In particular the dollar
 * figures and job counts stay inside their sentences — the pages say "Will
 * attract $5 billion in investment", and lifting that into a styled number
 * would be this app making a claim in a form the source never used. The only
 * text this component authors is its own section headings and the provenance
 * line, which are visibly ours.
 *
 * The source link is present but secondary. The point is that you do not have
 * to click it.
 */

import type { Lang, Project } from "../data/bundle";
import { t } from "../data/bundle";
import { PinButton } from "../tabs/TabStrip";

interface Props {
  project: Project;
  lang: Lang;
  onClose: () => void;
}

export function ProjectViewer({ project, lang, onClose }: Props) {
  const hero = project.media.find((m) => m.role === "hero");
  const page = t(project.page_url, lang);
  const verbatim = project.sources.find((s) => s.provenance === "page_verbatim");

  return (
    <article style={{ padding: "var(--sp-4)" }}>
      <header style={{ display: "flex", alignItems: "start", gap: "var(--sp-3)" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: "var(--sp-2)", marginBottom: "var(--sp-2)" }}>
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
          aria-label="Close project"
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
          src={hero.web}
          alt={t(hero.alt, lang)}
          style={{
            width: "100%",
            borderRadius: "var(--radius)",
            margin: "var(--sp-4) 0 var(--sp-2)",
            display: "block",
          }}
        />
      )}

      {/* The source's own caveat, carried with the geometry rather than buried
          in a footer. It is the government's statement, not ours. */}
      <p className="muted" style={{ fontSize: "var(--fs-small)", margin: "0 0 var(--sp-4)" }}>
        {project.sites.map((s) => s.geometry.location_verbatim).filter(Boolean).join(" · ")}
        {project.sites.some((s) => s.geometry.approximate) &&
          " — locations are approximate and subject to final routing decisions"}
      </p>

      <Section title="Description">
        <p style={{ margin: 0 }}>{t(project.description, lang)}</p>
      </Section>

      {project.quick_facts.length > 0 && (
        <Section title="Quick facts">
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

      {project.updates.length > 0 && (
        <Section title="Latest updates">
          <ol style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {project.updates.map((u, i) => (
              <li
                key={i}
                style={{
                  borderLeft: "2px solid var(--ink-axis)",
                  paddingLeft: "var(--sp-3)",
                  marginBottom: "var(--sp-3)",
                }}
              >
                {u.date_verbatim && (
                  <div className="muted" style={{ fontSize: "var(--fs-small)" }}>
                    {u.date_verbatim}
                  </div>
                )}
                <div>{t(u.body, lang)}</div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {project.sites.length > 1 && (
        <Section title="Sites">
          <ul style={{ margin: 0, paddingLeft: "1.1em" }}>
            {project.sites.map((s, i) => (
              <li key={i}>{t(s.name, lang)}</li>
            ))}
          </ul>
        </Section>
      )}

      <footer
        style={{
          marginTop: "var(--sp-5)",
          paddingTop: "var(--sp-3)",
          borderTop: "var(--hairline)",
          fontSize: "var(--fs-small)",
        }}
        className="muted"
      >
        <div>
          Text reproduced verbatim from the Major Projects Office
          {verbatim?.retrieved_at && ` · captured ${verbatim.retrieved_at.slice(0, 10)}`}
          {" · Open Government Licence – Canada"}
        </div>
        {page && (
          <div style={{ marginTop: "var(--sp-1)" }}>
            <a href={page} target="_blank" rel="noreferrer noopener">
              Official project page ↗
            </a>
          </div>
        )}
      </footer>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: "var(--sp-5)" }}>
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
