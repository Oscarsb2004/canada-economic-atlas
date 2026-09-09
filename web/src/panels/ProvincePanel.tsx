/**
 * ProvincePanel — a deliberately small home for province-level exploration.
 *
 * The map's StatCan boundary file is authoritative for the province name and
 * code. Everything else is held as TBD until it can be sourced and published
 * through the pipeline; a plausible-looking hand-written motto or coat of arms
 * would be worse than an honest empty profile.
 */

import type { ProvinceSummary } from "../map/Globe";

export function ProvincePanel({
  province,
  onClose,
}: {
  province: ProvinceSummary;
  onClose: () => void;
}) {
  return (
    <article className="province-panel">
      <header className="province-panel__header">
        <div>
          <p className="province-panel__eyebrow">Province or territory</p>
          <h1>{province.name}</h1>
          <p className="muted">{province.code} · profile in development</p>
        </div>
        <button type="button" className="province-panel__close" onClick={onClose}>
          Back to overview
        </button>
      </header>

      <section className="province-panel__identity" aria-label={`${province.name} identity`}>
        <div className="province-panel__emblem" aria-hidden="true">TBD</div>
        <div>
          <h2>Flag / coat of arms</h2>
          <p className="muted">TBD — official artwork and its source will be added here.</p>
        </div>
      </section>

      <section className="province-panel__section">
        <h2>Nickname or motto</h2>
        <p className="muted">TBD — this will use the province or territory’s own published wording.</p>
      </section>

      <section className="province-panel__section">
        <h2>Province profile</h2>
        <p className="muted">
          TBD. Population, economic and geographic details will be added as sourced data rather than inferred from the map.
        </p>
      </section>
    </article>
  );
}
