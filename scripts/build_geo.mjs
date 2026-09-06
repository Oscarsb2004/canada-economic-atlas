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
import { mkdirSync, existsSync, statSync, writeFileSync } from "node:fs";
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
    scale: "1:110m",            // world overview; the right detail for a globe
    version: "v5.1.2",          // git tag, not "current"
    licence: "public domain",
    url: "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
       + "v5.1.2/geojson/ne_110m_admin_0_countries.geojson",
    file: "ne_110m_admin_0_countries.geojson",
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
};

/**
 * The mapshaper command lines, verbatim.
 *
 * world: 20% simplification on an already-coarse 1:110m source, and 0.01°
 * precision (~1 km), which is far finer than a globe can show.
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
    + `-simplify 20% keep-shapes `
    + `-o format=geojson precision=0.01 "${dst}"`,

  provinces: (src, dst) =>
    `-i "${src}" -proj wgs84 `
    + `-simplify 0.1% keep-shapes `
    + `-filter-fields PRUID,PRENAME,PRFNAME `
    + `-o format=geojson precision=0.001 "${dst}"`,

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

async function build(key, src) {
  const dst = join(OUT, `${key}.json`);
  await mapshaper.runCommands(BUILDS[key](src, dst));
  console.log(`  ${key}.json  ${statSync(dst).size.toLocaleString()} bytes`);
}

mkdirSync(RAW, { recursive: true });
mkdirSync(OUT, { recursive: true });

console.log(`build_geo — mapshaper ${MAPSHAPER_VERSION} (pinned)`);
const world = await download(SOURCES.world);
const provinces = await download(SOURCES.provinces);

await build("world", world);
await build("provinces", provinces);
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
