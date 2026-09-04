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
 * M3 scope. The analytical charts, the filter row and the pinned tabs are M4
 * and M5 — the overview below is a real read of the bundle, not a placeholder,
 * but it is deliberately a small one.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { Globe } from "./map/Globe";
import { ProjectViewer } from "./panels/ProjectViewer";
import { SectorPanel } from "./panels/SectorPanel";
import { TabStrip } from "./tabs/TabStrip";
import { useTabs } from "./tabs/store";
import { applyPalette } from "./theme/applyPalette";
import { loadBundle, t, type Bundle, type Lang, type Project } from "./data/bundle";
import type { RangeId, SectorView } from "./filters/FilterRow";

export default function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Project | null>(null);
  const [lang] = useState<Lang>("en");

  const pins = useTabs((s) => s.pins);
  const activeId = useTabs((s) => s.activeId);
  const activate = useTabs((s) => s.activate);
  const activePin = pins.find((p) => p.id === activeId) ?? null;

  // A project pin drives the same selection the map does, so opening one flies
  // the globe there exactly as clicking the pin would. One code path, not two.
  useEffect(() => {
    if (!bundle) return;
    if (activePin?.kind === "project") {
      const p = bundle.projects.find((x) => x.slug === activePin.params.slug);
      if (p) setSelected(p);
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
        <h1 style={{ fontSize: "var(--fs-lead)" }}>Could not load the bundle</h1>
        <p className="muted">{error}</p>
        <p className="muted" style={{ fontSize: "var(--fs-small)" }}>
          Run the pipeline: <code>python pipeline/04_bundle.py</code>
        </p>
      </div>
    );
  }

  if (!bundle) {
    return <div style={{ padding: "var(--sp-6)" }} className="muted">Loading…</div>;
  }

  return (
    <div className="split">
      <a className="skip-link" href="#analysis">
        Skip the map and go to the analysis
      </a>
      <Globe bundle={bundle} selected={selected} onSelect={setSelected} />
      <div className="pane-side" id="analysis" role="region" aria-label="Analysis">
        <div style={{ padding: "0 var(--sp-4)" }}>
          <TabStrip />
        </div>
        {selected ? (
          <ProjectViewer
            project={selected}
            lang={lang}
            onClose={() => {
              setSelected(null);
              if (activePin?.kind === "project") activate(null);
            }}
          />
        ) : (
          <Overview
            bundle={bundle}
            lang={lang}
            onSelect={setSelected}
            initialView={activePin?.params.view}
            initialRange={activePin?.params.range}
            initialFocus={activePin?.params.code}
            /* Remount on pin change so the panel picks up the pinned state
               rather than keeping whatever the reader last had open. */
            key={activePin?.id ?? "overview"}
          />
        )}
      </div>
    </div>
  );
}

/** The default right half: what the economy looks like, and what is being built. */
function Overview({
  bundle,
  lang,
  onSelect,
  initialView,
  initialRange,
  initialFocus,
}: {
  bundle: Bundle;
  lang: Lang;
  onSelect: (p: Project) => void;
  initialView?: SectorView;
  initialRange?: RangeId;
  initialFocus?: string;
}) {
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
    const by = (code: string) => bundle.national.find((s) => s.code === code && s.geo === "CA");
    const latest = (code: string) => {
      const s = by(code);
      if (!s) return null;
      for (let i = s.values.length - 1; i >= 0; i--) {
        if (s.values[i] != null) return { period: s.periods[i], value: s.values[i]!, series: s };
      }
      return null;
    };
    return { total: latest("T001"), goods: latest("T002"), services: latest("T003") };
  }, [bundle]);

  const rate = bundle.rates.policy_rate;
  const projects = [...bundle.projects].sort((a, b) => a.name.en.localeCompare(b.name.en));

  return (
    <div ref={paneRef} style={{ padding: "var(--sp-4)" }}>
      <h1 style={{ fontSize: "var(--fs-title)", margin: "0 0 var(--sp-1)" }}>
        Canada Economic Atlas
      </h1>
      <p className="muted" style={{ margin: "0 0 var(--sp-5)", fontSize: "var(--fs-small)" }}>
        Real GDP by sector, and the Major Projects Office portfolio.
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
          label="Real GDP, all industries"
          value={headline.total ? fmtMillions(headline.total.value) : "—"}
          sub={headline.total?.period ?? ""}
          accent="var(--series-1)"
        />
        <Stat
          label="Goods-producing"
          value={headline.goods ? fmtMillions(headline.goods.value) : "—"}
          sub={headline.goods?.period ?? ""}
          accent="var(--series-1)"
        />
        <Stat
          label="Services-producing"
          value={headline.services ? fmtMillions(headline.services.value) : "—"}
          sub={headline.services?.period ?? ""}
          accent="var(--series-2)"
        />
        <Stat
          label="Policy rate"
          value={rate ? `${rate.value.toFixed(2)}%` : "—"}
          sub={rate?.period ?? ""}
          accent="var(--series-3)"
        />
      </div>

      {/* The vintage is stated, not hidden. Two runs a month apart legitimately
          disagree about a recent month, and without the stamp that reads as a
          bug rather than a revision. */}
      {headline.total && (
        <p className="muted" style={{ fontSize: "var(--fs-micro)", marginTop: "calc(-1 * var(--sp-4))" }}>
          Chained 2017 dollars, seasonally adjusted at annual rates · StatCan table{" "}
          {headline.total.series.source_table} · released{" "}
          {headline.total.series.release_time || "—"}
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

      <h2
        style={{
          fontSize: "var(--fs-small)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--ink-muted)",
          margin: "var(--sp-5) 0 var(--sp-2)",
        }}
      >
        Major Projects Office · {projects.length} projects
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
                    backgroundImage: hero?.thumb ? `url(${hero.thumb})` : undefined,
                    border: "1px solid var(--ink-axis)",
                  }}
                />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: "block" }}>{t(p.name, lang)}</span>
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
        Bundle schema {bundle.meta.schema_version} · generated{" "}
        {bundle.meta.generated_at.slice(0, 10)}
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

/** Millions of dollars, shown as billions where that reads better. */
function fmtMillions(v: number): string {
  return v >= 1000
    ? `$${(v / 1000).toLocaleString("en-CA", { maximumFractionDigits: 1 })}B`
    : `$${v.toLocaleString("en-CA", { maximumFractionDigits: 0 })}M`;
}
