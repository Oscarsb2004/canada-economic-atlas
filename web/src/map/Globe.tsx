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

import type { Bundle, CorridorNodeKind, Lang, Project, Text } from "../data/bundle";
import { PRUID_TO_CODE, asset, mapFeatures, t } from "../data/bundle";
import { LanguageToggle, stringsFor, useI18n } from "../i18n";

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
  selectedProvince: ProvinceSummary | null;
  onSelectProvince: (province: ProvinceSummary) => void;
  onClearSelection: () => void;
  overlays: MapOverlays;
  onToggleOverlay: (overlay: ToggleableOverlay) => void;
  analysisVisible: boolean;
  onToggleAnalysis: () => void;
}

/**
 * Map controls are explicit state, rather than a collection of layer ids leaking
 * into App. A disabled future layer has no boolean here: it cannot accidentally
 * imply that live vessel positions are available before a source is chosen.
 */
export type ToggleableOverlay =
  | "provinces"
  | "placeNames"
  | "nationalHighways"
  | "majorHighways"
  | "rail"
  | "ferries"
  | "majorProjects"
  | "tradePlaces";

export type MapOverlays = Record<ToggleableOverlay, boolean>;

export interface ProvinceSummary {
  code: string;
  /** StatCan's own names from the boundary file, PRENAME and PRFNAME. */
  name: Text;
}

const OVERLAY_LAYER_IDS: Record<Exclude<ToggleableOverlay, "majorProjects" | "placeNames">, readonly string[]> = {
  provinces: ["provinces-fill", "provinces"],
  nationalHighways: ["nhs-outline", "nhs"],
  majorHighways: ["major-highways-outline", "major-highways"],
  rail: ["rail-outline", "rail"],
  ferries: ["ferries"],
  tradePlaces: ["node-port", "node-border_crossing"],
};

const EMPTY_GEOJSON: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/**
 * Every toggleable overlay, in display order. Read off the label table, which
 * `satisfies Record<ToggleableOverlay, ...>`, so an overlay added without a
 * label is a build failure rather than a checkbox that never appears.
 */
const LAYER_ORDER = Object.keys(stringsFor("en").layers) as ToggleableOverlay[];

function railWidthAt(main: number, other: number) {
  return [
    "match", ["get", "TRACKCLASS"],
    "Main", main,
    "Siding", other,
    "Spur", other,
    "Yard", other,
    "Connecting", other,
    "Crossover", other,
    "Wye", other,
    "Ferry Route", other,
    other,
  ];
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
  const railColor = bundle.palette.categorical[1].hex;

  return {
    version: 8,
    sources: {
      world: { type: "geojson", data: bundle.world as never },
      canada: { type: "geojson", data: bundle.canada as never },
      // PRUID is stable in StatCan's boundary file. Promoting it to the feature
      // id lets hover state stay on exactly one province across mouse moves.
      provinces: { type: "geojson", data: bundle.provinces as never, promoteId: "PRUID" },
      // `corridors` is the MPO PROJECT routes; `trade` is the national trade
      // network. Two different things that both wanted the same word — naming
      // them apart here rather than letting one shadow the other.
      nhs: { type: "geojson", data: bundle.nhs as never },
      highways: { type: "geojson", data: bundle.highways as never },
      // Rail is 16 MB of official linework. It starts empty and is fetched only
      // when its off-by-default control is enabled, rather than making every
      // initial globe view pay for a layer it may never use.
      rail: { type: "geojson", data: EMPTY_GEOJSON as never },
      trade: { type: "geojson", data: corridorNodeGeoJSON(bundle) as never },
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
      // Provinces are geographic identities, not a proxy for GDP. They retain
      // one neutral treatment until the reader hovers or selects one, at which
      // point the accent makes the target unambiguous without assigning every
      // province a misleading individual colour.
      {
        id: "provinces-fill",
        type: "fill",
        source: "provinces",
        paint: {
          "fill-color": [
            "case",
            ["any", ["boolean", ["feature-state", "hover"], false], ["boolean", ["feature-state", "selected"], false]],
            accent,
            ink.axis,
          ],
          // Keep a subtle neutral surface at the overview zoom so the
          // provincial boundaries remain discoverable before the user hovers.
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 1.5, 0.16, 3.8, 0.84],
        },
      },
      // ── The physical economy, under the pins ───────────────────────────────
      //
      // All of it real, published geometry now. The schematic sea lanes this
      // project drew by hand are gone: once Transport Canada's own corridors
      // arrived — named, described and enumerated by the publisher — an arc
      // toward a made-up waypoint was a second answer to the same question, and
      // the invented one.
      //
      // Everything here fades IN with zoom and none of it is interactive. At
      // globe zoom a road network is a smear that hides the coastline the map
      // exists to show, and these are context for the pins rather than
      // competition for them.
      //
      // Natural Earth's Canadian Major Highway collection supplements the NHS.
      // It is deliberately quieter: it is a generalized reference network,
      // whereas the blue NHS line above it carries Transport Canada's formal
      // designation.
      {
        id: "major-highways-outline",
        type: "line",
        source: "highways",
        filter: ["==", ["get", "type"], "Major Highway"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ink.gridline,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1.3, 6, 3.4],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.72, 4.5, 0.86],
        },
      },
      {
        id: "major-highways",
        type: "line",
        source: "highways",
        filter: ["==", ["get", "type"], "Major Highway"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ink.muted,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.55, 6, 1.7],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.72, 4.5, 0.9],
        },
      },
      // Natural Resources Canada's National Railway Network. Orange denotes
      // this transport mode, not a carrier; the source's eight Track
      // Classification values are expressed by width, so Main lines remain
      // legible without treating every siding or yard as equally prominent.
      {
        id: "rail-outline",
        type: "line",
        source: "rail",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ink.gridline,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            2, railWidthAt(1.15, 0.7),
            6, railWidthAt(3.3, 1.9),
          ],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.7, 5, 0.88],
        },
      } as never,
      {
        id: "rail",
        type: "line",
        source: "rail",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": railColor,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            2, railWidthAt(0.55, 0.28),
            6, railWidthAt(1.8, 0.9),
          ],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.78, 5, 0.94],
        },
      } as never,
      // The National Highway System, coloured by Transport Canada's own class.
      //
      // ONE layer with a `match` built from a typed table, not three hand-rolled
      // layers — a fourth `type_code` would then fall into the default and draw
      // as the wrong class rather than failing. `verify/` gates that the codes
      // stay within {1,2,3}, so an upstream change is caught before it reaches
      // a colour. Weight rather than hue carries the class: the accent is
      // already doing selection here, and the validated palette caps
      // categorical encoding well below what is competing for it on this map.
      // A light casing makes the network survive both the GDP fill and the
      // dark land colour. It is a second line layer, not a made-up road class:
      // the blue line above remains Transport Canada's designation.
      {
        id: "nhs-outline",
        type: "line",
        source: "nhs",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ink.secondary,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            2, ["match", ["get", "type_code"], ...nhsWidthAt(1.5), 1.1],
            6, ["match", ["get", "type_code"], ...nhsWidthAt(5.4), 3.4],
          ],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.72, 4.5, 0.9],
        },
      } as never,
      {
        id: "nhs",
        type: "line",
        source: "nhs",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": accent,
          // A zoom `interpolate` must be the TOP-LEVEL expression of the paint
          // property, with the data-driven `match` in its output slots — not
          // the other way round, and not wrapped in an arithmetic operator.
          // Both of those were tried here and both are rejected with "Only one
          // zoom-based step/interpolate subexpression may be used".
          //
          // The rejection is total: MapLibre throws out the WHOLE STYLE, so the
          // globe renders as a bare sphere with no land, no coastline and no
          // provinces, while the HTML markers keep drawing because they never
          // touch the style. It reads as "the geometry failed to load" rather
          // than "one paint property is malformed" — which is exactly why the
          // style construction is wrapped and the error named at the call site.
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            2, ["match", ["get", "type_code"], ...nhsWidthAt(0.8), 0.5],
            6, ["match", ["get", "type_code"], ...nhsWidthAt(3.5), 2],
          ],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.78, 4.5, 0.92],
        },
      } as never,
      // Ferry routes, from Natural Earth. The NHS is ROADS ONLY, and on this
      // coastline the ferries are highway rather than leisure: the Marine
      // Atlantic crossing to Newfoundland and the BC Ferries links carry the
      // Trans-Canada itself. Without them the designated network is visibly
      // severed at exactly the places it is most interesting. Dashed, because
      // a sailing is not a road.
      {
        id: "ferries",
        type: "line",
        source: "highways",
        filter: ["==", ["get", "type"], "Ferry Route"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": ink.secondary,
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.6, 6, 1.6],
          "line-dasharray": [2, 2],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.25, 4.5, 0.55],
        },
      },
      // Corridor nodes — the ports and border crossings Transport Canada names
      // in each corridor's infrastructure list.
      //
      // ONE LAYER PER KIND, FROM A TYPED TABLE. This replaced a `sea-lanes` and
      // a `ports` layer built as two hand-written `filter`s over one collection
      // — the shape CLAUDE.md §2b bans, written in this repo two days after the
      // rule was added. A third node kind added to a filter pair renders
      // nothing and raises nothing; `NODE_LAYERS` below is keyed on
      // `CorridorNodeKind`, so a new kind is a compile error instead.
      //
      // These coordinates are OURS: Transport Canada names the facilities and
      // publishes no geometry for any of them, which is why every node carries
      // `coordinate_provenance: derived` and why the two kinds are drawn as
      // hollow marks rather than solid ones.
      ...NODE_LAYER_KINDS.map((kind) => ({
        id: `node-${kind}`,
        type: "circle" as const,
        source: "trade",
        filter: ["==", ["get", "kind"], kind] as never,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 2, 6, 5],
          "circle-color": bundle.palette.surface.page,
          "circle-opacity": ["interpolate", ["linear"], ["zoom"], 1.6, 0.35, 3, 0.85],
          "circle-stroke-width": NODE_STROKE[kind],
          "circle-stroke-color": ink.secondary,
        } as never,
      })),
      // Drawn after `provinces-fill` so the selected outline is never swallowed
      // by the province surface beneath it.
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
          "line-color": [
            "case",
            ["any", ["boolean", ["feature-state", "hover"], false], ["boolean", ["feature-state", "selected"], false]],
            accent,
            ink.secondary,
          ],
          "line-width": [
            "case",
            ["any", ["boolean", ["feature-state", "hover"], false], ["boolean", ["feature-state", "selected"], false]],
            1.8,
            0.6,
          ],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 1.5, 0.2, 3.6, 0.7],
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
 * Every corridor-node kind, and how thick its ring is.
 *
 * A `Record` keyed on `CorridorNodeKind`, not a list of hand-written layers: a
 * new kind fails the build here rather than silently rendering nothing. Stroke
 * weight rather than colour separates them, because colour on this map is
 * already carrying selection and the validated palette caps categorical
 * encoding well below the number of things competing for it.
 */
/**
 * Relative line weight per NHS class, as a fraction of the base width.
 *
 * A Record over Transport Canada's `type_code`, expanded into a MapLibre
 * `match`. Core routes read heaviest — 72.8% of the designated network and the
 * spine of every corridor. Northern and Remote routes read lightest but are NOT
 * dropped: that is where most of the Major Projects Office portfolio sits, and
 * a network that stopped at 55°N would be the same omission as listing four
 * corridors instead of five.
 */
const NHS_CLASS_WEIGHT: Record<1 | 2 | 3, number> = { 1: 1, 2: 0.65, 3: 0.5 };

/** The table, flattened into `match` case/value pairs at one zoom's base width. */
function nhsWidthAt(base: number): number[] {
  return Object.entries(NHS_CLASS_WEIGHT).flatMap(([code, w]) => [Number(code), base * w]);
}

const NODE_STROKE: Record<CorridorNodeKind, number> = {
  port: 1.6,
  border_crossing: 0.8,
};
const NODE_LAYER_KINDS = Object.keys(NODE_STROKE) as CorridorNodeKind[];

/** Corridor ports and crossings as points, with the corridor they belong to. */
function corridorNodeGeoJSON(bundle: Bundle): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: bundle.corridors.flatMap((c) =>
      c.nodes.map((n) => ({
        type: "Feature" as const,
        properties: {
          kind: n.kind,
          corridor: c.corridor_id,
          name: n.name.en,
          corridorName: c.name.en,
        },
        geometry: { type: "Point" as const, coordinates: n.geometry.coordinates[0] },
      })),
    ),
  };
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

/** A pin's tooltip and accessible name, in the reader's language. */
function labelPin(el: HTMLElement, name: Text, linear: boolean, lang: Lang) {
  const text = linear ? stringsFor(lang).pinRoute(t(name, lang)) : t(name, lang);
  el.title = text;
  el.setAttribute("aria-label", text);
}

export function Globe({
  bundle,
  selected,
  onSelect,
  selectedProvince,
  onSelectProvince,
  onClearSelection,
  overlays,
  onToggleOverlay,
  analysisVisible,
  onToggleAnalysis,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Map<string, maplibregl.Marker>>(new Map());
  const railLoaded = useRef(false);
  const railLoading = useRef(false);
  const placeMarkers = useRef<Map<string, maplibregl.Marker>>(new Map());
  const overlaysRef = useRef(overlays);
  overlaysRef.current = overlays;
  const refreshPlaceLabelsRef = useRef<() => void>(() => {});
  const { lang, s } = useI18n();
  // Read by the map's own event handlers, which are registered once per bundle:
  // a language change must relabel the map, not rebuild the globe.
  const langRef = useRef(lang);
  langRef.current = lang;
  /** Each pin's site, so its accessible name can follow the language. */
  const pinSites = useRef<Map<string, { name: Text; linear: boolean }>>(new Map());

  // Keep the latest callback without re-running the map setup effect, which
  // would tear down and rebuild the globe on every parent render.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onProvinceSelectRef = useRef(onSelectProvince);
  onProvinceSelectRef.current = onSelectProvince;
  const onClearSelectionRef = useRef(onClearSelection);
  onClearSelectionRef.current = onClearSelection;

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

    // Surfaced deliberately. A malformed paint expression makes the Map
    // constructor throw, which happens BEFORE any `m.on("error")` handler can
    // exist — so the failure reaches React as an unhandled exception and the
    // page renders a globe with no land and no message. Naming it here is the
    // difference between a five-minute fix and an afternoon of screenshots.
    let style: StyleSpecification;
    try {
      style = buildStyle(bundle);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[map] style is invalid:", err);
      throw err;
    }

    const m = new maplibregl.Map({
      container: container.current,
      style,
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

    // MapLibre swallows style errors: a malformed paint expression drops its
    // layer and renders the rest, so the map looks like it worked and one thing
    // is quietly missing. That is how a broken Canada highlight got as far as a
    // screenshot. Surfacing it costs three lines.
    m.on("error", (e) => {
      // eslint-disable-next-line no-console
      console.error("[map]", (e as unknown as { error?: Error }).error ?? e);
    });

    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        // Built from the bundle's own source table rather than written here, so
        // adding a source cannot leave the credit line stale. `sources.yaml`
        // says generating attribution from data is the point of carrying it.
        customAttribution: Array.from(
          new Set(
            Object.values(bundle.meta.sources ?? {})
              .map((v) => (v as { attribution?: string }).attribution)
              .filter((a): a is string => Boolean(a)),
          ),
        ).join(" · "),
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
      const key = `${project.slug}:${index}`;
      pinSites.current.set(key, { name: site.name, linear: line != null });
      labelPin(el, site.name, line != null, langRef.current);
      if (hero?.thumb) el.style.backgroundImage = `url(${asset(hero.thumb)})`;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelectRef.current(project);
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat(anchor)
        .addTo(m);

      markers.current.set(key, marker);
    });

    /**
     * A full country-wide town label layer cannot put one DOM node at every
     * source coordinate: it would make a small screen carry thousands of
     * overlapping elements. Capitals are the one deliberate exception: each
     * province and territory has its capital at the entry view. The remaining
     * places use their published 2021 Census population tier and then a
     * shrinking pixel grid, so larger centres arrive before smaller towns.
     */
    const syncPlaceLabels = () => {
      placeMarkers.current.forEach((marker) => marker.remove());
      placeMarkers.current.clear();

      const zoom = m.getZoom();
      if (!overlaysRef.current.placeNames) return;

      const { clientWidth: width, clientHeight: height } = m.getContainer();
      const cellSize = Math.max(8, 170 - (zoom - 3) * 24);
      const occupied = new Set<string>();
      const places = bundle.places.features
        .map((feature) => {
          if (feature.geometry?.type !== "Point") return null;
          const [lng, lat] = feature.geometry.coordinates;
          const properties = feature.properties as Record<string, unknown> | null;
          const id = String(properties?.id ?? "");
          // The Government of Canada publishes both names; show the reader's,
          // falling back to English where the French is blank.
          const name = String((langRef.current === "fr" && properties?.name_fr) || properties?.name_en || "");
          const capital = properties?.capital === true;
          const minZoom = Number(properties?.min_zoom);
          const population = Number(properties?.population ?? 0);
          if (!id || !name || !Number.isFinite(lng) || !Number.isFinite(lat)
            || (!capital && (!Number.isFinite(minZoom) || zoom < minZoom))) return null;
          const point = m.project([lng, lat]);
          if (point.x < -32 || point.x > width + 32 || point.y < -32 || point.y > height + 32) return null;
          return { id, name, lng, lat, point, capital, population };
        })
        .filter((place): place is NonNullable<typeof place> => place !== null)
        // A capital always outranks a non-capital; otherwise population is the
        // publisher's ranking. The stable id settles ties without label flicker.
        .sort((a, b) => Number(b.capital) - Number(a.capital)
          || b.population - a.population || Number(a.id) - Number(b.id));

      for (const place of places) {
        const cell = `${Math.floor(place.point.x / cellSize)}:${Math.floor(place.point.y / cellSize)}`;
        if (!place.capital && occupied.has(cell)) continue;
        if (!place.capital) occupied.add(cell);

        const element = document.createElement("span");
        element.className = place.capital ? "place-label place-label--capital" : "place-label";
        element.textContent = place.name;
        element.setAttribute("aria-hidden", "true");
        const marker = new maplibregl.Marker({ element, anchor: "top-left", offset: [3, 2] })
          .setLngLat([place.lng, place.lat])
          .addTo(m);
        placeMarkers.current.set(place.id, marker);
      }
    };
    refreshPlaceLabelsRef.current = syncPlaceLabels;
    m.on("moveend", syncPlaceLabels);
    // NavigationControl's zoom buttons can emit a zoom-only camera update.
    // Listen explicitly so labels arrive at the same moment as the new scale.
    m.on("zoomend", syncPlaceLabels);
    // `idle` is the final camera signal after a globe animation. In particular
    // it covers a control-button zoom that coalesces its move and zoom events.
    m.on("idle", syncPlaceLabels);
    syncPlaceLabels();

    // Province identity belongs to the StatCan boundary feature rather than a
    // hand-maintained coordinate table. The promoted PRUID gives every island
    // in a province one shared hover state.
    let hoveredProvinceId: string | number | null = null;
    m.on("mousemove", "provinces-fill", (event) => {
      const feature = event.features?.[0];
      const id = feature?.id;
      if (id == null || id === hoveredProvinceId) return;
      if (hoveredProvinceId != null) {
        m.setFeatureState({ source: "provinces", id: hoveredProvinceId }, { hover: false });
      }
      hoveredProvinceId = id;
      m.setFeatureState({ source: "provinces", id }, { hover: true });
      m.getCanvas().style.cursor = "pointer";
    });
    m.on("mouseleave", "provinces-fill", () => {
      if (hoveredProvinceId != null) {
        m.setFeatureState({ source: "provinces", id: hoveredProvinceId }, { hover: false });
      }
      hoveredProvinceId = null;
      m.getCanvas().style.cursor = "";
    });
    m.on("click", "provinces-fill", (event) => {
      const feature = event.features?.[0];
      const pruid = String(feature?.properties?.PRUID ?? "");
      const code = PRUID_TO_CODE[pruid];
      const name = {
        en: String(feature?.properties?.PRENAME ?? ""),
        fr: String(feature?.properties?.PRFNAME ?? ""),
      };
      if (code && name.en) onProvinceSelectRef.current({ code, name });
    });

    // Clicking empty ocean clears either type of selection, which is the
    // obvious gesture and otherwise leaves a detail panel stuck open.
    m.on("click", (event) => {
      // Layer-specific click handlers fire as well as this map-wide handler.
      // Query first so choosing a province cannot immediately clear itself.
      if (m.queryRenderedFeatures(event.point, { layers: ["provinces-fill"] }).length === 0) {
        onClearSelectionRef.current();
      }
    });

    return () => {
      markers.current.forEach((mk) => mk.remove());
      markers.current.clear();
      pinSites.current.clear();
      m.off("moveend", syncPlaceLabels);
      m.off("zoomend", syncPlaceLabels);
      m.off("idle", syncPlaceLabels);
      placeMarkers.current.forEach((marker) => marker.remove());
      placeMarkers.current.clear();
      refreshPlaceLabelsRef.current = () => {};
      m.remove();
      map.current = null;
    };
  }, [bundle]);

  // Selection persists after the cursor leaves. It uses the same feature state
  // as hover, but does not need another colour or a second province layer.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      bundle.provinces.features.forEach((feature) => {
        const code = PRUID_TO_CODE[String(feature.properties?.PRUID ?? "")];
        const id = String(feature.properties?.PRUID ?? "");
        if (id) m.setFeatureState({ source: "provinces", id }, { selected: code === selectedProvince?.code });
      });
    };
    // Gate on the PROVINCES SOURCE, not on `isStyleLoaded()`. The latter is
    // false whenever ANY source is still loading — including the 16 MB rail
    // layer for a second or two after its toggle — and this effect used to
    // return early on it with no retry. Reproduced 2026-09-10: enable rail,
    // click Ontario while the rail data parses, and the panel opens but the
    // province is never highlighted, even once the map goes idle. Feature
    // state only needs its own source to exist, which it does from style load.
    if (m.getSource("provinces")) apply();
    else m.once("style.load", apply);
    return () => {
      m.off("style.load", apply);
    };
  }, [bundle.provinces.features, selectedProvince]);

  // The language changed: relabel what the map built imperatively. Pins and
  // place labels are DOM the map owns, so React re-rendering does not reach them.
  useEffect(() => {
    markers.current.forEach((marker, key) => {
      const site = pinSites.current.get(key);
      if (site) labelPin(marker.getElement(), site.name, site.linear, lang);
    });
    refreshPlaceLabelsRef.current();
  }, [lang]);

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

  // The control bar changes visibility only for geometry already in the map.
  // Rail is the exception: it is fetched on demand because the authoritative,
  // nationwide geometry is large and starts disabled.
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    const syncVisibility = () => {
      (Object.entries(OVERLAY_LAYER_IDS) as [keyof typeof OVERLAY_LAYER_IDS, readonly string[]][])
        .forEach(([overlay, layerIds]) => {
          layerIds.forEach((layerId) => {
            if (m.getLayer(layerId)) {
              m.setLayoutProperty(layerId, "visibility", overlays[overlay] ? "visible" : "none");
            }
          });
        });

      markers.current.forEach((marker) => {
        marker.getElement().style.display = overlays.majorProjects ? "block" : "none";
      });
      if (m.getLayer("corridors")) {
        m.setLayoutProperty("corridors", "visibility", overlays.majorProjects ? "visible" : "none");
      }
      refreshPlaceLabelsRef.current();
    };

    if (m.isStyleLoaded()) syncVisibility();
    else m.once("style.load", syncVisibility);

    return () => {
      m.off("style.load", syncVisibility);
    };
  }, [overlays]);

  useEffect(() => {
    const m = map.current;
    if (!m || !overlays.rail || railLoaded.current || railLoading.current) return;

    railLoading.current = true;
    void fetch(asset("/geo/rail.json"))
      .then(async (response) => {
        if (!response.ok) throw new Error(`/geo/rail.json → HTTP ${response.status}`);
        return response.json() as Promise<GeoJSON.FeatureCollection>;
      })
      .then((data) => {
        const target = map.current;
        if (!target) return;
        // Mark the layer loaded only once the data has actually reached a
        // source. This used to set `railLoaded` unconditionally after an
        // optional `source?.setData(...)`, so if the fetch resolved before the
        // style existed the data was silently discarded AND the flag stopped
        // any retry — the toggle would read "on" over an empty layer for the
        // life of the page. Same shape as the province-highlight race, which
        // was reproduced; this one needs a toggle before style load, so it is
        // latent rather than observed.
        const apply = () => {
          const source = target.getSource("rail") as maplibregl.GeoJSONSource | undefined;
          if (!source) return false;
          source.setData(data);
          railLoaded.current = true;
          return true;
        };
        if (!apply()) target.once("style.load", () => { apply(); });
      })
      .catch((error: unknown) => {
        // Keep the rest of the map usable if the optional layer fails to load.
        // The error remains visible to a maintainer without pretending the
        // official source is available.
        console.error("Unable to load the official NRWN rail layer", error);
      })
      .finally(() => {
        railLoading.current = false;
      });
  }, [overlays.rail]);

  return (
    <div
      className="pane-map"
      // Space: the canvas behind the sphere. The style's background layer is
      // the ocean, so this is the only place the void gets a colour.
      style={{ background: bundle.palette.surface.page }}
    >
      <div ref={container} className="map-canvas" aria-label={s.mapLabel} />
      <aside className="map-layer-bar" aria-label={s.layersTitle}>
        <div className="map-layer-bar__title">{s.layersTitle}</div>
        {LAYER_ORDER.map((overlay) => (
          <LayerToggle
            key={overlay}
            checked={overlays[overlay]}
            label={s.layers[overlay].label}
            detail={s.layers[overlay].detail}
            onChange={() => onToggleOverlay(overlay)}
          />
        ))}
        <div className="map-layer-bar__future">
          <span>{s.futureShips.label}</span>
          <small>{s.futureShips.detail}</small>
        </div>
        <div className="map-layer-bar__future">
          <span>{s.futureHeatmap.label}</span>
          <small>{s.futureHeatmap.detail}</small>
        </div>
        <LanguageToggle className="map-layer-bar__lang" />
        <button type="button" className="map-layer-bar__analysis" onClick={onToggleAnalysis}>
          {analysisVisible ? s.hideAnalysis : s.showAnalysis}
        </button>
      </aside>
    </div>
  );
}

function LayerToggle({
  checked,
  label,
  detail,
  onChange,
}: {
  checked: boolean;
  label: string;
  detail: string;
  onChange: () => void;
}) {
  return (
    <label className="map-layer-toggle">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>
        <span>{label}</span>
        <small>{detail}</small>
      </span>
    </label>
  );
}
