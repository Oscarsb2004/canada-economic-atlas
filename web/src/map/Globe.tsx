/**
 * Globe.tsx — Canada in the world, and the project pins on it.
 *
 * One library does both halves of the view. MapLibre GL JS v5 ships a native
 * globe projection that transitions to Mercator automatically around zoom 12,
 * so the "Canada in the world" entry view and the drill-down to a project site
 * are the same map — no globe.gl, no three.js, no second stack to keep in sync.
 *
 * NO BASEMAP TILES, NO API KEY, NO COST.
 *
 * Every polygon is committed vector data built by `scripts/build_geo.mjs`:
 * Natural Earth 1:110m for the world, StatCan 2021 cartographic boundaries for
 * the provinces. A tile provider would mean an account, a key in the client,
 * and a rate limit on a page that is otherwise entirely static.
 *
 * There are also no `symbol` layers anywhere here, which is deliberate: symbol
 * layers need a `glyphs` URL, and every free glyph endpoint is somebody's
 * hosted service. Labels are HTML instead.
 *
 * WHY THE PINS CARRY NO SECTOR COLOUR
 *
 * Map markers are an all-pairs form — any two can end up adjacent — and the
 * validated palette caps all-pairs categorical encoding at three slots. The MPO
 * publishes six sectors, so colouring pins by sector would break the colour
 * gates. It is also unnecessary: the pin's face is the project's own official
 * rendering, which identifies it far better than a hue could. Sector filtering
 * belongs in the filter row.
 */

import { useEffect, useRef } from "react";
import maplibregl, { type LngLatLike, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { Bundle, Project } from "../data/bundle";
import { corridorSites, pinnableSites } from "../data/bundle";

/** Where the globe opens: Canada, tilted so the Arctic projects are visible. */
const HOME: { center: LngLatLike; zoom: number } = {
  center: [-96, 58],
  // Low enough that the sphere reads as a sphere. Past ~2.5 the curvature
  // stops being legible and the view is just a map of Canada, which is the
  // drill-down, not the entry.
  zoom: 1.55,
};

interface Props {
  bundle: Bundle;
  selected: Project | null;
  onSelect: (p: Project | null) => void;
}

/**
 * A style with no external sources at all.
 *
 * Colours come from the committed palette rather than being written here, so
 * the map cannot drift away from the validated system. Map chrome (ocean, land)
 * uses ink tokens; Canada uses the accent, because it is the subject.
 */
function buildStyle(bundle: Bundle): StyleSpecification {
  const ink = bundle.palette.ink;
  const accent = bundle.palette.categorical[0].hex;

  return {
    version: 8,
    sources: {
      world: { type: "geojson", data: bundle.world as never },
      provinces: { type: "geojson", data: bundle.provinces as never },
      corridors: { type: "geojson", data: corridorGeoJSON(bundle) as never },
    },
    layers: [
      // The background layer paints the SPHERE under globe projection, not the
      // canvas — so this is the ocean. Space is the container's own CSS
      // background, behind the globe. Getting these the wrong way round gives a
      // planet with no sea, which is what a first attempt here did: an "ocean"
      // fill layer bound to the world source just painted the same country
      // polygons as `land`, twice.
      { id: "ocean", type: "background", paint: { "background-color": ink.gridline } },
      {
        id: "land",
        type: "fill",
        source: "world",
        paint: { "fill-color": ink.axis, "fill-opacity": 1 },
      },
      {
        id: "land-outline",
        type: "line",
        source: "world",
        paint: { "line-color": bundle.palette.surface.page, "line-width": 0.5 },
      },
      // Canada, highlighted. Join on ADM0_A3: Natural Earth publishes ISO_A3 as
      // "-99" for five countries, and while Canada is not one of them, using the
      // unreliable field anywhere invites using it where it does break.
      {
        id: "canada",
        type: "fill",
        source: "world",
        filter: ["==", ["get", "ADM0_A3"], "CAN"],
        paint: { "fill-color": accent, "fill-opacity": 0.22 },
      },
      {
        id: "canada-outline",
        type: "line",
        source: "world",
        filter: ["==", ["get", "ADM0_A3"], "CAN"],
        paint: { "line-color": accent, "line-width": 1.1 },
      },
      // Province boundaries fade in as the globe becomes a map — invisible at
      // world zoom where they would only add noise.
      {
        id: "provinces",
        type: "line",
        source: "provinces",
        paint: {
          "line-color": accent,
          "line-width": 0.6,
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2.2, 0, 3.6, 0.55],
        },
      },
      // Corridors: routes whose endpoints are all the source published.
      {
        id: "corridors",
        type: "line",
        source: "corridors",
        layout: { "line-cap": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1.4, 6, 3],
          "line-dasharray": [2, 1.6],
          "line-opacity": 0.85,
        },
      },
    ],
  };
}

/**
 * Corridor sites as LineStrings.
 *
 * Dashed, and labelled "approximate" in the panel, because the source states
 * that routing is not final. Two published endpoints are not a route — drawing
 * a solid line would imply an alignment the government has not committed to.
 */
function corridorGeoJSON(bundle: Bundle): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: corridorSites(bundle.projects).map(({ project, site }) => ({
      type: "Feature",
      properties: { slug: project.slug, name: site.name.en },
      geometry: { type: "LineString", coordinates: site.geometry.coordinates },
    })),
  };
}

export function Globe({ bundle, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Map<string, maplibregl.Marker>>(new Map());

  // Keep the latest callback without re-running the map setup effect, which
  // would tear down and rebuild the globe on every parent render.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current || map.current) return;

    const m = new maplibregl.Map({
      container: container.current,
      style: buildStyle(bundle),
      center: HOME.center,
      zoom: HOME.zoom,
      attributionControl: false,
      // The globe is the subject; letting it rotate under a stray drag makes
      // the pins hard to hit without adding anything.
      pitchWithRotate: false,
      dragRotate: false,
    });
    map.current = m;

    m.on("style.load", () => {
      // MUST be inside style.load. Calling setProjection before the style is
      // ready throws — this is the single most common way to get a blank map.
      m.setProjection({ type: "globe" });
    });

    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution:
          "Natural Earth · Statistics Canada · Major Projects Office of Canada",
      }),
      "bottom-right",
    );

    // Pins. One HTML marker per point site, faced with the project's own
    // 96 px circular rendering.
    for (const { project, site, index } of pinnableSites(bundle.projects)) {
      const hero = project.media.find((x) => x.role === "hero");
      const el = document.createElement("button");
      el.className = "pin";
      el.type = "button";
      el.setAttribute("aria-pressed", "false");
      // textContent, never innerHTML: these names come from a federal dataset,
      // which is untrusted input as far as the DOM is concerned.
      el.title = site.name.en;
      el.setAttribute("aria-label", site.name.en);
      if (hero?.thumb) el.style.backgroundImage = `url(${hero.thumb})`;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelectRef.current(project);
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat(site.geometry.coordinates[0])
        .addTo(m);

      markers.current.set(`${project.slug}:${index}`, marker);
    }

    // Clicking empty ocean clears the selection, which is the obvious gesture
    // and otherwise leaves the panel stuck on whatever was last opened.
    m.on("click", () => onSelectRef.current(null));

    return () => {
      markers.current.forEach((mk) => mk.remove());
      markers.current.clear();
      m.remove();
      map.current = null;
    };
  }, [bundle]);

  // Fly to the selection, and mark the matching pins pressed.
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    markers.current.forEach((mk, key) => {
      const pressed = selected != null && key.startsWith(`${selected.slug}:`);
      mk.getElement().setAttribute("aria-pressed", String(pressed));
    });

    if (!selected) return;
    const first = selected.sites.find((s) => s.geometry.coordinates.length > 0);
    if (!first) return;

    m.flyTo({
      center: first.geometry.coordinates[0],
      // Stops short of zoom 12, where the projection would switch to Mercator.
      // A project site reads fine at 6 and the globe stays a globe.
      zoom: 5.6,
      speed: 0.85,
      curve: 1.5,
    });
  }, [selected]);

  return (
    <div
      ref={container}
      className="pane-map"
      aria-label="Map of Canada in the world"
      // Space: the canvas behind the sphere. The style's background layer is
      // the ocean, so this is the only place the void gets a colour.
      style={{ background: bundle.palette.surface.page }}
    />
  );
}
