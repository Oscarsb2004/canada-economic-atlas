/**
 * build_geo.mjs — produce the committed map geometry, reproducibly.
 *
 *     node scripts/build_geo.mjs [--force]
 *
 * Outputs
 *     web/public/geo/world.json      177 country polygons, for the globe
 *     web/public/geo/provinces.json  13 provinces and territories, for drill-down
 *     web/public/geo/canada.json     the national outline, dissolved from those
 *     web/public/geo/rail.json       NRCan's operational National Railway Network
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
import AdmZip from "adm-zip";
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
const RAIL_REGIONS = ["ab", "bc", "mb", "nb", "nl", "ns", "nt", "on", "qc", "sk", "yt"];
const RAIL_SOURCE_ROOT = "https://ftp.maps.canada.ca/pub/nrcan_rncan/vector/geobase_nrwn_rfn";

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
    scale: "1:10m",
    version: "v5.1.2",          // git tag, not "current"
    licence: "public domain",
    url: "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
       + "v5.1.2/geojson/ne_10m_admin_0_countries.geojson",
    file: "ne_10m_admin_0_countries.geojson",
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
  // Lakes and rivers for Canada's detail tier. The StatCan provinces file is
  // land to the riverbank, and StatCan's 2021 boundary page lists no separate
  // hydrography file, so the water is NRCan's. The zip carries an English and a
  // French copy of the same shapefile; only the English one is read.
  water: {
    name: "Atlas of Canada National Scale Data 1:1,000,000 — Waterbodies",
    publisher: "Natural Resources Canada",
    scale: "1:1,000,000",
    version: "record modified 2022-02-22",
    licence: "ogl-canada-2.0",
    dataset: "https://open.canada.ca/data/en/dataset/e9931fc7-034c-52ad-91c5-6c64d4ba0065",
    url: "https://ftp.geogratis.gc.ca/pub/nrcan_rncan/vector/framework_cadre/"
       + "Atlas_of_Canada_1M/hydrology/AC_1M_Waterbodies.shp.zip",
    file: "AC_1M_Waterbodies.shp.zip",
    shapefile: "AC_1M_Waterbodies_shp/AC_1M_Waterbodies",
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
  population_centres: {
    name: "Population and dwelling counts: Canada and population centres",
    publisher: "Statistics Canada",
    version: "2021 Census",
    licence: "statcan-open",
    dataset: "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810001101",
    url: "https://www150.statcan.gc.ca/n1/en/tbl/csv/98100011-eng.zip",
    file: "98100011-eng.zip",
  },
  municipal_population: {
    name: "Population and dwelling counts: census subdivisions (municipalities)",
    publisher: "Statistics Canada",
    version: "2021 Census",
    licence: "statcan-open",
    dataset: "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201",
    // The FALLBACK label rank — see populationByMunicipality for why.
    url: "https://www150.statcan.gc.ca/n1/en/tbl/csv/98100002-eng.zip",
    file: "98100002-eng.zip",
  },
  rail: {
    name: "National Railway Network (NRWN) — GeoBase Series",
    publisher: "Natural Resources Canada",
    version: "pre-packaged English Shapefiles; official catalogue updated 2021-05-19",
    licence: "ogl-canada-2.0",
    dataset: "https://open.canada.ca/data/en/dataset/ac26807e-a1e8-49fa-87bf-451175a859b8",
    // NRCan distributes the national network as one English Shapefile archive
    // per region. Its directory has no PE or NU archive; the build records that
    // absence rather than filling either jurisdiction from another source.
    distribution: RAIL_SOURCE_ROOT,
    files: Object.fromEntries(RAIL_REGIONS.map((region) => {
      const file = `nrwn_rfn_${region}_shp_en.zip`;
      return [region.toUpperCase(), {
        file,
        url: `${RAIL_SOURCE_ROOT}/${region}/${file}`,
      }];
    })),
  },
};

/**
 * The mapshaper command lines, verbatim.
 *
 * world: 1:10m simplified to 10%, at 0.001° precision (~110 m). Until
 * 2026-09-12 this was 1:50m at 35% and 0.005° (~500 m), which put harbours and
 * river mouths abroad under land at the zoom a ship is inspected at. 1:10m at
 * 10% is 1,060,969 bytes (360,115 gzipped) against 602,372 (195,425) before.
 * It stays coarser than Canada on purpose: Canada gets its own detail tier
 * below. `keep-shapes` stops small island states being simplified away.
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
    + `-simplify 10% keep-shapes `
    + `-o format=geojson precision=0.001 "${dst}"`,

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

  // NRWN's official Track Classification carries Main, Siding, Spur, Yard,
  // Connecting, Crossover and Wye. The map keeps each class — deciding that
  // only Main lines "count" would be our judgement — but dissolves identical
  // published attributes so it does not ship tens of thousands of individual
  // centreline fragments. No geometric simplify is used: the NHS experiment
  // proved that `keep-shapes` protects polygon rings, not short line segments.
  // Decimal precision (about 11 m) reduces repeated coordinate bytes without
  // changing the source's topology or its attribute categories.
  rail: (src, dst) =>
    `-i ${src} combine-files -merge-layers `
    + `-filter 'STATUS === "Operational"' `
    + `-filter-fields TRACKCLASS,STATUS,TRANSPTYPE,USETYPE,OWNERENA,OPERATOENA,ADMINAREAC,SUBDI1NAME `
    + `-dissolve fields=TRACKCLASS,STATUS,TRANSPTYPE,USETYPE,OWNERENA,OPERATOENA,ADMINAREAC,SUBDI1NAME `
    + `-o format=geojson precision=0.0001 "${dst}"`,

  // -dissolve2 rather than -dissolve: the former unions the polygons and drops
  // the shared arcs, which is what removes the interprovincial borders; the
  // latter only merges attributes and would leave every internal line in place.
  // `-each name="Canada"` exists to keep the output a FeatureCollection —
  // dissolving away every field makes mapshaper emit a bare GeometryCollection,
  // which MapLibre's geojson source does not reliably accept.
  canada: (src, dst) =>
    `-i "${src}" -dissolve2 -each 'name="Canada"' `
    + `-o format=geojson precision=0.001 "${dst}"`,

  // ── Canada's detail tier, fetched by the app only past DETAIL_ZOOM ──────────
  //
  // Added 2026-09-12 because ships drew on land. Of 1,201 Canadian vessel
  // positions, 636 fell inside the overview's 0.1% coastline; at 1% 405, at 3%
  // 218, at 10% 146 (30.8 MB). Around Vancouver even the unsimplified file left
  // 64 of 395 on land, 40 of them in the Fraser — the boundary is land to the
  // riverbank — so the tier carries NRCan's water too. 3% is where the file is
  // still a download (2.4 MB gzipped) rather than a dataset.
  "provinces-detail": (src, dst) =>
    `-i "${src}" -proj wgs84 `
    + `-simplify 3% keep-shapes `
    + `-filter-fields PRUID,PRENAME,PRFNAME `
    + `-o format=geojson precision=0.0005 "${dst}"`,

  "canada-detail": (src, dst) =>
    `-i "${src}" -dissolve2 -each 'name="Canada"' `
    + `-o format=geojson precision=0.0005 "${dst}"`,

  // Permanent water of 10 km² or more. SHAPE_Area is square metres (the source
  // is NAD83 Canada Atlas Lambert). The 1 km² cut was measured too: 18.5 MB
  // against 3.1 MB, and the same 74 of 395 Vancouver positions left on land.
  water: (src, dst) =>
    `-i "${src}" -filter 'TYPE == "Permanent Water" && SHAPE_Area >= 1e7' `
    + `-proj wgs84 -simplify 5% keep-shapes -filter-fields NAME,NOM `
    + `-o format=geojson precision=0.0005 "${dst}"`,
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
const CAPITALS = {
  NL: "St. John's", PE: "Charlottetown", NS: "Halifax", NB: "Fredericton",
  QC: "Québec", ON: "Toronto", MB: "Winnipeg", SK: "Regina", AB: "Edmonton",
  BC: "Victoria", YT: "Whitehorse", NT: "Yellowknife", NU: "Iqaluit",
};

const PRUID_TO_CODE = {
  10: "NL", 11: "PE", 12: "NS", 13: "NB", 24: "QC", 35: "ON", 46: "MB",
  47: "SK", 48: "AB", 59: "BC", 60: "YT", 61: "NT", 62: "NU",
};

function normalName(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Census population centres are the published, comparable rank for labels. */
function populationByPlace(src) {
  const zip = new AdmZip(src);
  const entry = zip.getEntries().find((item) => item.entryName === "98100011.csv");
  if (!entry) throw new Error("98100011-eng.zip contains no 98100011.csv table");
  const rows = parseCsv(entry.getData().toString("utf8"));
  const header = rows.shift().map((value) => value.replace(/^\uFEFF/, ""));
  const dguid = header.indexOf("DGUID");
  const name = header.indexOf("GEO");
  const population = header.findIndex((value) => value.includes("Population, 2021"));
  if (dguid < 0 || name < 0 || population < 0) {
    throw new Error("98100011.csv layout changed — inspect the census table before rebuilding labels");
  }
  const out = new Map();
  let currentProvince;
  for (const row of rows) {
    // Population-centre DGUIDs carry an area ID, not their province. The table
    // is grouped by province/territory, whose 2021A0002xx heading establishes
    // the province for the following population-centre rows.
    const provinceMatch = /^2021A0002(\d{2})$/.exec(row[dguid] ?? "");
    if (provinceMatch) {
      currentProvince = PRUID_TO_CODE[Number(provinceMatch[1])];
      continue;
    }
    if (!/^2021S051/.test(row[dguid] ?? "")) continue;
    const code = currentProvince;
    const count = Number(row[population]);
    if (!code || !Number.isFinite(count)) continue;
    out.set(`${code}:${normalName(row[name])}`, count);
  }
  if (out.size < 500) throw new Error(`expected hundreds of population centres, found ${out.size}`);
  return out;
}

/**
 * Municipal (census subdivision) population — the FALLBACK rank for labels.
 *
 * Population CENTRES are urban agglomerations, not places. Mississauga and
 * Brampton sit inside the "Toronto" centre, Surrey inside "Vancouver", Laval
 * inside "Montréal", and Ottawa's centre is published as "Ottawa - Gatineau
 * (Ontario part)". None has a centre of its own name, so the centre join alone
 * left 12,071 of 13,018 places unranked and pushed their labels to street zoom
 * — the national capital (1,017,449) among them.
 *
 * A fallback, not a replacement: a municipality is smaller than its
 * agglomeration (Vancouver 662,248 against a centre of 2,426,160), so switching
 * outright would demote every metro core that already ranks correctly. Only
 * places the centre table cannot rank are filled, and no existing rank moves.
 *
 * Duplicate names within a province are WITHHELD rather than guessed — Prince
 * Edward Island alone publishes two "Souris" and two "Morell". A label ranked
 * by the wrong municipality's population is worse than an unranked one.
 */
function populationByMunicipality(src) {
  const zip = new AdmZip(src);
  const entry = zip.getEntries().find((item) => item.entryName === "98100002.csv");
  if (!entry) throw new Error("98100002-eng.zip contains no 98100002.csv table");
  const rows = parseCsv(entry.getData().toString("utf8"));
  const header = rows.shift().map((value) => value.replace(/^\uFEFF/, ""));
  const dguid = header.indexOf("DGUID");
  const name = header.indexOf("GEO");
  const population = header.findIndex((value) => value.includes("Population, 2021"));
  if (dguid < 0 || name < 0 || population < 0) {
    throw new Error("98100002.csv layout changed — inspect the census table before rebuilding labels");
  }
  const found = new Map();
  for (const row of rows) {
    // A census subdivision DGUID is 2021A0005 + its 7-digit CSDUID, whose first
    // two digits ARE the province code. The province comes from the identifier
    // itself, not from the row's position in the table.
    const match = /^2021A0005(\d{2})\d{5}$/.exec(row[dguid] ?? "");
    if (!match || (row[population] ?? "") === "") continue;
    const code = PRUID_TO_CODE[Number(match[1])];
    const count = Number(row[population]);
    if (!code || !Number.isFinite(count)) continue;
    const key = `${code}:${normalName(row[name])}`;
    // `null` marks a name published more than once in the same province.
    found.set(key, found.has(key) ? null : { count, label: row[name] });
  }
  const populations = new Map([...found].filter(([, value]) => value !== null));
  if (populations.size < 4000) {
    throw new Error(`expected thousands of municipalities, found ${populations.size}`);
  }
  return { populations, withheld: found.size - populations.size };
}

function minZoomForPopulation(population) {
  if (population >= 1_000_000) return 2.8;
  if (population >= 100_000) return 3.6;
  if (population >= 25_000) return 4.5;
  if (population >= 5_000) return 5.5;
  if (population >= 1_000) return 6.7;
  // The source's hamlets and other named places arrive only after the census
  // population-centre hierarchy has had room to breathe.
  return 8.2;
}

function buildPlaces(src, populationSrc, municipalSrc) {
  const header = ["PNuid_NLidu", "Name_en", "Nom_fr", "Province", "Latitude", "Longitude"];
  // MAG_EXO.CSV is served as a legacy single-byte CSV. Decoding it as UTF-8
  // turns names such as Québec into replacement characters, which in turn
  // breaks the capital and population-centre joins below.
  const rows = parseCsv(readFileSync(src, "latin1"));
  if (JSON.stringify(rows.shift()) !== JSON.stringify(header)) {
    throw new Error("MAG_EXO.CSV header changed — inspect the source before rebuilding place labels");
  }

  const populations = populationByPlace(populationSrc);
  const municipal = populationByMunicipality(municipalSrc);
  const matchedMunicipalities = new Set();
  const capitalsFound = new Set();
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
    const capital = CAPITALS[province] === name_en;
    if (capital) capitalsFound.add(province);
    const key = `${province}:${normalName(name_en)}`;
    const centre = populations.get(key);
    const municipality = municipal.populations.get(key);
    if (municipality) matchedMunicipalities.add(key);
    // The centre figure wins wherever it exists, so every place that already
    // ranked correctly keeps its rank; the municipality only fills a gap.
    const population = centre ?? municipality?.count ?? null;
    const population_source = centre !== undefined ? "population_centre"
      : municipality ? "census_subdivision" : null;
    return {
      type: "Feature",
      properties: {
        id, name_en, name_fr, province, capital, population, population_source,
        min_zoom: capital ? 1.5 : minZoomForPopulation(population ?? 0),
      },
      geometry: { type: "Point", coordinates: [lng, lat] },
    };
  });
  if (capitalsFound.size !== Object.keys(CAPITALS).length) {
    throw new Error(`place source is missing a provincial or territorial capital: ${Object.keys(CAPITALS).filter((code) => !capitalsFound.has(code)).join(", ")}`);
  }
  // Reported, never thrown. Municipalities of 100,000+ that no place name
  // matches are amalgamations whose placename record uses the historic
  // community — "Greater Sudbury / Grand Sudbury" is "Sudbury" there. Mapping
  // them by hand would be this project authoring a join neither publisher
  // makes. Carried in the file (a GeoJSON foreign member) so verify/ can report
  // it, and any change to the list shows in the diff.
  const unmatched_large_municipalities = [...municipal.populations]
    .filter(([key, value]) => value.count >= 100_000 && !matchedMunicipalities.has(key))
    .map(([, value]) => ({ name: value.label, population: value.count }))
    .sort((a, b) => b.population - a.population || a.name.localeCompare(b.name));
  const ranked = features.filter((f) => f.properties.population_source);
  const dst = join(OUT, "places.json");
  writeFileSync(dst, JSON.stringify({
    type: "FeatureCollection",
    unmatched_large_municipalities,
    features,
  }), "utf8");
  console.log(`  places.json  ranked ${ranked.length.toLocaleString()} places `
    + `(${ranked.filter((f) => f.properties.population_source === "population_centre").length} census centre, `
    + `${ranked.filter((f) => f.properties.population_source === "census_subdivision").length} municipal); `
    + `${municipal.withheld} duplicate municipal names withheld; `
    + `${unmatched_large_municipalities.length} large municipalities unmatched`);
  console.log(`  places.json  ${features.length.toLocaleString()} named places, ${capitalsFound.size} capitals, ${statSync(dst).size.toLocaleString()} bytes`);
}

/**
 * The NRWN archives contain six feature classes. Extract only TRACK into a
 * stable local basename, so mapshaper never accidentally merges crossings or
 * stations into the line layer when combining the eleven regional packages.
 */
function extractRailTrack(src, region) {
  const zip = new AdmZip(src);
  const entries = zip.getEntries().filter((entry) => /_TRACK\.(dbf|prj|shp|shx)$/i.test(entry.entryName));
  if (entries.length !== 4) {
    throw new Error(`${src} has ${entries.length} TRACK shapefile parts; expected .dbf, .prj, .shp and .shx`);
  }
  const directory = join(RAW, "nrwn-track");
  mkdirSync(directory, { recursive: true });
  const base = join(directory, `nrwn_${region.toLowerCase()}_track`);
  for (const entry of entries) {
    const extension = entry.entryName.slice(entry.entryName.lastIndexOf(".")).toLowerCase();
    writeFileSync(`${base}${extension}`, entry.getData());
  }
  return `${base}.shp`;
}

/**
 * The English Waterbodies shapefile, extracted beside its archive.
 *
 * mapshaper can read a zip, but this one holds the English and French copies of
 * the same 128,205 polygons under different names; reading the zip whole would
 * import both and draw every lake twice.
 */
function extractWater(src) {
  const dir = join(RAW, "waterbodies");
  const base = join(dir, SOURCES.water.shapefile);
  if (!existsSync(`${base}.shp`) || force) {
    const zip = new AdmZip(src);
    const parts = zip.getEntries().filter((e) => e.entryName.startsWith(`${SOURCES.water.shapefile}.`));
    const exts = parts.map((e) => e.entryName.slice(SOURCES.water.shapefile.length)).sort();
    for (const needed of [".dbf", ".prj", ".shp", ".shx"]) {
      if (!exts.includes(needed)) throw new Error(`${src} has no ${SOURCES.water.shapefile}${needed}`);
    }
    parts.forEach((e) => zip.extractEntryTo(e, dir, true, true));
  }
  return `${base}.shp`;
}

async function build(key, src) {
  const dst = join(OUT, `${key}.json`);
  await mapshaper.runCommands(BUILDS[key](src, dst));
  pruneEmpty(key, dst);
  console.log(`  ${key}.json  ${statSync(dst).size.toLocaleString()} bytes`);
}

async function buildRail(regionalArchives) {
  const tracks = regionalArchives.map(({ region, path }) => extractRailTrack(path, region));
  const dst = join(OUT, "rail.json");
  await mapshaper.runCommands(BUILDS.rail(tracks.map((path) => `"${path}"`).join(" "), dst));
  pruneEmpty("rail", dst);
  console.log(`  rail.json  ${statSync(dst).size.toLocaleString()} bytes`);
}

mkdirSync(RAW, { recursive: true });
mkdirSync(OUT, { recursive: true });

console.log(`build_geo — mapshaper ${MAPSHAPER_VERSION} (pinned)`);
const placesOnly = process.argv.includes("--places-only");
const railOnly = process.argv.includes("--rail-only");
if (placesOnly && railOnly) throw new Error("choose at most one targeted build: --places-only or --rail-only");
const targeted = placesOnly || railOnly;
const world = targeted ? null : await download(SOURCES.world);
const nhs = targeted ? null : await downloadPaged(SOURCES.nhs);
const highways = targeted ? null : await download(SOURCES.highways);
const provinces = targeted ? null : await download(SOURCES.provinces);
const water = targeted ? null : extractWater(await download(SOURCES.water));
const places = railOnly ? null : await download(SOURCES.places);
const populationCentres = railOnly ? null : await download(SOURCES.population_centres);
const municipalPopulation = railOnly ? null : await download(SOURCES.municipal_population);
const railArchives = placesOnly ? [] : await Promise.all(
  Object.entries(SOURCES.rail.files).map(async ([region, spec]) => ({
    region,
    path: await download(spec),
  })),
);

if (!targeted) {
  await build("world", world);
  await build("nhs", nhs);
  await build("highways", highways);
  await build("provinces", provinces);
}
if (!railOnly) buildPlaces(places, populationCentres, municipalPopulation);
// Derived from the file the previous line just wrote, not from a download.
if (!targeted) await build("canada", join(OUT, "provinces.json"));
if (!targeted) {
  await build("provinces-detail", provinces);
  // Derived like canada.json: dissolved from the detailed provinces, so the
  // detailed outline and the detailed province edges share every vertex.
  await build("canada-detail", join(OUT, "provinces-detail.json"));
  await build("water", water);
}
if (!placesOnly) await buildRail(railArchives);

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
            k === "rail"
              ? Object.keys(SOURCES.rail.files).map((region) => `"data/raw/geo/nrwn-track/nrwn_${region.toLowerCase()}_track.shp"`).join(" ")
              // Derived outlines read another output rather than a download; the
              // detailed provinces read the same archive as provinces.json; water
              // reads the English shapefile extracted from its archive.
              : k === "canada" ? "web/public/geo/provinces.json"
              : k === "canada-detail" ? "web/public/geo/provinces-detail.json"
              : k === "provinces-detail" ? `data/raw/geo/${SOURCES.provinces.file}`
              : k === "water" ? `data/raw/geo/waterbodies/${SOURCES.water.shapefile}.shp`
              : `data/raw/geo/${SOURCES[k].file}`,
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
        places_population:
          "Place labels rank by 2021 Census population-centre population, "
          + "falling back to census-subdivision (municipal) population only "
          + "where no centre matches. Centres are agglomerations, so Ottawa, "
          + "Mississauga, Brampton, Surrey, Laval and Gatineau have none of their "
          + "own name. Duplicate municipal names within a province are withheld, "
          + "and population_source records which figure each place carries.",
        rail:
          "rail.json is NRCan's operational NRWN track segment class from the "
          + "eleven regional English Shapefile archives it publishes (AB, BC, MB, "
          + "NB, NL, NS, NT, ON, QC, SK, YT). The directory publishes no PE or NU "
          + "archive, so neither is supplemented or inferred. Track Classification "
          + "is retained; all official operational classes are rendered. Owner and "
          + "operator are retained as attributes, not visual categories.",
        detail_tier:
          "provinces-detail.json, canada-detail.json and water.json are fetched by "
          + "the app only when the camera reaches DETAIL_ZOOM, and replace the "
          + "overview geometry in place. water.json is NRCan's permanent water of "
          + "10 km² or more, painted over the provinces because the StatCan "
          + "boundary is land to the riverbank.",
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
