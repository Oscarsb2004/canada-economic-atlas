/**
 * TimelinePanel.tsx — the Major Projects Office portfolio, in the order things
 * happened (BACKLOG B3).
 *
 * EVERY ENTRY IS A FEDERAL SENTENCE, REPRODUCED WHOLE.
 *
 * The one thing this panel does is ORDER the entries, by the date each one opens
 * with — parsed by the pipeline at the precision the page published it. It adds
 * no events, summarises nothing and merges nothing. An entry that names no date
 * gets none: undated entries are listed apart, in the order their page publishes
 * them, and never placed on the time axis by borrowing a neighbour's date.
 *
 * A month-only or year-only date ("In July 2026", "In 2022") is drawn as a
 * hollow mark at the start of its month or year and labelled with its
 * precision, so a position on the axis never claims a day the government did
 * not write.
 *
 * Every count on screen is counted from the bundle at render time.
 */

import { useMemo, useState } from "react";

import { PlotFigure } from "../charts/Plot";
import { timeline, type TimelineMark } from "../charts/specs";
import { t, type Bundle, type Lang, type Project, type Update } from "../data/bundle";
import { LOCALE, useI18n } from "../i18n";

interface Entry {
  project: Project;
  update: Update;
  /** Position on its own page, which orders ties and the undated list. */
  index: number;
}

/** "2026-07" → month, "2022" → year, "2026-07-15" → day. */
function precisionOf(iso: string): TimelineMark["precision"] {
  return iso.length === 4 ? "year" : iso.length === 7 ? "month" : "day";
}

function toDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/** The date as the reader's language page wrote it. */
function written(update: Update, lang: Lang): string {
  return (lang === "fr" && update.date_verbatim_fr) || update.date_verbatim || update.date_verbatim_fr;
}

/**
 * The entries that belong to `lang` for one project.
 *
 * Usually every entry carries both languages. Where the two pages list
 * different entries the pipeline carries each list whole and unpaired, and the
 * reader sees their own language's list — the rule `ProjectViewer` applies to
 * benefits. A project with nothing in one language falls back to the other
 * rather than vanishing from the timeline.
 */
function entriesFor(project: Project, lang: Lang): Entry[] {
  const all = project.updates.map((update, index) => ({ project, update, index }));
  const own = all.filter((e) => (lang === "fr" ? e.update.body.fr : e.update.body.en));
  return own.length > 0 ? own : all;
}

export function TimelinePanel({
  bundle,
  width,
  onSelect,
}: {
  bundle: Bundle;
  width: number;
  onSelect: (p: Project) => void;
}) {
  const { lang, s } = useI18n();
  const [projectSlug, setProjectSlug] = useState("");
  const [sector, setSector] = useState("");

  const projects = useMemo(
    () => [...bundle.projects].sort((a, b) => t(a.name, lang).localeCompare(t(b.name, lang), LOCALE[lang])),
    [bundle.projects, lang],
  );
  const sectors = useMemo(
    () => [...new Set(bundle.projects.map((p) => p.sector))].sort((a, b) => a.localeCompare(b, LOCALE[lang])),
    [bundle.projects, lang],
  );

  const entries = useMemo(
    () =>
      projects
        .filter((p) => (!projectSlug || p.slug === projectSlug) && (!sector || p.sector === sector))
        .flatMap((p) => entriesFor(p, lang)),
    [projects, projectSlug, sector, lang],
  );

  // Newest first. Two entries with the same date keep their page order.
  const dated = useMemo(
    () =>
      entries
        .filter((e) => e.update.date)
        .sort((a, b) => b.update.date.localeCompare(a.update.date) || a.index - b.index),
    [entries],
  );
  const undated = entries.filter((e) => !e.update.date);

  const marks: TimelineMark[] = dated.map((e) => ({
    project: t(e.project.name, lang),
    date: toDate(e.update.date),
    precision: precisionOf(e.update.date),
    when: written(e.update, lang),
  }));

  const precisionNote = (iso: string) => {
    const p = precisionOf(iso);
    return p === "month" ? s.timelineMonthOnly : p === "year" ? s.timelineYearOnly : "";
  };

  return (
    <section style={{ marginTop: "var(--sp-5)" }}>
      <h2 style={heading}>{s.timelineHeading(dated.length)}</h2>
      <p className="muted" style={{ fontSize: "var(--fs-micro)", margin: "0 0 var(--sp-3)" }}>
        {s.timelineIntro}
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)", marginBottom: "var(--sp-2)" }}>
        <select aria-label={s.timelineProject} value={projectSlug} onChange={(e) => setProjectSlug(e.target.value)} style={select}>
          <option value="">{s.timelineAll}</option>
          {projects.map((p) => (
            <option key={p.slug} value={p.slug}>{t(p.name, lang)}</option>
          ))}
        </select>
        {/* MPO sector names are carried in English only (BACKLOG B1a). */}
        <select aria-label={s.timelineSector} value={sector} onChange={(e) => setSector(e.target.value)} style={select}>
          <option value="">{s.timelineAllSectors}</option>
          {sectors.map((x) => (
            <option key={x} value={x}>{x}</option>
          ))}
        </select>
      </div>

      {dated.length === 0 ? (
        <p className="muted" style={{ fontSize: "var(--fs-small)" }}>{s.timelineEmpty}</p>
      ) : (
        <PlotFigure
          label={s.timelineFigure}
          deps={[marks.map((m) => `${m.project}|${m.date.getTime()}|${m.when}`).join(","), width, bundle.palette, lang]}
          spec={() => timeline(marks, bundle.palette, width, lang)}
        />
      )}

      <details style={{ marginTop: "var(--sp-2)" }}>
        <summary style={summary}>{s.timelineList(dated.length)}</summary>
        <ol style={{ listStyle: "none", margin: "var(--sp-2) 0 0", padding: 0 }}>
          {dated.map((e) => (
            <li key={`${e.project.slug}:${e.index}`} style={item}>
              <div className="muted" style={{ fontSize: "var(--fs-small)" }}>
                {written(e.update, lang)}
                {precisionNote(e.update.date) && ` · ${precisionNote(e.update.date)}`}
              </div>
              <EntryHeader entry={e} lang={lang} onSelect={onSelect} label={s.timelineOpenProject(t(e.project.name, lang))} />
              <div>{t(e.update.body, lang)}</div>
            </li>
          ))}
        </ol>
      </details>

      {undated.length > 0 && (
        <details style={{ marginTop: "var(--sp-2)" }}>
          <summary style={summary}>{s.timelineUndated(undated.length)}</summary>
          <ol style={{ listStyle: "none", margin: "var(--sp-2) 0 0", padding: 0 }}>
            {undated.map((e) => (
              <li key={`${e.project.slug}:${e.index}`} style={item}>
                <EntryHeader entry={e} lang={lang} onSelect={onSelect} label={s.timelineOpenProject(t(e.project.name, lang))} />
                <div>{t(e.update.body, lang)}</div>
              </li>
            ))}
          </ol>
        </details>
      )}

      <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-3)" }}>
        {s.timelineSource}
      </p>
    </section>
  );
}

function EntryHeader({
  entry,
  lang,
  onSelect,
  label,
}: {
  entry: Entry;
  lang: Lang;
  onSelect: (p: Project) => void;
  label: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", margin: "2px 0" }}>
      <button type="button" onClick={() => onSelect(entry.project)} aria-label={label} style={projectButton}>
        {t(entry.project.name, lang)}
      </button>
      <span className="tag">{entry.project.sector}</span>
    </div>
  );
}

const heading: React.CSSProperties = {
  fontSize: "var(--fs-small)",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--ink-muted)",
  margin: "0 0 var(--sp-1)",
};

const summary: React.CSSProperties = {
  cursor: "pointer",
  fontSize: "var(--fs-micro)",
  color: "var(--ink-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const select: React.CSSProperties = {
  font: "inherit",
  fontSize: "var(--fs-small)",
  background: "var(--surface-chart)",
  color: "var(--ink-primary)",
  border: "var(--hairline)",
  borderRadius: "var(--radius)",
  padding: "3px 6px",
  minHeight: 24,
  maxWidth: "100%",
};

const item: React.CSSProperties = {
  borderLeft: "2px solid var(--ink-axis)",
  paddingLeft: "var(--sp-3)",
  marginBottom: "var(--sp-3)",
};

const projectButton: React.CSSProperties = {
  background: "transparent",
  border: "none",
  padding: 0,
  color: "var(--ink-primary)",
  font: "inherit",
  fontWeight: 600,
  textAlign: "left",
  cursor: "pointer",
  textDecoration: "underline",
  textDecorationColor: "var(--ink-axis)",
  textUnderlineOffset: 3,
};
