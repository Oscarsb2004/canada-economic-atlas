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
import { PRUID_TO_CODE, asset, mapFeatures, provincialTotals } from "../data/bundle";

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
      canada: { type: "geojson", data: bundle.canada as never },
      provinces: { type: "geojson", data: provincesWithGdp(bundle) as never },
      // `corridors` is the MPO PROJECT routes; `trade` is the national trade
      // network. Two different things that both wanted the same word — naming
      // them apart here rather than letting one shadow the other.
      highways: { type: "geojson", data: bundle.highways as never },
      trade: { type: "geojson", data: bundle.corridors as never },
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
      // Land, everywhere EXCEPT Canada — see `canada-land` below for why.
      {
        id: "land",
        type: "fill",
        source: "world",
        filter: ["!=", ["get", "ADM0_A3"], "CAN"],
        paint: { "fill-color": ink.axis, "fill-opacity": 1 },
      },
      {
        id: "land-outline",
        type: "line",
        source: "world",
        filter: ["!=", ["get", "ADM0_A3"], "CAN"],
        paint: { "line-color": bundle.palette.surface.page, "line-width": 0.5 },
      },
      // Canada's landmass, from the SAME geometry as the highlight above it.
      //
      // Painting it from `world` instead — which is what happened until the
      // highlight moved to `canada.json` — puts a 9-polygon grey shape under a
      // 451-polygon blue one. The mismatch is visible and reads as a rendering
      // fault: grey land bleeds past the coastline in the Arctic where Natural
      // Earth merges the channels, and Vancouver Island and Haida Gwaii are
      // outlined in blue over open ocean because the coarse source has no
      // polygon for them at all.
      //
      // Same colour as `land`, so Canada is not singled out by fill — the
      // coastline is what marks it. Same vertices as the outline, so the two
      // can never disagree.
      {
        id: "canada-land",
        type: "fill",
        source: "canada",
        paint: { "fill-color": ink.axis, "fill-opacity": 1 },
      },
      // Canada, highlighted as a LIT COASTLINE rather than a filled shape.
      //
      // This draws from `canada` — the outline dissolved from the StatCan
      // provincial boundaries — and not from `world` filtered to ADM0_A3=CAN,
      // which is what it used to do. Natural Earth at 1:110m gives Canada nine
      // polygons and 146 points: no Vancouver Island, no Haida Gwaii, no
      // Anticosti, and an Arctic archipelago reduced to a few lozenges. It read
      // as a cartoon of the country. The dissolved boundary is 451 polygons and
      // 16,121 points, so every island carries its own highlight.
      //
      // Two passes. The glow is a wide blurred line that gives the country
      // presence at globe zoom, where a 1px hairline on the Arctic islands
      // would disappear; the hairline on top is what actually traces the coast.
      // Both use `line`, not `fill`, so the archipelago reads as the lacework
      // of channels it is instead of one solid mass.
      {
        id: "canada-glow",
        type: "line",
        source: "canada",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["interpolate", ["linear"], ["zoom"], 1.5, 5, 4, 9],
          "line-blur": ["interpolate", ["linear"], ["zoom"], 1.5, 4, 4, 8],
          // Eases off as the choropleth takes over: past that zoom the
          // provinces carry the colour and the glow is only haze on the coast.
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2.4, 0.5, 4.5, 0.18],
        },
      },
      // Provincial choropleth. Magnitude is a SEQUENTIAL job: one hue,
      // light-to-dark, from the validated ramp. A categorical scale here would
      // claim the provinces are unordered identities when the thing being shown
      // is how much each produces.
      //
      // It fades in with the boundaries: at world zoom it would be a coloured
      // smudge, and the globe's job there is "Canada in the world".
      {
        id: "provinces-fill",
        type: "fill",
        source: "provinces",
        paint: {
          "fill-color": [
            "interpolate",
            ["linear"],
            ["coalesce", ["get", "gdp"], 0],
            ...seqStops(bundle),
          ],
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 2.4, 0, 3.8, 0.85],
        },
      },
      // ── The physical economy, under the pins ───────────────────────────────
      //
      // Two layers with deliberately different visual grammar, because they are
      // two different KINDS of claim and must not read as one dataset:
      //
      //   `highways` is Natural Earth's own road classification — real
      //   published geometry, filtered on the source's `type` field, so what
      //   counts as "major" is the publisher's judgement. Solid.
      //
      //   `corridors` lanes are OURS. There is no public-domain shipping-lane
      //   dataset that is reproducible from a pinned URL and small enough to
      //   commit, so rather than pretend, these are schematic arcs from real
      //   ports saying "this gateway trades in that direction". Dashed, and
      //   the panel carries the disclaimer that ships inside the payload.
      //
      // Both are semi-translucent and both fade IN with zoom: at globe zoom a
      // road network is a smear that hides the coastline the map is built to
      // show. Neither is interactive — they are context for the pins, not
      // competition for them.
      {
        id: "sea-lanes",
        type: "line",
        source: "trade",
        filter: ["==", ["get", "kind"], "lane"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ink.secondary,
          "line-width": ["interpolate", ["linear"], ["zoom"], 1.5, 1, 5, 2.4],
          // Long dashes: the same grammar the project corridors already use for
          // "the endpoints are published, the line between them is not".
          "line-dasharray": [3, 2.5],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 1.4, 0.28, 3, 0.5],
        },
      },
      {
        id: "highways",
        type: "line",
        source: "highways",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.5, 5, 1.6, 8, 3],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.18, 4, 0.45],
        },
      },
      {
        id: "ports",
        type: "circle",
        source: "trade",
        filter: ["==", ["get", "kind"], "port"],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 2, 6, 5],
          "circle-color": ink.secondary,
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 1.6, 0.35, 3, 0.75],
          "circle-stroke-width": 0.6,
          "circle-stroke-color": bundle.palette.surface.page,
        },
      },
      // Drawn after `provinces-fill` on purpose: the choropleth reaches 0.85
      // opacity over exactly this footprint, so an outline underneath it would
      // fade out along every coast at precisely the zoom where the coast is
      // most legible.
      {
        id: "canada-outline",
        type: "line",
        source: "canada",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["interpolate", ["linear"], ["zoom"], 1.5, 0.8, 4, 1.4, 7, 2.2],
        },
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
/**
 * Province polygons with their latest GDP attached.
 *
 * MapLibre cannot join across sources, so the value has to ride on the feature.
 * The join key is PRUID, which is what the StatCan boundary file publishes;
 * everything else in the bundle uses the two-letter code.
 */
function provincesWithGdp(bundle: Bundle): GeoJSON.FeatureCollection {
  const totals = provincialTotals(bundle.provincial);
  return {
    ...bundle.provinces,
    features: bundle.provinces.features.map((f) => {
      const code = PRUID_TO_CODE[String(f.properties?.PRUID ?? "")];
      return { ...f, properties: { ...f.properties, code, gdp: totals[code] ?? null } };
    }),
  };
}

/**
 * Interpolation stops for the sequential ramp.
 *
 * Ontario and Quebec dwarf the territories, so a linear domain would leave
 * eleven provinces in the first swatch. The stops are spaced on a square-root
 * progression of the maximum, which keeps the small economies distinguishable
 * without claiming a false ordering.
 */
function seqStops(bundle: Bundle): (number | string)[] {
  const totals = Object.values(provincialTotals(bundle.provincial));
  const max = Math.max(...totals, 1);
  const steps = bundle.palette.sequential.steps;
  return steps.flatMap((hex, i) => [Math.round(max * (i / (steps.length - 1)) ** 2), hex]);
}

function corridorGeoJSON(bundle: Bundle): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: mapFeatures(bundle.projects)
      .filter((f) => f.line)
      .map(({ project, site, line }) => ({
        type: "Feature",
        properties: { slug: project.slug, name: site.name.en },
        geometry: { type: "LineString", coordinates: line as [number, number][] },
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
    // NO `if (map.current) return` guard here. It looks like it prevents a
    // double-init, but under React StrictMode's mount → unmount → mount it
    // instead lets the second setup bail while the first map is torn down,
    // leaving a live canvas whose map object is destroyed. Symptom: the map
    // renders but every getSource / getStyle call returns undefined, so nothing
    // can be inspected or updated afterwards.
    //
    // The effect's own cleanup is the mechanism. One map per mount, removed on
    // unmount, and the ref is only a handle for the sibling effects below.
    if (!container.current) return;

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
        // The trade-lane disclaimer travels INSIDE the payload and is read from
        // it here rather than restated, so the sentence on screen and the
        // sentence in the registry cannot drift apart. The layer is not allowed
        // to render without it: the ports are real and the arcs are ours, and a
        // reader has no way to tell those apart by looking.
        customAttribution:
          "Natural Earth · Statistics Canada · Major Projects Office of Canada · "
          + bundle.corridors.disclaimer.en,
      }),
      "bottom-right",
    );

    // Pins. ONE MARKER PER MAP FEATURE — points and corridors alike.
    //
    // Corridors used to get a dashed line and nothing else, because markers
    // were built from a `kind === "point"` filter. Four projects were therefore
    // unreachable from the map: no headpiece, nothing to click, no way to open
    // them. `mapFeatures` is a total function precisely so this loop cannot
    // skip a geometry again — if a feature exists it has an anchor, and if it
    // has an anchor it gets a marker.
    //
    // A corridor's anchor is the midpoint of its route and is OURS, not the
    // government's: the source published the ends of the Mackenzie Valley
    // Highway, never its middle. The `pin--derived` class is what keeps that
    // visible rather than letting an inferred position wear the same face as a
    // published one.
    mapFeatures(bundle.projects).forEach(({ project, site, anchor, line, anchorIsDerived }, index) => {
      const hero = project.media.find((x) => x.role === "hero");
      const el = document.createElement("button");
      el.className = anchorIsDerived ? "pin pin--derived" : "pin";
      el.type = "button";
      el.setAttribute("aria-pressed", "false");
      // textContent/attributes, never innerHTML: these names come from a
      // federal dataset, which is untrusted input as far as the DOM is
      // concerned.
      const label = line
        ? `${site.name.en} — route, marker at its midpoint`
        : site.name.en;
      el.title = label;
      el.setAttribute("aria-label", label);
      if (hero?.thumb) el.style.backgroundImage = `url(${asset(hero.thumb)})`;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelectRef.current(project);
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat(anchor)
        .addTo(m);

      markers.current.set(`${project.slug}:${index}`, marker);
    });

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
    // Fly to the anchor, not to coordinates[0]: for a corridor that is the
    // midpoint of the route rather than one arbitrary end, so the camera frames
    // the project instead of landing on whichever endpoint the source listed
    // first — which for the West Coast Oil Pipeline is the BC end of an
    // Alberta-to-BC route.
    const first = selected.sites.find((s) => s.geometry.anchor);
    if (!first?.geometry.anchor) return;

    // A long animated camera move across a globe is the most motion-heavy
    // thing in the app and a genuine vestibular risk. Readers who have asked
    // for reduced motion get the same destination without the flight.
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const target = {
      center: first.geometry.anchor,
      // Stops short of zoom 12, where the projection would switch to Mercator.
      // A project site reads fine at 6 and the globe stays a globe.
      zoom: 5.6,
    };
    if (calm) m.jumpTo(target);
    else m.flyTo({ ...target, speed: 0.85, curve: 1.5 });
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
