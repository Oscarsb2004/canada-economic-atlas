/**
 * bundle.ts — the shapes the Python pipeline publishes, and how to load them.
 *
 * These types mirror `atlas/core/schema.py` exactly. That is the project's
 * governing rule made concrete:
 *
 *     The frontend and the backend are the same object.
 *
 * Identity travels with the value. Nothing here re-derives a label, a total or
 * a rank — if the UI needs it, the pipeline publishes it. When these types and
 * the dataclasses disagree, the dataclasses are right and this file is the bug.
 */

export type Lang = "en" | "fr";

/** One string in both official languages. */
export interface Text {
  en: string;
  fr: string;
}

export function t(text: Text | undefined, lang: Lang): string {
  if (!text) return "";
  return lang === "fr" && text.fr ? text.fr : text.en;
}

export type Provenance =
  | "official_dataset"
  | "page_verbatim"
  | "news_release"
  | "market_data"
  | "derived"
  | "absent";

export interface SourceRef {
  url: string;
  retrieved_at: string;
  provenance: Provenance;
  licence: string;
  content_sha256: string;
}

/**
 * A project's location as the source published it.
 *
 * `coordinates` is [lon, lat] — GeoJSON order, not lat/lon. One pair is a
 * point; two is a corridor whose endpoints are all the source gives, so it is
 * drawn as a line rather than pinned at one end.
 */
export interface Geometry {
  kind: "point" | "corridor" | "region" | "absent";
  coordinates: [number, number][];
  provinces: string[];
  location_verbatim: string;
  approximate: boolean;
}

export interface Site {
  name: Text;
  geometry: Geometry;
}

export interface QuickFact {
  label: Text;
  body: Text;
}

export interface Update {
  date: string;
  date_verbatim: string;
  body: Text;
}

export interface MediaRef {
  source_url: string;
  thumb: string;
  web: string;
  role: string;
  alt: Text;
}

export interface Project {
  slug: string;
  event_slug: string;
  name: Text;
  proponent: Text;
  sector: string;
  status: Text;
  description: Text;
  sites: Site[];
  quick_facts: QuickFact[];
  updates: Update[];
  media: MediaRef[];
  page_url: Text;
  sources: SourceRef[];
}

export interface Strategy {
  slug: string;
  name: Text;
  sector: string;
  location_verbatim: Text;
  description: Text;
  page_url: Text;
  provinces: string[];
  draws_region: boolean;
  provenance: Provenance;
}

export interface Series {
  code: string;
  label: Text;
  geo: string;
  measure: string;
  unit: string;
  scalar: string;
  frequency: string;
  periods: string[];
  values: (number | null)[];
  source_table: string;
  release_time: string;
  provenance: Provenance;
}

export interface Company {
  ticker: string;
  name: string;
  gics_sector: string;
  naics_codes: string[];
  weight_pct: number | null;
  shares: number | null;
  price: number | null;
  currency: string;
  provenance: Provenance;
}

/** The validated colour system. Read, never hand-edited here. */
export interface Palette {
  surface: { chart: string; page: string };
  ink: Record<string, string>;
  categorical: { slot: number; hue: string; step: number; hex: string }[];
  roles: Record<string, number | string>;
  sequential: { hue: string; steps: string[] };
  diverging: { negative: string[]; midpoint: string; positive: string[] };
  status: Record<string, string>;
}

export interface Bundle {
  meta: { schema_version: string; generated_at: string; licences: Record<string, any> };
  palette: Palette;
  projects: Project[];
  strategies: Strategy[];
  national: Series[];
  /**
   * The additive price basis. Chained dollars are NOT additive — measured at
   * +0.311% drift on 2026-06 against +0.000% here — so any chart asserting that
   * parts make a whole reads this instead.
   */
  constant: Series[];
  /** 13 geographies x 23 codes, annual. Feeds the provincial choropleth. */
  provincial: Series[];
  companies: Company[];
  rates: { policy_rate?: { period: string; value: number; label: string } };
  world: GeoJSON.FeatureCollection;
  provinces: GeoJSON.FeatureCollection;
}

/** The bundle's major version this client knows how to read. */
const SUPPORTED_MAJOR = 1;

/**
 * Resolve a path that the pipeline wrote as site-absolute.
 *
 * The bundle and the media paths inside it are written as `/data/...` and
 * `/media/...`, which is correct at the site root and WRONG under a GitHub
 * Pages project site, where everything is served from
 * `/canada-economic-atlas/`. Vite exposes that prefix as `BASE_URL` ("/" in
 * dev), so every fetch and every image src goes through here.
 *
 * Doing it at render time rather than baking the prefix into the JSON keeps the
 * data deployment-agnostic: the same committed bundle serves the dev server,
 * a project site, and a custom domain.
 */
export function asset(path: string): string {
  if (!path) return "";
  const base = import.meta.env.BASE_URL || "/";
  return path.startsWith("/") ? base.replace(/\/$/, "") + path : path;
}

async function json<T>(path: string): Promise<T> {
  const url = asset(path);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

/**
 * Load everything the app needs, in parallel.
 *
 * The whole bundle is ~1.4 MB plus 385 KB of geometry, which is why this is one
 * eager load rather than lazy routes: chunking would add machinery to defer
 * less than a single map tile's worth of bytes.
 *
 * The schema major is asserted rather than assumed. Rendering half a bundle
 * whose shape changed is worse than failing, because it looks like it worked.
 */
export async function loadBundle(): Promise<Bundle> {
  const [meta, palette, projectsDoc, strategiesDoc, nationalDoc, constantDoc, provincialDoc, companiesDoc, rates, world, provinces] =
    await Promise.all([
      json<Bundle["meta"]>("/data/meta.json"),
      json<Palette>("/data/palette.json"),
      json<{ projects: Project[] }>("/data/events/major-projects-office/projects.json"),
      json<{ strategies: Strategy[] }>("/data/events/major-projects-office/strategies.json"),
      json<{ series: Series[] }>("/data/sectors/national-monthly.json"),
      json<{ series: Series[] }>("/data/sectors/national-constant.json"),
      json<{ series: Series[] }>("/data/sectors/provincial-annual.json"),
      json<{ companies: Company[] }>("/data/companies/xic.json"),
      json<Bundle["rates"]>("/data/sectors/rates.json"),
      json<GeoJSON.FeatureCollection>("/geo/world.json"),
      json<GeoJSON.FeatureCollection>("/geo/provinces.json"),
    ]);

  const major = Number(String(meta.schema_version).split(".")[0]);
  if (major !== SUPPORTED_MAJOR) {
    throw new Error(
      `bundle schema_version ${meta.schema_version} — this client reads ${SUPPORTED_MAJOR}.x`,
    );
  }

  return {
    meta,
    palette,
    projects: projectsDoc.projects,
    strategies: strategiesDoc.strategies,
    national: nationalDoc.series,
    constant: constantDoc.series,
    provincial: provincialDoc.series,
    companies: companiesDoc.companies,
    rates,
    world,
    provinces,
  };
}

/** Every mappable site, flattened, with its project attached. */
export function pinnableSites(projects: Project[]) {
  return projects.flatMap((p) =>
    p.sites
      .filter((s) => s.geometry.kind === "point")
      .map((s, i) => ({ project: p, site: s, index: i })),
  );
}

/** Corridor sites, which render as lines rather than pins. */
export function corridorSites(projects: Project[]) {
  return projects.flatMap((p) =>
    p.sites
      .filter((s) => s.geometry.kind === "corridor")
      .map((s) => ({ project: p, site: s })),
  );
}

/**
 * StatCan's numeric province key to our two-letter codes.
 *
 * The boundary file carries PRUID; every other file in the bundle uses the
 * subdivision code, so the join happens here rather than in three places.
 */
export const PRUID_TO_CODE: Record<string, string> = {
  "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC",
  "35": "ON", "46": "MB", "47": "SK", "48": "AB", "59": "BC",
  "60": "YT", "61": "NT", "62": "NU",
};

/** Latest all-industries GDP per province, for the choropleth. */
export function provincialTotals(provincial: Series[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of provincial) {
    if (s.code !== "T001") continue;
    for (let i = s.values.length - 1; i >= 0; i--) {
      if (s.values[i] != null) {
        out[s.geo] = s.values[i]!;
        break;
      }
    }
  }
  return out;
}

/**
 * An external URL that is safe to put in an href.
 *
 * `page_url` is read out of scraped federal HTML. It is very unlikely that
 * canada.ca ever serves a `javascript:` href — but "the upstream page is
 * trustworthy" is not a property this app can enforce, and a scheme allowlist
 * costs three lines. African-Stability-Index hit exactly this and added the
 * same guard after a security review.
 *
 * Returns "" for anything that is not http(s), so the caller renders no link
 * rather than a dangerous one.
 */
export function safeExternalUrl(raw: string): string {
  if (!raw) return "";
  try {
    const u = new URL(raw, window.location.origin);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : "";
  } catch {
    return "";
  }
}
