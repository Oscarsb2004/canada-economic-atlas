/**
 * App.tsx — the split the whole product is built around.
 *
 * Left: Canada in the world, with the project pins.
 * Right: context-sensitive. National figures by default; a project's own words
 *        when a pin is selected.
 *
 * The right half follows the map rather than being a fixed second view, which
 * is the arrangement chosen in planning: one panel, driven by selection.
 *
 * Everything renders inside `I18nProvider`. The reader's language used to be
 * `useState("en")` with no setter, which made every French string in the
 * bundle — descriptions, benefits, sector labels, corridor paragraphs —
 * unreachable. BACKLOG B1.
 */

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { Globe, type MapOverlays, type ProvinceSummary, type ToggleableOverlay } from "./map/Globe";
import { ProjectViewer } from "./panels/ProjectViewer";
import { ProvincePanel } from "./panels/ProvincePanel";
import { CorridorPanel } from "./panels/CorridorPanel";
import { SectorPanel } from "./panels/SectorPanel";
import { TimelinePanel } from "./panels/TimelinePanel";
import { TabStrip } from "./tabs/TabStrip";
import { useTabs } from "./tabs/store";
import { applyPalette } from "./theme/applyPalette";
import { asset, loadBundle, t, type Bundle, type Project } from "./data/bundle";
import type { RangeId, SectorView } from "./filters/FilterRow";
import { I18nProvider, LOCALE, fmtHeadlineMoney, fmtPercent, useI18n } from "./i18n";

export default function App() {
  return (
    <I18nProvider>
      <Atlas />
    </I18nProvider>
  );
}

function Atlas() {
  const { s } = useI18n();
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Project | null>(null);
  const [selectedProvince, setSelectedProvince] = useState<ProvinceSummary | null>(null);
  const [analysisVisible, setAnalysisVisible] = useState(true);
  const [mapShare, setMapShare] = useState(50);
  const [resizing, setResizing] = useState(false);
  const splitRef = useRef<HTMLDivElement>(null);
  const [overlays, setOverlays] = useState<MapOverlays>({
    provinces: true,
    placeNames: true,
    nationalHighways: true,
    majorHighways: true,
    rail: false,
    ferries: true,
    majorProjects: true,
    tradePlaces: true,
    vessels: true,
  });

  const pins = useTabs((st) => st.pins);
  const activeId = useTabs((st) => st.activeId);
  const activate = useTabs((st) => st.activate);
  const activePin = pins.find((p) => p.id === activeId) ?? null;

  // A project pin drives the same selection the map does, so opening one flies
  // the globe there exactly as clicking the pin would. One code path, not two.
  useEffect(() => {
    if (!bundle) return;
    if (activePin?.kind === "project") {
      const p = bundle.projects.find((x) => x.slug === activePin.params.slug);
      if (p) {
        setSelected(p);
        setSelectedProvince(null);
      }
    }
  }, [activePin, bundle]);

  useEffect(() => {
    loadBundle()
      .then((b) => {
        applyPalette(b.palette);
        setBundle(b);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div style={{ padding: "var(--sp-6)" }}>
        <h1 style={{ fontSize: "var(--fs-lead)" }}>{s.bundleError}</h1>
        <p className="muted">{error}</p>
        <p className="muted" style={{ fontSize: "var(--fs-small)" }}>
          {s.bundleErrorHint} <code>python pipeline/99_bundle.py</code>
        </p>
      </div>
    );
  }

  if (!bundle) {
    return <div style={{ padding: "var(--sp-6)" }} className="muted">{s.loading}</div>;
  }

  const toggleOverlay = (overlay: ToggleableOverlay) => {
    setOverlays((current) => ({ ...current, [overlay]: !current[overlay] }));
  };

  const resizeMap = (clientX: number) => {
    const rect = splitRef.current?.getBoundingClientRect();
    if (!rect) return;
    // Both panes need enough room to remain useful. The divider is therefore
    // bounded rather than allowing a drag to create an inaccessible sliver.
    const next = ((clientX - rect.left) / rect.width) * 100;
    setMapShare(Math.round(Math.min(75, Math.max(30, next))));
  };

  const clearMapSelection = () => {
    setSelected(null);
    setSelectedProvince(null);
    if (activePin?.kind === "project") activate(null);
  };

  return (
    <div
      ref={splitRef}
      className={`split${analysisVisible ? "" : " split--analysis-hidden"}`}
      style={{ "--map-share": `${mapShare}%` } as CSSProperties}
    >
      <a className="skip-link" href="#analysis">
        {s.skipToAnalysis}
      </a>
      <Globe
        bundle={bundle}
        selected={selected}
        onSelect={(project) => {
          setSelected(project);
          if (project) setSelectedProvince(null);
        }}
        selectedProvince={selectedProvince}
        onSelectProvince={(province) => {
          setSelected(null);
          setSelectedProvince(province);
          if (activePin?.kind === "project") activate(null);
        }}
        onClearSelection={clearMapSelection}
        overlays={overlays}
        onToggleOverlay={toggleOverlay}
        analysisVisible={analysisVisible}
        onToggleAnalysis={() => setAnalysisVisible((visible) => !visible)}
      />
      {analysisVisible && <div
        className={`split-divider${resizing ? " split-divider--dragging" : ""}`}
        role="separator"
        aria-label={s.resizePanes}
        aria-orientation="vertical"
        aria-valuemin={30}
        aria-valuemax={75}
        aria-valuenow={mapShare}
        tabIndex={0}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setResizing(true);
          resizeMap(event.clientX);
        }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) resizeMap(event.clientX);
        }}
        onPointerUp={(event) => {
          setResizing(false);
          event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            setMapShare((share) => Math.max(30, share - 5));
          }
          if (event.key === "ArrowRight") {
            event.preventDefault();
            setMapShare((share) => Math.min(75, share + 5));
          }
        }}
      />}
      {analysisVisible && <div className="pane-side" id="analysis" role="region" aria-label={s.analysis}>
        <div style={{ padding: "0 var(--sp-4)" }}>
          <TabStrip />
        </div>
        {selected ? (
          <ProjectViewer
            project={selected}
            industries={bundle.industries}
            onClose={() => {
              setSelected(null);
              if (activePin?.kind === "project") activate(null);
            }}
          />
        ) : selectedProvince ? (
          <ProvincePanel province={selectedProvince} onClose={clearMapSelection} />
        ) : (
          <Overview
            bundle={bundle}
            onSelect={setSelected}
            initialView={activePin?.params.view}
            initialRange={activePin?.params.range}
            initialFocus={activePin?.params.code}
            /* Remount on pin change so the panel picks up the pinned state
               rather than keeping whatever the reader last had open. */
            key={activePin?.id ?? "overview"}
          />
        )}
      </div>}
    </div>
  );
}

/** The default right half: what the economy looks like, and what is being built. */
function Overview({
  bundle,
  onSelect,
  initialView,
  initialRange,
  initialFocus,
}: {
  bundle: Bundle;
  onSelect: (p: Project) => void;
  initialView?: SectorView;
  initialRange?: RangeId;
  initialFocus?: string;
}) {
  const { lang, s } = useI18n();
  // Plot renders to a fixed pixel width, so the pane has to be measured rather
  // than left to CSS. ResizeObserver keeps the charts correct through the
  // 1100px breakpoint where the split stacks.
  const paneRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);

  useEffect(() => {
    const el = paneRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      // Minus the padding either side; floored so a narrow phone still gets a
      // usable chart rather than a negative width.
      setWidth(Math.max(280, Math.floor(entry.contentRect.width) - 32));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const headline = useMemo(() => {
    const by = (code: string) => bundle.national.find((x) => x.code === code && x.geo === "CA");
    const latest = (code: string) => {
      const series = by(code);
      if (!series) return null;
      for (let i = series.values.length - 1; i >= 0; i--) {
        if (series.values[i] != null) return { period: series.periods[i], value: series.values[i]!, series };
      }
      return null;
    };
    return { total: latest("T001"), goods: latest("T002"), services: latest("T003") };
  }, [bundle]);

  const rate = bundle.rates.policy_rate;
  // Sorted by the name the reader sees, with that language's collation — "Île"
  // belongs among the I's in French, not after Z.
  const projects = [...bundle.projects].sort((a, b) =>
    t(a.name, lang).localeCompare(t(b.name, lang), LOCALE[lang]),
  );

  return (
    <div ref={paneRef} style={{ padding: "var(--sp-4)" }}>
      <h1 style={{ fontSize: "var(--fs-title)", margin: "0 0 var(--sp-1)" }}>
        {s.appTitle}
      </h1>
      <p className="muted" style={{ margin: "0 0 var(--sp-5)", fontSize: "var(--fs-small)" }}>
        {s.appSubtitle}
      </p>

      {/* A KPI row, not a chart: these are single current values, and a
          one-bar bar chart of a single number is the classic wrong form. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "var(--sp-3)",
          marginBottom: "var(--sp-5)",
        }}
      >
        <Stat
          label={s.kpiGdp}
          value={headline.total ? fmtHeadlineMoney(headline.total.value, lang) : "—"}
          sub={headline.total?.period ?? ""}
          accent="var(--series-1)"
        />
        <Stat
          label={s.kpiGoods}
          value={headline.goods ? fmtHeadlineMoney(headline.goods.value, lang) : "—"}
          sub={headline.goods?.period ?? ""}
          accent="var(--series-1)"
        />
        <Stat
          label={s.kpiServices}
          value={headline.services ? fmtHeadlineMoney(headline.services.value, lang) : "—"}
          sub={headline.services?.period ?? ""}
          accent="var(--series-2)"
        />
        <Stat
          label={s.kpiPolicyRate}
          value={rate ? fmtPercent(rate.value, lang, 2) : "—"}
          sub={rate?.period ?? ""}
          accent="var(--series-3)"
        />
      </div>

      {/* The vintage is stated, not hidden. Two runs a month apart legitimately
          disagree about a recent month, and without the stamp that reads as a
          bug rather than a revision. */}
      {headline.total && (
        <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "calc(-1 * var(--sp-4))" }}>
          {s.vintage(headline.total.series.source_table, headline.total.series.release_time || "—")}
        </p>
      )}

      <div style={{ marginTop: "var(--sp-5)" }}>
        <SectorPanel
          bundle={bundle}
          width={width}
          initialView={initialView}
          initialRange={initialRange}
          initialFocus={initialFocus}
        />
      </div>

      <CorridorPanel bundle={bundle} />

      <TimelinePanel bundle={bundle} width={width} onSelect={onSelect} />

      <h2
        style={{
          fontSize: "var(--fs-small)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--ink-muted)",
          margin: "var(--sp-5) 0 var(--sp-2)",
        }}
      >
        {s.mpoHeading(projects.length)}
      </h2>

      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {projects.map((p) => {
          const hero = p.media.find((m) => m.role === "hero");
          return (
            <li key={p.slug}>
              <button
                type="button"
                onClick={() => onSelect(p)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-3)",
                  width: "100%",
                  padding: "var(--sp-2)",
                  background: "transparent",
                  border: "none",
                  borderBottom: "var(--hairline)",
                  color: "inherit",
                  font: "inherit",
                  textAlign: "left",
                  cursor: "pointer",
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: `var(--surface-chart) center/cover no-repeat`,
                    backgroundImage: hero?.thumb ? `url(${asset(hero.thumb)})` : undefined,
                    border: "1px solid var(--ink-axis)",
                  }}
                />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: "block" }}>{t(p.name, lang)}</span>
                  {/* Sector and location wording are carried in English only
                      (BACKLOG B1a), so they read English in both languages. */}
                  <span className="muted" style={{ fontSize: "var(--fs-small)" }}>
                    {p.sector} · {p.sites[0]?.geometry.location_verbatim ?? ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <footer
        className="muted"
        style={{ fontSize: "var(--fs-micro)", marginTop: "var(--sp-5)", paddingBottom: "var(--sp-5)" }}
      >
        {s.bundleFooter(bundle.meta.schema_version, bundle.meta.generated_at.slice(0, 10))}
      </footer>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent: string;
}) {
  return (
    <div className="card" style={{ padding: "var(--sp-3)" }}>
      <div className="muted" style={{ fontSize: "var(--fs-micro)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </div>
      {/* Proportional figures, not tabular-nums: these are standalone display
          numbers, not a column that has to align. */}
      <div style={{ fontSize: "var(--fs-lead)", marginTop: 2, color: accent }}>{value}</div>
      <div className="muted" style={{ fontSize: "var(--fs-micro)" }}>{sub}</div>
    </div>
  );
}
