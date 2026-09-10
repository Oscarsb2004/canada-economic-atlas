/**
 * ProvincePanel — a deliberately small home for province-level exploration.
 *
 * The map's StatCan boundary file is authoritative for the province name and
 * code — in both languages, since it carries PRENAME and PRFNAME. Everything
 * else is held as TBD until it can be sourced and published through the
 * pipeline; a plausible-looking hand-written motto or coat of arms would be
 * worse than an honest empty profile.
 */

import { t } from "../data/bundle";
import { useI18n } from "../i18n";
import type { ProvinceSummary } from "../map/Globe";

export function ProvincePanel({
  province,
  onClose,
}: {
  province: ProvinceSummary;
  onClose: () => void;
}) {
  const { lang, s } = useI18n();
  const name = t(province.name, lang);
  return (
    <article className="province-panel">
      <header className="province-panel__header">
        <div>
          <p className="province-panel__eyebrow">{s.provinceEyebrow}</p>
          <h1>{name}</h1>
          <p className="muted">{province.code} · {s.profileInDevelopment}</p>
        </div>
        <button type="button" className="province-panel__close" onClick={onClose}>
          {s.backToOverview}
        </button>
      </header>

      <section className="province-panel__identity" aria-label={s.provinceIdentity(name)}>
        <div className="province-panel__emblem" aria-hidden="true">{s.emblemTbd}</div>
        <div>
          <h2>{s.flagHeading}</h2>
          <p className="muted">{s.flagTbd}</p>
        </div>
      </section>

      <section className="province-panel__section">
        <h2>{s.mottoHeading}</h2>
        <p className="muted">{s.mottoTbd}</p>
      </section>

      <section className="province-panel__section">
        <h2>{s.profileHeading}</h2>
        <p className="muted">{s.profileTbd}</p>
      </section>
    </article>
  );
}
