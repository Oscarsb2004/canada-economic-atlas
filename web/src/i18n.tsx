/**
 * i18n.tsx — the interface in both official languages, and the reader's choice.
 *
 * TWO KINDS OF TEXT, TWO RULES
 *
 * DATA text — project descriptions, sector labels, corridor paragraphs, place
 * and province names — is published by government in English and French and
 * arrives in the bundle as `Text`. It is reproduced, and `t()` picks the
 * language. Nothing in this file translates it.
 *
 * INTERFACE text — headings, control labels, captions, provenance lines — is
 * the app's own, and it lives here. The French below was written for this
 * interface by this project. It is not a government translation and has not
 * been reviewed by a translator (BACKLOG B1b). Where the federal page has its
 * own French heading for the same section ("Faits saillants"), that heading is
 * used rather than a translation of ours.
 *
 * TOTAL BY CONSTRUCTION
 *
 * `fr` is typed as `Strings`, the shape of `en`, and every table keyed on an
 * enum `satisfies` a Record over it. A string added in English and forgotten in
 * French is a build failure, not an English heading in the French interface —
 * the rule CLAUDE.md §2b applies to rendering an open enum, applied to words.
 *
 * NUMBERS COME FROM THE LOCALE, NOT FROM HERE
 *
 * "$183B" and "183 G $" are both produced by `Intl.NumberFormat` from Unicode
 * CLDR locale data. Writing French abbreviations by hand would be this project
 * inventing a convention; asking the platform for fr-CA is not. Measured before
 * switching: for en-CA the Intl output is character-for-character what the
 * hand-written English formatter produced ("$2.4T", "$183B", "$500M").
 *
 * WHAT STAYS ENGLISH IN FRENCH, AND WHY
 *
 * The pipeline carries some fields in English only: an MPO project's sector, a
 * site's location wording, an update's date as written, GICS sector names and
 * company names, and the map's source credits. Translating them here would be
 * the app authoring text a publisher printed; they need the pipeline to capture
 * the French source (BACKLOG B1a).
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { CorridorNodeKind, Lang } from "./data/bundle";
import type { RangeId, SectorView } from "./filters/FilterRow";
import type { ToggleableOverlay } from "./map/Globe";

export const LOCALE: Record<Lang, string> = { en: "en-CA", fr: "fr-CA" };

/** Each language's name, in that language. The toggle never translates it. */
const LANGUAGE_NAME: Record<Lang, string> = { en: "English", fr: "Français" };

// ── The interface's own words ──────────────────────────────────────────────────

const en = {
  appTitle: "Canada Economic Atlas",
  appSubtitle: "Real GDP by sector, and the Major Projects Office portfolio.",
  loading: "Loading…",
  bundleError: "Could not load the bundle",
  bundleErrorHint: "Run the pipeline:",
  skipToAnalysis: "Skip the map and go to the analysis",
  resizePanes: "Resize map and analysis panes",
  analysis: "Analysis",
  languageGroup: "Language",

  kpiGdp: "Real GDP, all industries",
  kpiGoods: "Goods-producing",
  kpiServices: "Services-producing",
  kpiPolicyRate: "Policy rate",
  vintage: (table: string, released: string) =>
    `Chained 2017 dollars, seasonally adjusted at annual rates · StatCan table ${table} · released ${released}`,
  mpoHeading: (n: number) => `Major Projects Office · ${n} projects`,
  bundleFooter: (version: string, date: string) => `Bundle schema ${version} · generated ${date}`,

  filterView: "View",
  filterRange: "Range",
  views: {
    composition: { label: "Composition", hint: "Goods vs services over time" },
    ranking: { label: "Size", hint: "Sectors by latest GDP" },
    growth: { label: "Growth", hint: "Year-over-year change by sector" },
    trends: { label: "Trends", hint: "All sectors as small multiples" },
    heatmap: { label: "Heatmap", hint: "Growth by sector and month" },
  } satisfies Record<SectorView, { label: string; hint: string }>,
  ranges: { "5y": "5 years", "10y": "10 years", all: "All" } satisfies Record<RangeId, string>,
  rangeInapplicable: "This view reads the latest period only",

  compositionFigure: "Goods-producing and services-producing industries over time",
  compositionNote:
    "2017 constant prices — the additive basis. Chained dollars drift +0.311% on this identity, so a stacked chart must not use them.",
  compositionCaption: "Goods and services, latest 12 periods, millions of 2017 dollars",
  colPeriod: "Period",
  colGoods: "Goods",
  colServices: "Services",
  rankingFigure: "Sectors ranked by latest real GDP",
  rankingCaption: (period: string) => `Real GDP by sector, ${period}, millions of chained 2017 dollars`,
  colSector: "Sector",
  colNaics: "NAICS",
  colGdp: "GDP",
  growthFigure: "Year-over-year growth by sector",
  growthNote: "Change against the same month a year earlier. Diverging scale centred on zero.",
  growthCaption: "Year-over-year change by sector, latest month",
  colYoy: "y/y",
  trendsFigure: "All twenty sectors as small multiples",
  trendsNote:
    "Each panel has its own y-scale — these sectors differ by an order of magnitude, and a shared scale would flatten fifteen of them into flat lines.",
  heatmapFigure: "Year-over-year growth by sector and month",
  heatmapScale: "y/y %",
  contracting: "contracting",
  expanding: "expanding",
  focusHeading: "One sector in context",
  focusFigure: (sector: string) => `${sector} against all other sectors`,
  focusSelect: "Sector",
  companiesHeading: "Largest listed companies",
  companiesIndex: "S&P/TSX Capped Composite · market data.",
  companiesFigure: "Largest index constituents by weight",
  companiesCaption: "S&P/TSX Capped Composite constituents by index weight",
  colCompany: "Company",
  colTicker: "Ticker",
  colGics: "GICS sector",
  colWeight: "Weight",
  sectorSource: (table: string, released: string) =>
    `Source: Statistics Canada, table ${table} · released ${released} · reproduced under the Statistics Canada Open Licence.`,

  tableView: (rows: number) => `Table view · ${rows} rows`,

  pinnedViews: "Pinned views",
  pinnedStrip: "Pinned",
  overview: "Overview",
  pin: "Pin",
  pinnedButton: "Pinned",
  alreadyPinned: "Already pinned",
  pinThisView: "Pin this view",
  isPinned: (label: string) => `${label} is pinned`,
  pinNamed: (label: string) => `Pin ${label}`,
  renameNamed: (label: string) => `Rename ${label}`,
  renameHint: (label: string) => `${label} — double-click to rename`,
  moveLeft: (label: string) => `Move ${label} left`,
  moveRight: (label: string) => `Move ${label} right`,
  unpin: (label: string) => `Unpin ${label}`,

  provinceEyebrow: "Province or territory",
  profileInDevelopment: "profile in development",
  backToOverview: "Back to overview",
  provinceIdentity: (name: string) => `${name} identity`,
  emblemTbd: "TBD",
  flagHeading: "Flag / coat of arms",
  flagTbd: "TBD — official artwork and its source will be added here.",
  mottoHeading: "Nickname or motto",
  mottoTbd: "TBD — this will use the province or territory’s own published wording.",
  profileHeading: "Province profile",
  profileTbd:
    "TBD. Population, economic and geographic details will be added as sourced data rather than inferred from the map.",

  corridorsHeading: (n: number) => `Trade corridors · ${n}`,
  corridorsIntroBefore: "Transport Canada's national trade corridors, in its own words. The corridors ",
  corridorsIntroStrong: "do not partition Canada",
  corridorsIntroAfter:
    " — the Northern Corridor is defined by latitude and overlaps the four described by province.",
  nodeKinds: { port: "Ports", border_crossing: "Border crossings" } satisfies Record<CorridorNodeKind, string>,
  onTheMap: "on the map",
  corridorProvenance:
    "Description and infrastructure reproduced verbatim from Transport Canada · Open Government Licence – Canada. Province mapping and node positions are derived by this project: Transport Canada names these facilities and publishes no coordinates for them.",

  closeProject: "Close project",
  locationsApproximate: " — locations are approximate and subject to final routing decisions",
  sectionDescription: "Description",
  sectionQuickFacts: "Quick facts",
  sectionBenefits: "Benefits",
  sectionUpdates: "Latest updates",
  sectionSites: "Sites",
  verbatimFooter: (captured: string) =>
    `Text reproduced verbatim from the Major Projects Office${captured ? ` · captured ${captured}` : ""} · Open Government Licence – Canada`,
  officialPage: "Official project page ↗",

  mapLabel: "Map of Canada in the world",
  layersTitle: "Map layers",
  layers: {
    provinces: { label: "Provinces and territories", detail: "Hover or click for a profile" },
    placeNames: { label: "City and town names", detail: "Government of Canada place names" },
    nationalHighways: { label: "National Highway System", detail: "Transport Canada" },
    majorHighways: { label: "Major highways", detail: "Natural Earth reference network" },
    rail: { label: "Rail network", detail: "Natural Resources Canada · NRWN" },
    ferries: { label: "Ferry routes", detail: "Natural Earth" },
    majorProjects: { label: "Major Projects Office", detail: "Project pins and published route endpoints" },
    tradePlaces: { label: "Trade corridor places", detail: "Ports and border crossings" },
  } satisfies Record<ToggleableOverlay, { label: string; detail: string }>,
  futureShips: { label: "Ship tracking", detail: "Planned — no source connected" },
  futureHeatmap: { label: "Population heatmap", detail: "Planned — 3D visualization" },
  showAnalysis: "Show analysis",
  hideAnalysis: "Hide analysis",
  pinRoute: (name: string) => `${name} — route, marker at its midpoint`,

  timelineHeading: (n: number) => `Portfolio timeline · ${n} dated updates`,
  timelineIntro:
    "Every update the Major Projects Office has published on a project page, in its own words, placed by the date the entry opens with. Entries that name no date are listed apart, in the order their page publishes them, and are never placed on the timeline.",
  timelineFigure: "Project updates over time, one row per project",
  timelineProject: "Project",
  timelineAll: "All projects",
  timelineSector: "Sector",
  timelineAllSectors: "All sectors",
  timelineMonthOnly: "month only",
  timelineYearOnly: "year only",
  timelineList: (n: number) => `Dated updates, newest first · ${n}`,
  timelineUndated: (n: number) => `Updates with no published date · ${n}`,
  timelineOpenProject: (name: string) => `Open ${name}`,
  timelineEmpty: "No dated updates match these filters.",
  timelineSource:
    "Text reproduced verbatim from the Major Projects Office · Open Government Licence – Canada. Dates are read from the opening words of each entry, at the precision the page published.",
};

export type Strings = typeof en;

const fr: Strings = {
  appTitle: "Atlas économique du Canada",
  appSubtitle: "Le PIB réel par secteur et le portefeuille du Bureau des grands projets.",
  loading: "Chargement…",
  bundleError: "Impossible de charger les données",
  bundleErrorHint: "Exécutez le pipeline :",
  skipToAnalysis: "Passer la carte et aller à l’analyse",
  resizePanes: "Redimensionner la carte et l’analyse",
  analysis: "Analyse",
  languageGroup: "Langue",

  kpiGdp: "PIB réel, ensemble des industries",
  kpiGoods: "Production de biens",
  kpiServices: "Production de services",
  kpiPolicyRate: "Taux directeur",
  vintage: (table, released) =>
    `Dollars enchaînés de 2017, désaisonnalisés au taux annuel · tableau ${table} de Statistique Canada · diffusé le ${released}`,
  mpoHeading: (n) => `Bureau des grands projets · ${n} projets`,
  bundleFooter: (version, date) => `Schéma des données ${version} · générées le ${date}`,

  filterView: "Vue",
  filterRange: "Période",
  views: {
    composition: { label: "Composition", hint: "Biens et services au fil du temps" },
    ranking: { label: "Taille", hint: "Secteurs selon le PIB le plus récent" },
    growth: { label: "Croissance", hint: "Variation d’une année à l’autre par secteur" },
    trends: { label: "Tendances", hint: "Tous les secteurs en petits multiples" },
    heatmap: { label: "Carte thermique", hint: "Croissance par secteur et par mois" },
  },
  ranges: { "5y": "5 ans", "10y": "10 ans", all: "Tout" },
  rangeInapplicable: "Cette vue ne lit que la période la plus récente",

  compositionFigure: "Industries productrices de biens et de services au fil du temps",
  compositionNote:
    "Prix constants de 2017 — la base additive. Les dollars enchaînés s’écartent de +0,311 % sur cette identité; un graphique empilé ne doit donc pas les utiliser.",
  compositionCaption: "Biens et services, 12 dernières périodes, millions de dollars de 2017",
  colPeriod: "Période",
  colGoods: "Biens",
  colServices: "Services",
  rankingFigure: "Secteurs classés selon le PIB réel le plus récent",
  rankingCaption: (period) => `PIB réel par secteur, ${period}, millions de dollars enchaînés de 2017`,
  colSector: "Secteur",
  colNaics: "SCIAN",
  colGdp: "PIB",
  growthFigure: "Croissance d’une année à l’autre par secteur",
  growthNote: "Variation par rapport au même mois de l’année précédente. Échelle divergente centrée sur zéro.",
  growthCaption: "Variation d’une année à l’autre par secteur, dernier mois",
  colYoy: "Var. annuelle",
  trendsFigure: "Les vingt secteurs en petits multiples",
  trendsNote:
    "Chaque panneau a sa propre échelle verticale — ces secteurs diffèrent d’un ordre de grandeur, et une échelle commune en réduirait quinze à des lignes plates.",
  heatmapFigure: "Croissance d’une année à l’autre par secteur et par mois",
  heatmapScale: "var. annuelle %",
  contracting: "en contraction",
  expanding: "en expansion",
  focusHeading: "Un secteur en contexte",
  focusFigure: (sector) => `${sector} par rapport à tous les autres secteurs`,
  focusSelect: "Secteur",
  companiesHeading: "Plus grandes sociétés cotées",
  companiesIndex: "Indice composé plafonné S&P/TSX · données de marché.",
  companiesFigure: "Principales composantes de l’indice selon la pondération",
  companiesCaption: "Composantes de l’indice composé plafonné S&P/TSX selon la pondération",
  colCompany: "Société",
  colTicker: "Symbole",
  colGics: "Secteur GICS",
  colWeight: "Pondération",
  sectorSource: (table, released) =>
    `Source : Statistique Canada, tableau ${table} · diffusé le ${released} · reproduit en vertu de la Licence ouverte de Statistique Canada.`,

  tableView: (rows) => `Tableau · ${rows} lignes`,

  pinnedViews: "Vues épinglées",
  pinnedStrip: "Épinglées",
  overview: "Aperçu",
  pin: "Épingler",
  pinnedButton: "Épinglée",
  alreadyPinned: "Déjà épinglée",
  pinThisView: "Épingler cette vue",
  isPinned: (label) => `${label} est épinglée`,
  pinNamed: (label) => `Épingler ${label}`,
  renameNamed: (label) => `Renommer ${label}`,
  renameHint: (label) => `${label} — double-cliquez pour renommer`,
  moveLeft: (label) => `Déplacer ${label} vers la gauche`,
  moveRight: (label) => `Déplacer ${label} vers la droite`,
  unpin: (label) => `Retirer ${label}`,

  provinceEyebrow: "Province ou territoire",
  profileInDevelopment: "profil en préparation",
  backToOverview: "Retour à l’aperçu",
  provinceIdentity: (name) => `Identité : ${name}`,
  emblemTbd: "À venir",
  flagHeading: "Drapeau / armoiries",
  flagTbd: "À venir — les illustrations officielles et leur source seront ajoutées ici.",
  mottoHeading: "Surnom ou devise",
  mottoTbd: "À venir — le libellé publié par la province ou le territoire lui-même sera utilisé.",
  profileHeading: "Profil de la province",
  profileTbd:
    "À venir. Les renseignements démographiques, économiques et géographiques seront ajoutés à partir de données sourcées plutôt que déduits de la carte.",

  corridorsHeading: (n) => `Corridors commerciaux · ${n}`,
  corridorsIntroBefore: "Les corridors commerciaux nationaux de Transports Canada, dans ses propres mots. Les corridors ",
  corridorsIntroStrong: "ne forment pas une partition du Canada",
  corridorsIntroAfter:
    " — le Corridor du Nord est défini par la latitude et chevauche les quatre corridors décrits par province.",
  nodeKinds: { port: "Ports", border_crossing: "Postes frontaliers" },
  onTheMap: "sur la carte",
  corridorProvenance:
    "Description et infrastructures reproduites textuellement de Transports Canada · Licence du gouvernement ouvert – Canada. L’attribution aux provinces et la position des installations sont établies par ce projet : Transports Canada nomme ces installations sans en publier les coordonnées.",

  closeProject: "Fermer le projet",
  locationsApproximate: " — les emplacements sont approximatifs et sous réserve des décisions finales sur le tracé",
  sectionDescription: "Description",
  sectionQuickFacts: "Faits saillants",
  sectionBenefits: "Avantages",
  sectionUpdates: "Dernière mise à jour",
  sectionSites: "Sites",
  verbatimFooter: (captured) =>
    `Texte reproduit textuellement du Bureau des grands projets${captured ? ` · saisi le ${captured}` : ""} · Licence du gouvernement ouvert – Canada`,
  officialPage: "Page officielle du projet ↗",

  mapLabel: "Carte du Canada dans le monde",
  layersTitle: "Couches de la carte",
  layers: {
    provinces: { label: "Provinces et territoires", detail: "Survolez ou cliquez pour un profil" },
    placeNames: { label: "Noms des villes et villages", detail: "Noms géographiques du gouvernement du Canada" },
    nationalHighways: { label: "Réseau routier national", detail: "Transports Canada" },
    majorHighways: { label: "Grandes routes", detail: "Réseau de référence Natural Earth" },
    rail: { label: "Réseau ferroviaire", detail: "Ressources naturelles Canada · RFN" },
    ferries: { label: "Liaisons par traversier", detail: "Natural Earth" },
    majorProjects: { label: "Bureau des grands projets", detail: "Épingles des projets et extrémités de tracé publiées" },
    tradePlaces: { label: "Lieux des corridors commerciaux", detail: "Ports et postes frontaliers" },
  },
  futureShips: { label: "Suivi des navires", detail: "Prévu — aucune source connectée" },
  futureHeatmap: { label: "Carte thermique de la population", detail: "Prévue — visualisation 3D" },
  showAnalysis: "Afficher l’analyse",
  hideAnalysis: "Masquer l’analyse",
  pinRoute: (name) => `${name} — tracé, repère à son point médian`,

  timelineHeading: (n) => `Chronologie du portefeuille · ${n} mises à jour datées`,
  timelineIntro:
    "Chaque mise à jour publiée par le Bureau des grands projets sur une page de projet, dans ses propres mots, placée à la date par laquelle l’entrée commence. Les entrées sans date sont présentées à part, dans l’ordre de leur page, et ne sont jamais placées sur la chronologie.",
  timelineFigure: "Mises à jour des projets au fil du temps, une ligne par projet",
  timelineProject: "Projet",
  timelineAll: "Tous les projets",
  timelineSector: "Secteur",
  timelineAllSectors: "Tous les secteurs",
  timelineMonthOnly: "mois seulement",
  timelineYearOnly: "année seulement",
  timelineList: (n) => `Mises à jour datées, des plus récentes aux plus anciennes · ${n}`,
  timelineUndated: (n) => `Mises à jour sans date publiée · ${n}`,
  timelineOpenProject: (name) => `Ouvrir ${name}`,
  timelineEmpty: "Aucune mise à jour datée ne correspond à ces filtres.",
  timelineSource:
    "Texte reproduit textuellement du Bureau des grands projets · Licence du gouvernement ouvert – Canada. Les dates sont lues dans les premiers mots de chaque entrée, à la précision publiée par la page.",
};

const STRINGS: Record<Lang, Strings> = { en, fr };

/** The strings for a language, for code outside React: chart specs and map DOM. */
export function stringsFor(lang: Lang): Strings {
  return STRINGS[lang];
}

// ── Numbers and dates, from the locale ─────────────────────────────────────────

const formats = new Map<string, Intl.NumberFormat>();

/** Intl formatters are expensive to build and charts format thousands of ticks. */
function numberFormat(lang: Lang, key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const id = `${lang}:${key}`;
  let format = formats.get(id);
  if (!format) {
    format = new Intl.NumberFormat(LOCALE[lang], options);
    formats.set(id, format);
  }
  return format;
}

const COMPACT_CAD: Intl.NumberFormatOptions = {
  style: "currency",
  currency: "CAD",
  currencyDisplay: "narrowSymbol",
  notation: "compact",
};

/** Millions of dollars as compact currency, for axes and tables: 2,369,309 → "$2.4T" / "2,4 T $". */
export function fmtMoneyM(millions: number, lang: Lang): string {
  const dollars = millions * 1_000_000;
  const digits = Math.abs(dollars) >= 1e12 ? 1 : 0;
  return numberFormat(lang, `compact${digits}`, { ...COMPACT_CAD, maximumFractionDigits: digits }).format(dollars);
}

/**
 * Millions of dollars for a headline tile: "$2,369.3B" / "2 369,3 G $".
 *
 * Compact notation would say "$2.4T" and discard three digits a tile has room
 * for. So the number is formatted plainly and set where the locale puts one
 * billion's digits — which keeps the symbol, the unit letter and their order
 * ("$…B" against "… G $") CLDR's rather than ours.
 */
export function fmtHeadlineMoney(millions: number, lang: Lang): string {
  const billions = Math.abs(millions) >= 1_000;
  const number = numberFormat(lang, billions ? "plain1" : "plain0", { maximumFractionDigits: billions ? 1 : 0 })
    .format(Math.abs(millions) / (billions ? 1_000 : 1));
  const shape = numberFormat(lang, "compact0", { ...COMPACT_CAD, maximumFractionDigits: 0 })
    .formatToParts(billions ? 1e9 : 1e6);
  return (millions < 0 ? "-" : "") + shape.map((p) => (p.type === "integer" ? number : p.value)).join("");
}

/** A signed change: "+2.0%" / "+2,0 %". Zero carries no sign. */
export function fmtPct(value: number, lang: Lang, digits = 1): string {
  return numberFormat(lang, `pct-signed-${digits}`, {
    style: "percent",
    signDisplay: "exceptZero",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value / 100);
}

/** A level rather than a change: "7.82%" / "7,82 %". */
export function fmtPercent(value: number, lang: Lang, digits = 1): string {
  return numberFormat(lang, `pct-${digits}`, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value / 100);
}

/** "Jun 2026" / "juin 2026". */
export function fmtMonth(date: Date, lang: Lang): string {
  return date.toLocaleDateString(LOCALE[lang], { year: "numeric", month: "short" });
}

// ── The reader's choice ────────────────────────────────────────────────────────

const STORAGE_KEY = "atlas.lang.v1";

function isLang(value: unknown): value is Lang {
  return typeof value === "string" && (Object.keys(LANGUAGE_NAME) as string[]).includes(value);
}

/**
 * Where the language comes from, strongest first: a `?lang=` in the link, the
 * reader's own earlier choice, then the browser's FIRST preferred language.
 *
 * Only the first preference, not any: a reader who lists French second still
 * reads English first, and opening in French would be the app overruling them.
 */
function initialLang(): Lang {
  try {
    const fromLink = new URLSearchParams(window.location.search).get("lang");
    if (isLang(fromLink)) return fromLink;
  } catch {
    // No usable URL; fall through.
  }
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLang(stored)) return stored;
  } catch {
    // Storage blocked; fall through.
  }
  const first = (navigator.languages?.[0] ?? navigator.language ?? "").toLowerCase();
  return first.startsWith("fr") ? "fr" : "en";
}

interface I18n {
  lang: Lang;
  s: Strings;
  setLang: (lang: Lang) => void;
}

const I18nContext = createContext<I18n | null>(null);

/**
 * A context rather than a `lang` prop threaded through every panel. Twelve
 * components render interface text, several of them several levels down —
 * `TableView` inside every chart, `PinButton` inside every panel — and a prop
 * missed on any one of them renders English inside the French interface with
 * no error. A hook cannot be forgotten that way.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  // Only an explicit choice is remembered. Storing the browser-derived default
  // on first load would freeze it for no reason the reader could see.
  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage blocked: the choice lasts the session.
    }
  }, []);

  // `<html lang>` drives screen-reader pronunciation and hyphenation.
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = STRINGS[lang].appTitle;
  }, [lang]);

  const value = useMemo(() => ({ lang, s: STRINGS[lang], setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n() needs an <I18nProvider> above it");
  return value;
}

/** EN / FR. Each button names its language in that language, and says so to assistive tech. */
export function LanguageToggle({ className }: { className?: string }) {
  const { lang, s, setLang } = useI18n();
  return (
    <div className={className} role="group" aria-label={s.languageGroup}>
      {(Object.keys(LANGUAGE_NAME) as Lang[]).map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={lang === code}
          aria-label={LANGUAGE_NAME[code]}
          title={LANGUAGE_NAME[code]}
          onClick={() => setLang(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
