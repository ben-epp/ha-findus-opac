/*
 * Findus OPAC card: loan list with due dates and a renew button.
 * Served and auto-registered by the findus_opac integration; no build step, no dependencies.
 */
const CARD_VERSION = "0.3.0";
const DOMAIN = "findus_opac";

const ICONS = {
  book: "mdi:book-open-variant",
  tonie: "mdi:account-music",
  cd: "mdi:disc",
  video: "mdi:filmstrip",
  game: "mdi:gamepad-variant",
};

const TEXT = {
  de: {
    loans: "Ausleihen",
    none: "Keine Ausleihen – alles zurückgegeben.",
    overdue: (n) => `${n} überfällig`,
    today: "heute fällig",
    tomorrow: "morgen fällig",
    inDays: (n) => `in ${n} Tagen`,
    overdueDays: (n) => (n === 1 ? "seit 1 Tag überfällig" : `seit ${n} Tagen überfällig`),
    renewable: "verlängerbar",
    renewAll: (n) => `${n} verlängern`,
    renewing: "Verlängerung wird beantragt…",
    renewed: "Verlängerung beantragt. Neue Fristen erscheinen ggf. erst nach dem nächsten Abgleich.",
    failed: "Verlängerung fehlgeschlagen",
    more: (n) => `+ ${n} weitere`,
    missing: (e) => `Entität ${e} nicht gefunden`,
    next: "nächste Rückgabe",
    renewOne: "Nur dieses Medium verlängern",
    sync: "Jetzt mit der Bücherei abgleichen",
    synced: "Konto abgeglichen.",
  },
  en: {
    loans: "Loans",
    none: "No loans – everything returned.",
    overdue: (n) => `${n} overdue`,
    today: "due today",
    tomorrow: "due tomorrow",
    inDays: (n) => `in ${n} days`,
    overdueDays: (n) => (n === 1 ? "1 day overdue" : `${n} days overdue`),
    renewable: "renewable",
    renewAll: (n) => `Renew ${n}`,
    renewing: "Requesting renewal…",
    renewed: "Renewal requested. New due dates may only appear after the library's next sync.",
    failed: "Renewal failed",
    more: (n) => `+ ${n} more`,
    missing: (e) => `Entity ${e} not found`,
    next: "next due",
    renewOne: "Renew only this item",
    sync: "Sync with the library now",
    synced: "Account synced.",
  },
};

const LABELS = {
  de: {
    entity: "Ausleihen-Sensor",
    title: "Titel (leer = Kontoname)",
    show_renew: "Verlängern-Knopf anzeigen",
    show_covers: "Cover anzeigen",
    max_items: "Höchstens anzeigen (0 = alle)",
    warn_days: "Warnen ab Tagen vor Rückgabe",
  },
  en: {
    entity: "Loans sensor",
    title: "Title (empty = account name)",
    show_renew: "Show renew button",
    show_covers: "Show covers",
    max_items: "Maximum items (0 = all)",
    warn_days: "Warn days before due",
  },
};

const lang = (hass) => (hass?.locale?.language || hass?.language || "en").startsWith("de") ? "de" : "en";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** Registry entry of this integration's entity with the given translation key on a device. */
const findEntity = (hass, deviceId, domain, key) =>
  Object.values(hass.entities || {}).find(
    (e) =>
      e.platform === DOMAIN &&
      e.device_id === deviceId &&
      e.translation_key === key &&
      e.entity_id.startsWith(`${domain}.`),
  )?.entity_id;

const findLoanSensors = (hass) =>
  Object.values(hass.entities || {})
    .filter((e) => e.platform === DOMAIN && e.translation_key === "loans" && e.entity_id.startsWith("sensor."))
    .map((e) => e.entity_id);

class FindusOpacCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("findus-opac-card-editor");
  }

  static getStubConfig(hass) {
    return { entity: findLoanSensors(hass)[0] || "" };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("entity is required: pick the Findus 'Loans' sensor");
    }
    this._config = { show_renew: true, show_covers: true, max_items: 0, warn_days: 3, ...config };
    this._lastKey = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const items = this._items().length;
    return 2 + Math.min(items, this._config?.max_items || items);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 2 };
  }

  _items() {
    const st = this._hass?.states?.[this._config?.entity];
    return Array.isArray(st?.attributes?.items) ? st.attributes.items : [];
  }

  _render() {
    if (!this._hass || !this._config) return;
    const hass = this._hass;
    const t = TEXT[lang(hass)];
    const st = hass.states[this._config.entity];
    const reg = hass.entities?.[this._config.entity];
    const deviceId = reg?.device_id;
    const renewId = deviceId ? findEntity(hass, deviceId, "button", "renew_all") : undefined;
    const syncId = deviceId ? findEntity(hass, deviceId, "button", "sync") : undefined;
    const device = deviceId ? hass.devices?.[deviceId] : undefined;
    const entryId = device?.primary_config_entry || device?.config_entries?.[0];

    // Re-render only when something visible changed; hass updates arrive constantly.
    const key = JSON.stringify([
      st?.last_updated, st?.state, renewId, syncId, entryId,
      this._busy, this._busyItem, this._syncing, this._config, lang(hass),
    ]);
    if (key === this._lastKey) return;
    this._lastKey = key;

    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    if (!st) {
      this.shadowRoot.innerHTML = `<ha-card><div class="warn">${esc(t.missing(this._config.entity))}</div></ha-card>${STYLE}`;
      return;
    }

    const title = this._config.title || (deviceId && hass.devices?.[deviceId]?.name) || t.loans;
    const items = [...this._items()].sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : 0));
    const max = Number(this._config.max_items) || items.length;
    const shown = items.slice(0, max);
    const overdue = items.filter((i) => i.days_left < 0).length;
    const renewable = items.filter((i) => i.renewable).length;
    const locale = hass.locale?.language || "de";
    const fmtDate = (iso) =>
      new Date(`${iso}T12:00:00`).toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "numeric" });

    const dueText = (d) =>
      d < 0 ? t.overdueDays(-d) : d === 0 ? t.today : d === 1 ? t.tomorrow : t.inDays(d);
    const level = (d) => (d < 0 ? "overdue" : d <= Number(this._config.warn_days) ? "soon" : "ok");

    const rows = shown
      .map(
        (i) => `
        <div class="row ${level(i.days_left)}" title="${esc(i.note)}">
          ${
            this._config.show_covers && /^https:\/\//.test(i.cover || "")
              ? `<img class="cover" src="${esc(i.cover)}" alt="" loading="lazy" referrerpolicy="no-referrer"
                   data-icon="${ICONS[i.category] || ICONS.book}">`
              : `<ha-icon class="type" icon="${ICONS[i.category] || ICONS.book}"></ha-icon>`
          }
          <div class="main">
            <div class="name">${esc(i.title)}</div>
            <div class="sub">${esc([i.media_type, i.author].filter(Boolean).join(" · "))}</div>
          </div>
          <div class="due">
            <div class="date">${esc(fmtDate(i.due))}</div>
            <div class="left">${esc(dueText(i.days_left))}</div>
            ${i.renewable ? `<span class="chip">${esc(t.renewable)}</span>` : ""}
            ${
              i.renewable && entryId && this._config.show_renew
                ? `<button class="icon-btn item-renew" data-mednr="${esc(i.mednr)}" title="${esc(t.renewOne)}"
                     ${this._busy || this._busyItem ? "disabled" : ""}>
                     <ha-icon icon="${this._busyItem === i.mednr ? "mdi:timer-sand" : "mdi:book-refresh"}"></ha-icon>
                   </button>`
                : ""
            }
          </div>
        </div>`,
      )
      .join("");

    const showRenew = this._config.show_renew && renewId && renewable > 0;
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="header">
          <div class="title">${esc(title)}</div>
          <div class="badges">
            <span class="badge">${items.length} ${esc(t.loans)}</span>
            ${overdue ? `<span class="badge bad">${esc(t.overdue(overdue))}</span>` : ""}
            ${
              syncId
                ? `<button id="sync" class="icon-btn ${this._syncing ? "spin" : ""}" title="${esc(t.sync)}"
                     ${this._syncing ? "disabled" : ""}><ha-icon icon="mdi:sync"></ha-icon></button>`
                : ""
            }
          </div>
        </div>
        <div class="list">
          ${items.length ? rows : `<div class="empty">${esc(t.none)}</div>`}
          ${items.length > shown.length ? `<div class="more">${esc(t.more(items.length - shown.length))}</div>` : ""}
        </div>
        ${
          showRenew
            ? `<div class="actions"><button id="renew" ${this._busy ? "disabled" : ""}>
                 <ha-icon icon="mdi:book-refresh"></ha-icon>&nbsp;${esc(this._busy ? t.renewing : t.renewAll(renewable))}
               </button></div>`
            : ""
        }
      </ha-card>${STYLE}`;

    this.shadowRoot.getElementById("renew")?.addEventListener("click", () => this._renew(renewId));
    this.shadowRoot.getElementById("sync")?.addEventListener("click", () => this._sync(syncId));
    this.shadowRoot.querySelectorAll("button.item-renew").forEach((btn) =>
      btn.addEventListener("click", () => this._renewOne(entryId, btn.dataset.mednr)),
    );
    // Missing or broken cover: fall back to the media-type icon.
    this.shadowRoot.querySelectorAll("img.cover").forEach((img) => {
      const fallback = () => {
        const icon = document.createElement("ha-icon");
        icon.className = "type";
        icon.setAttribute("icon", img.dataset.icon);
        img.replaceWith(icon);
      };
      img.addEventListener("error", fallback, { once: true });
      // Some cover services answer a 1x1 placeholder instead of an error.
      img.addEventListener("load", () => img.naturalWidth < 10 && fallback(), { once: true });
    });
  }

  async _renew(entityId) {
    if (this._busy) return;
    const t = TEXT[lang(this._hass)];
    this._busy = true;
    this._render();
    try {
      await this._hass.callService("button", "press", { entity_id: entityId });
      this._toast(t.renewed);
    } catch (err) {
      this._toast(`${t.failed}: ${err?.message || err}`);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _renewOne(entryId, mednr) {
    if (this._busy || this._busyItem) return;
    const t = TEXT[lang(this._hass)];
    this._busyItem = mednr;
    this._render();
    try {
      await this._hass.callService(DOMAIN, "renew", { config_entry_id: entryId, media_ids: [mednr] });
      this._toast(t.renewed);
    } catch (err) {
      this._toast(`${t.failed}: ${err?.message || err}`);
    } finally {
      this._busyItem = undefined;
      this._render();
    }
  }

  async _sync(entityId) {
    if (this._syncing) return;
    const t = TEXT[lang(this._hass)];
    this._syncing = true;
    this._render();
    try {
      await this._hass.callService("button", "press", { entity_id: entityId });
      this._toast(t.synced);
    } catch (err) {
      this._toast(`${err?.message || err}`);
    } finally {
      this._syncing = false;
      this._render();
    }
  }

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }
}

const STYLE = `<style>
  ha-card { padding: 12px 16px 8px; }
  .header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
  .title { font-size: 1.2em; font-weight: 500; }
  .badges { display: flex; gap: 6px; align-items: center; }
  .icon-btn { border: none; background: none; cursor: pointer; padding: 4px; border-radius: 50%;
              color: var(--secondary-text-color); line-height: 0; }
  .icon-btn:hover { background: var(--secondary-background-color); color: var(--primary-color, #03a9f4); }
  .icon-btn[disabled] { opacity: .5; cursor: default; }
  .item-renew { color: var(--success-color, #43a047); vertical-align: middle; }
  .spin ha-icon { animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(-360deg); } }
  .badge { font-size: .8em; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color); }
  .badge.bad { background: var(--error-color); color: var(--text-primary-color, #fff); }
  .list { margin-top: 8px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-top: 1px solid var(--divider-color); }
  .row:first-child { border-top: none; }
  .type { color: var(--state-icon-color, var(--paper-item-icon-color)); flex: none; width: 40px; text-align: center; }
  .cover { width: 40px; height: 56px; object-fit: cover; border-radius: 4px; flex: none;
           background: var(--secondary-background-color); box-shadow: 0 1px 3px rgba(0,0,0,.25); }
  .main { flex: 1; min-width: 0; }
  .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { font-size: .85em; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .due { text-align: right; flex: none; font-size: .9em; }
  .left { font-size: .85em; color: var(--secondary-text-color); }
  .row.soon .left, .row.soon .type { color: var(--warning-color); }
  .row.overdue .left, .row.overdue .type, .row.overdue .date { color: var(--error-color); font-weight: 500; }
  .chip { display: inline-block; margin-top: 2px; font-size: .75em; padding: 0 6px; border-radius: 8px;
          border: 1px solid var(--success-color, #4caf50); color: var(--success-color, #4caf50); }
  .empty, .more, .warn { padding: 8px 0; color: var(--secondary-text-color); }
  .warn { color: var(--error-color); }
  .actions { display: flex; justify-content: flex-end; border-top: 1px solid var(--divider-color); padding-top: 4px; margin-top: 4px; }
  #renew { display: inline-flex; align-items: center; gap: 4px; border: none; background: none; cursor: pointer;
           color: var(--primary-color, #03a9f4); font: inherit; font-weight: 500; padding: 8px; border-radius: 8px; }
  #renew:hover { background: var(--secondary-background-color); }
  #renew[disabled] { opacity: .6; cursor: default; }
</style>`;

class FindusOpacCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        this._config = ev.detail.value;
        this.dispatchEvent(
          new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }),
        );
      });
      this.appendChild(this._form);
    }
    const labels = LABELS[lang(this._hass)];
    this._form.hass = this._hass;
    this._form.data = { show_renew: true, show_covers: true, max_items: 0, warn_days: 3, ...this._config };
    this._form.computeLabel = (s) => labels[s.name] || s.name;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { filter: { integration: DOMAIN, domain: "sensor" } } } },
      { name: "title", selector: { text: {} } },
      { name: "show_renew", selector: { boolean: {} } },
      { name: "show_covers", selector: { boolean: {} } },
      { name: "max_items", selector: { number: { min: 0, max: 50, mode: "box" } } },
      { name: "warn_days", selector: { number: { min: 0, max: 14, mode: "box" } } },
    ];
  }
}

if (!customElements.get("findus-opac-card")) {
  customElements.define("findus-opac-card", FindusOpacCard);
  customElements.define("findus-opac-card-editor", FindusOpacCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "findus-opac-card",
    name: "Findus Bibliothek",
    description: "Ausleihen mit Rückgabefristen und Verlängern-Knopf (findus_opac)",
    preview: true,
    documentationURL: "https://github.com/ben-epp/ha-findus-opac",
  });
  console.info(`%c FINDUS-OPAC-CARD %c ${CARD_VERSION} `, "background:#2e7d32;color:#fff", "");
}
