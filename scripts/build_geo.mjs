/**
 * build_geo.mjs — produce the committed map geometry, reproducibly.
 *
 *     node scripts/build_geo.mjs [--force]
 *
 * Outputs
 *     web/public/geo/world.json      177 country polygons, for the globe
 *     web/public/geo/provinces.json  13 provinces and territories, for drill-down
 *     web/public/geo/canada.json     the national outline, dissolved from those
 *     web/public/geo/SOURCES.json    the manifest describing the three above
 *
 * These live under web/public/geo/ rather than web/public/data/ because they are
 * geometry, not bundle: 04_bundle.py does not touch them and meta.json does not
 * list them.
 *
 * WHY THIS SCRIPT EXISTS RATHER THAN A COMMITTED BLOB
 *
 * The sibling repo world-strategic-map draws the same world. If the two apps
 * simplify Natural Earth differently their coastlines disagree, and flipping
 * between the apps looks broken. So the exact source version, scale and
 * mapshaper invocation are recorded here and the sibling reproduces the file
 * rather than shipping a second, subtly different world.
 *
 * EVERYTHING IS PINNED, INCLUDING THE TOOL
 *
 * The Natural Earth download is a GIT TAG (v5.1.2), not a "current" CDN path,
 * because naciscdn.org serves whatever is latest and a silent upstream release
 * would change our coastlines with no commit to explain it.
 *
 * mapshaper is a pinned devDependency and is called through its Node API, not
 * through `npx mapshaper`. `npx --yes` fetches whatever version is current,
 * which would have quietly defeated the byte-identical reproduction this file
 * exists to guarantee. Using the API also avoids spawning a child process,
 * which on Windows meant either an unresolvable `npx.cmd` or `shell: true` —
 * and Node deprecated passing args alongside a shell (DEP0190) because they are
 * concatenated rather than escaped.
 *
 * TWO THINGS THAT WILL BITE A READER OF THIS FILE
 *
 * 1. Natural Earth's ISO_A3 is "-99" for five entries — Norway, France,
 *    N. Cyprus, Somaliland and Kosovo. It is a long-standing quirk of the
 *    dataset, not a download error. Join on ADM0_A3, which is always populated.
 *    Both fields are kept so the quirk stays visible rather than looking like
 *    our bug.
 *
 * 2. The StatCan shapefile is 266 MB uncompressed and in NAD83 Statistics
 *    Canada Lambert, so it needs -proj wgs84 before MapLibre can use it.
 *    Simplify BEFORE any island filtering: -filter-islands on the full-detail
 *    geometry takes minutes and buys almost nothing, because Canada's vertex
 *    count is dominated by the Arctic archipelago's shape complexity, not by
 *    the number of islands.
 *
 * WHY canada.json IS DERIVED FROM provinces.json, NOT FROM NATURAL EARTH
 *
 * The globe used to highlight Canada by filtering the world source to
 * ADM0_A3 = CAN. At 1:110m that feature is NINE polygons and 146 points for
 * the whole country: Vancouver Island, Haida Gwaii, Anticosti and most of the
 * Arctic archipelago are simply not there, and Ellesmere and Baffin are
 * lozenges. Outlining it drew a shape that is not Canada's coast.
 *
 * The StatCan boundaries already committed here are the real thing — 479
 * polygons and 18,502 points, Nunavut alone carrying 246 up to 83.1°N — so the
 * outline is dissolved from those rather than downloaded again. Deriving it
 * from the SIMPLIFIED provinces output, not from the source zip, is deliberate:
 * mapshaper preserves topology, so the dissolved boundary reuses the province
 * arcs vertex for vertex and the outline sits exactly on the province fills at
 * every zoom. Rebuilding it from the zip at a different simplification would
 * leave hairline gaps along the coast.
 */

import mapshaperPkg from "mapshaper";
import { createRequire } from "node:module";
import { mkdirSync, existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const mapshaper = mapshaperPkg.default ?? mapshaperPkg;
const require = createRequire(import.meta.url);
const MAPSHAPER_VERSION = require("mapshaper/package.json").version;

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const RAW = join(ROOT, "data", "raw", "geo");
const OUT = join(ROOT, "web", "public", "geo");

const force = process.argv.includes("--force");

/** Pinned provenance. Changing any of this changes the committed output. */
const SOURCES = {
  world: {
    name: "Natural Earth — Admin 0 countries",
    // 1:50m, NOT 1:110m. The globe used to draw the world at 110m, where the
    // United States is a smooth blob, Alaska's panhandle is a wedge, Greenland
    // has no fjords and the Great Lakes are lozenges. That was tolerable while
    // Canada was drawn from the same source and equally coarse; it stopped
    // being tolerable when Canada moved to the 451-polygon StatCan boundary,
    // because the two now disagree along every shared edge. The Canada-Alaska
    // border, the Great Lakes and the Gulf of Maine all showed the accurate
    // outline crossing the coarse one, which reads as a rendering fault.
    scale: "1:50m",
    version: "v5.1.2",          // git tag, not "current"
    licence: "public domain",
    url: "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
       + "v5.1.2/geojson/ne_50m_admin_0_countries.geojson",
    file: "ne_50m_admin_0_countries.geojson",
  },
  nhs: {
    name: "Transport Canada — National Highway System",
    scale: "1:10m-equivalent centreline (from the National Road Network)",
    version: "as officially accepted by the Council of Ministers",
    licence: "ogl-canada-2.0",
    // 38,021 km in 60,999 segments. `type_code` is TRANSPORT CANADA's own
    // classification — 1 Core (72.8%), 2 Feeder (11.7%), 3 Northern and Remote
    // (15.5%) — so which roads count as trade arteries is the Council of
    // Ministers' judgement, not a threshold this project picked.
    //
    // Served from the SAME ESRI host as the MPO project layer, so this reuses a
    // pattern the repo already runs against rather than adding a stack.
    layer: "https://maps-cartes.services.geo.ca/server_serveur/rest/services/TC/"
         + "canada_national_highway_system_en/MapServer/0",
    outFields: "type_code,rtnumber1,rtename1,roadclass",
    // ⚠ MANDATORY. ESRI does not guarantee a stable page order without an
    // explicit sort, so two rebuilds would emit differently-ordered features
    // from unchanged upstream data and break the zero-line-diff guarantee that
    // is this project's acceptance test for every stage (CLAUDE.md §6).
    orderBy: "OBJECTID ASC",
    pageSize: 1000,
    file: "tc_national_highway_system.geojson",
  },
  highways: {
    name: "Natural Earth — Roads (10m)",
    scale: "1:10m",
    version: "v5.1.2",
    licence: "public domain",
    // 56,600 features worldwide, 900 of them Canadian, carrying `type`
    // (Major Highway / Secondary Highway / Ferry Route / Beltway), `scalerank`
    // and `length_km`. The filter below keeps only what the source itself
    // classes as a major highway or a ferry route, so "biggest" is the
    // publisher's judgement rather than ours.
    url: "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
       + "v5.1.2/geojson/ne_10m_roads.geojson",
    file: "ne_10m_roads.geojson",
  },
  provinces: {
    name: "Statistics Canada — Provinces/territories, cartographic boundary file",
    scale: "cartographic (major land mass, no coastal water)",
    version: "2021 Census, reference date 2021-01-01",
    licence: "Statistics Canada Open Licence",
    dataset: "https://open.canada.ca/data/en/dataset/ef70dc3b-1069-4037-9bce-61f47e628a1d",
    url: "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/"
       + "boundary-limites/files-fichiers/lpr_000b21a_e.zip",
    file: "lpr_000b21a_e.zip",
  },
  places: {
    name: "Geolocated placenames in Canada",
    publisher: "Innovation, Science and Economic Development Canada",
    version: "published 2018-08-22",
    licence: "ogl-canada-2.0",
    dataset: "https://open.canada.ca/data/en/dataset/fe945388-1dd9-4a4a-9a1e-5c552579a28c",
    // A national point layer of cities, towns, villages, First Nations
    // communities and small hamlets. Unlike a municipality-boundary layer,
    // it carries the place the reader expects to see named on a map.
    url: "https://ised-isde.canada.ca/app/scr/sittibc/web/api/openData/MAG_EXO.CSV",
    file: "MAG_EXO.CSV",
  },
};

/**
 * The mapshaper command lines, verbatim.
 *
 * world: 1:50m simplified to 35%, at 0.005° precision (~500 m). The source is
 * five times the detail of 1:110m, so it can take a harder simplification and
 * still resolve the things 110m loses entirely — the Alaska panhandle, the
 * Great Lakes shoreline, the Scandinavian and Chilean coasts. `keep-shapes`
 * stops small island states being simplified out of existence.
 *
 * provinces: 0.1% is aggressive because the source is full detail — it takes
 * 266 MB down to 319 KB while keeping every province recognisable and the
 * longitude range exact (-141.02 to -52.64). `keep-shapes` stops small polygons
 * being simplified out of existence. 0.001° precision is ~110 m, well under a
 * province fill's rendered resolution.
 */
const BUILDS = {
  world: (src, dst) =>
    `-i "${src}" -filter-fields ADM0_A3,ISO_A3,NAME `
    + `-simplify 35% keep-shapes `
    + `-o format=geojson precision=0.005 "${dst}"`,

  provinces: (src, dst) =>
    `-i "${src}" -proj wgs84 `
    + `-simplify 0.1% keep-shapes `
    + `-filter-fields PRUID,PRENAME,PRFNAME `
    + `-o format=geojson precision=0.001 "${dst}"`,

  // Canada's trunk network, as Natural Earth classes it.
  //
  // `type` is the source's own classification, so filtering on it keeps the
  // judgement of what counts as "major" with the publisher. Ferry routes are
  // kept deliberately: on this coastline they are highway, not leisure — the
  // Marine Atlantic crossing to Newfoundland and the BC Ferries links carry
  // the Trans-Canada itself, and dropping them leaves the network visibly
  // severed at exactly the places it is most interesting.
  //
  // scalerank <= 7 drops the very local segments the 10m file also carries;
  // at globe zoom those are noise the reader cannot resolve anyway.
  // DISSOLVED BY (class, route), which is the difference between 0.77 MB and
  // 11 MB. The service publishes 60,999 separate centreline segments, and at
  // that count the repeated property block dominates the file — simplification
  // alone barely touches it, because `keep-shapes` correctly refuses to drop
  // short segments. Merging contiguous segments that share a class and a route
  // number gives 232 multilines for the same 38,021 km, and keeps `rtnumber1`,
  // which is what lets the map say "1" or "401" rather than just drawing a line.
  //
  // NO `-simplify`, and that is measured rather than lazy. `keep-shapes` guards
  // polygon RINGS; it does not protect short lines, so every simplify setting
  // tried — 2%, 6%, interval=200m, interval=1000m — collapsed the same 37 route
  // groups to null geometry: present in the properties, absent from the map,
  // silent. `-dissolve` alone produces 232 groups and zero nulls.
  //
  // Coordinate precision does the reduction instead, and its cost was measured
  // rather than assumed: at 0.01° (~1 km) the file is 1.0 MB and the groups that
  // collapse total **10.1 km out of 49,617 — 0.020%** — with the longest being a
  // 0.7 km interchange stub (`I1:382:31`). Those are ramps, not highways.
  // `-filter remove-empty` drops them explicitly rather than shipping features
  // that have properties and no geometry.
  //
  // `rtnumber2-5` and `rtename2-4` are NOT requested — see SOURCES.json notes.
  // That loses route concurrency, which is a real omission and is recorded
  // rather than silent.
  nhs: (src, dst) =>
    // The service publishes the literal STRING "None" as the route number of an
    // unnumbered segment — 2,682 of them. Left alone it survives the dissolve
    // and reaches the map as a route called "None". Normalised to empty here
    // rather than special-cased in the frontend, so the quirk is handled where
    // it enters. Same class of thing as Natural Earth's ISO_A3 = -99.
    `-i "${src}" -each 'rtnumber1 = rtnumber1 === "None" ? "" : rtnumber1' `
    + `-dissolve fields=type_code,rtnumber1 `
    
    + `-o format=geojson precision=0.01 "${dst}"`,

  highways: (src, dst) =>
    `-i "${src}" `
    + `-filter 'sov_a3 === "CAN" && (type === "Major Highway" || type === "Ferry Route") && scalerank <= 7' `
    + `-filter-fields type,name,label,length_km,scalerank `
    + `-simplify 25% keep-shapes `
    + `-o format=geojson precision=0.005 "${dst}"`,

  // -dissolve2 rather than -dissolve: the former unions the polygons and drops
  // the shared arcs, which is what removes the interprovincial borders; the
  // latter only merges attributes and would leave every internal line in place.
  // `-each name="Canada"` exists to keep the output a FeatureCollection —
  // dissolving away every field makes mapshaper emit a bare GeometryCollection,
  // which MapLibre's geojson source does not reliably accept.
  canada: (src, dst) =>
    `-i "${src}" -dissolve2 -each 'name="Canada"' `
    + `-o format=geojson precision=0.001 "${dst}"`,
};

async function download(spec) {
  const dest = join(RAW, spec.file);
  if (existsSync(dest) && !force) {
    console.log(`  cached   ${spec.file} (${statSync(dest).size.toLocaleString()} bytes)`);
    return dest;
  }
  process.stdout.write(`  fetching ${spec.file} ... `);
  const res = await fetch(spec.url);
  if (!res.ok) throw new Error(`${spec.url} returned HTTP ${res.status}`);
  writeFileSync(dest, Buffer.from(await res.arrayBuffer()));
  console.log(`${statSync(dest).size.toLocaleString()} bytes`);
  return dest;
}

/**
 * Fetch a paged ESRI feature layer into one GeoJSON file.
 *
 * `download()` is a single request to a single file; an ESRI layer caps at
 * `maxRecordCount` (1000 here, against 60,999 features) and must be walked with
 * `resultOffset`. `outSR=4326` asks for degrees — the layer's own extent is in
 * WKID 3978 Lambert, and a seven-digit metre coordinate renders as nothing
 * rather than raising, so `verify/` gates the bounding box afterwards.
 */
async function downloadPaged(spec) {
  const dest = join(RAW, spec.file);
  if (existsSync(dest) && !force) {
    console.log(`  cached   ${spec.file} (${statSync(dest).size.toLocaleString()} bytes)`);
    return dest;
  }
  const features = [];
  for (let offset = 0; ; offset += spec.pageSize) {
    const url = `${spec.layer}/query?where=1%3D1`
      + `&outFields=${encodeURIComponent(spec.outFields)}`
      + `&orderByFields=${encodeURIComponent(spec.orderBy)}`
      + `&resultOffset=${offset}&resultRecordCount=${spec.pageSize}`
      + `&returnGeometry=true&outSR=4326&f=geoJSON`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${spec.file}: page at ${offset} returned HTTP ${res.status}`);
    const page = await res.json();
    const got = page.features ?? [];
    features.push(...got);
    process.stdout.write(`
  fetching ${spec.file} ... ${features.length} features`);
    if (got.length < spec.pageSize) break;
  }
  writeFileSync(dest, JSON.stringify({ type: "FeatureCollection", features }), "utf8");
  console.log(`
  fetched  ${spec.file} — ${features.length} features, `
    + `${statSync(dest).size.toLocaleString()} bytes`);
  return dest;
}

/**
 * Drop features whose geometry collapsed, and say how many.
 *
 * Coordinate precision is applied when mapshaper WRITES, so a short line can
 * survive every processing step and still land as `{properties, geometry: null}`
 * in the output — which no `-filter` can catch, because during processing the
 * geometry was still there. On the NHS that is 37 of 232 route groups.
 *
 * They are dropped rather than shipped, because a feature with properties and
 * no geometry is one a map silently ignores and a count silently includes. The
 * removal is reported rather than quiet: it was measured at 10.1 km of 49,617
 * (0.020%), all of it sub-kilometre interchange stubs, and if that ratio ever
 * moves it should be visible in the build output rather than discovered later.
 */
function pruneEmpty(key, dst) {
  const doc = JSON.parse(readFileSync(dst, "utf8"));
  if (!Array.isArray(doc.features)) return 0;
  const before = doc.features.length;
  doc.features = doc.features.filter((f) => f.geometry);
  const dropped = before - doc.features.length;
  if (dropped > 0) {
    writeFileSync(dst, JSON.stringify(doc), "utf8");
    console.log(`  ${key}.json  dropped ${dropped} feature(s) whose geometry `
      + `collapsed at output precision`);
  }
  return dropped;
}

/**
 * CSV is the source's published form, not a convenience format we control.
 *
 * Some Canadian place names contain commas and embedded line breaks, so a
 * `split("\\n")` parser would turn a real place into two malformed records.
 * This small RFC-4180 reader keeps the transformation dependency-free and
 * deliberately refuses a changed header rather than publishing an empty map.
 */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') quoted = false;
      else cell += ch;
      continue;
    }
    if (ch === '"') quoted = true;
    else if (ch === ',') {
      row.push(cell);
      cell = "";
    } else if (ch === '\n') {
      row.push(cell.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell || row.length) {
    row.push(cell.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

/** Convert the Government of Canada placename CSV to lean browser GeoJSON. */
function buildPlaces(src) {
  const header = ["PNuid_NLidu", "Name_en", "Nom_fr", "Province", "Latitude", "Longitude"];
  const rows = parseCsv(readFileSync(src, "utf8"));
  if (JSON.stringify(rows.shift()) !== JSON.stringify(header)) {
    throw new Error("MAG_EXO.CSV header changed — inspect the source before rebuilding place labels");
  }

  const ids = new Set();
  const features = rows.map((row, index) => {
    const [id, name_en, name_fr, province, latText, lngText] = row;
    const lat = Number(latText);
    const lng = Number(lngText);
    if (!id || !name_en || !Number.isFinite(lat) || !Number.isFinite(lng)
      || lat < 40 || lat > 85 || lng < -142 || lng > -50 || ids.has(id)) {
      throw new Error(`MAG_EXO.CSV row ${index + 2} is not one unique Canadian populated place`);
    }
    ids.add(id);
    return {
      type: "Feature",
      properties: { id, name_en, name_fr, province },
      geometry: { type: "Point", coordinates: [lng, lat] },
    };
  });
  const dst = join(OUT, "places.json");
  writeFileSync(dst, JSON.stringify({ type: "FeatureCollection", features }), "utf8");
  console.log(`  places.json  ${features.length.toLocaleString()} named places, ${statSync(dst).size.toLocaleString()} bytes`);
}

async function build(key, src) {
  const dst = join(OUT, `${key}.json`);
  await mapshaper.runCommands(BUILDS[key](src, dst));
  pruneEmpty(key, dst);
  console.log(`  ${key}.json  ${statSync(dst).size.toLocaleString()} bytes`);
}

mkdirSync(RAW, { recursive: true });
mkdirSync(OUT, { recursive: true });

console.log(`build_geo — mapshaper ${MAPSHAPER_VERSION} (pinned)`);
const world = await download(SOURCES.world);
const nhs = await downloadPaged(SOURCES.nhs);
const highways = await download(SOURCES.highways);
const provinces = await download(SOURCES.provinces);
const places = await download(SOURCES.places);

await build("world", world);
await build("nhs", nhs);
await build("highways", highways);
await build("provinces", provinces);
buildPlaces(places);
// Derived from the file the previous line just wrote, not from a download.
await build("canada", join(OUT, "provinces.json"));

// A manifest beside the geometry, so a reader can see what produced these files
// without reading this script, and the sibling repo can assert it is
// reproducing the same inputs with the same tool.
writeFileSync(
  join(OUT, "SOURCES.json"),
  JSON.stringify(
    {
      generated_by: "scripts/build_geo.mjs",
      mapshaper: MAPSHAPER_VERSION,
      sources: SOURCES,
      commands: Object.fromEntries(
        Object.entries(BUILDS).map(([k, f]) => [
          k,
          f(
            // canada.json is derived from another output rather than a download.
            SOURCES[k] ? `data/raw/geo/${SOURCES[k].file}` : "web/public/geo/provinces.json",
            `web/public/geo/${k}.json`,
          ),
        ]),
      ),
      notes: {
        iso_a3:
          "Natural Earth ISO_A3 is '-99' for Norway, France, N. Cyprus, "
          + "Somaliland and Kosovo. Join on ADM0_A3.",
        projection:
          "The StatCan source is NAD83 Statistics Canada Lambert; -proj wgs84 "
          + "converts it for MapLibre.",
        province_codes:
          "PRUID is the StatCan numeric key (10 NL, 11 PE, 12 NS, 13 NB, "
          + "24 QC, 35 ON, 46 MB, 47 SK, 48 AB, 59 BC, 60 YT, 61 NT, 62 NU).",
        nhs_unnumbered:
          "Transport Canada publishes the literal string \"None\" as rtnumber1 "
          + "for unnumbered segments (2,682 of 60,999). The build normalises it "
          + "to an empty string; a route named None would otherwise reach the map.",
        nhs_route_concurrency:
          "Only rtnumber1 and rtename1 are kept. Where two designated routes "
          + "share a carriageway the NHS records the others in rtnumber2-5 and "
          + "rtename2-4, and those are not requested. A segment carrying both the "
          + "Trans-Canada and a provincial route therefore shows only the first.",
        nhs_projection:
          "The layer's own extent is WKID 3978 (Lambert). outSR=4326 is what "
          + "makes it degrees; a metre coordinate would render as nothing rather "
          + "than raising, so verify/ gates the bounding box.",
        nhs_pagination:
          "orderByFields=OBJECTID ASC is mandatory. ESRI does not guarantee page "
          + "order without an explicit sort, and an unstable order breaks the "
          + "zero-line-diff guarantee on unchanged upstream data.",
        canada:
          "canada.json is the national outline, dissolved from provinces.json "
          + "so its arcs are identical to the province geometry. It replaces "
          + "filtering world.json to ADM0_A3=CAN, which at 1:110m is 9 polygons "
          + "and omits Vancouver Island, Haida Gwaii and most of the Arctic "
          + "archipelago.",
      },
    },
    null,
    2,
  ) + "\n",
  "utf8",
);
console.log("  SOURCES.json written");
