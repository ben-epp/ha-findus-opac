/*
 * Findus OPAC card: loan list with due dates and a renew button.
 * Served and auto-registered by the findus_opac integration; no build step, no dependencies.
 */
const CARD_VERSION = "0.8.0";
const DOMAIN = "findus_opac";

const ICONS = {
  book: "mdi:book-open-variant",
  tonie: "mdi:account-music",
  cd: "mdi:disc",
  video: "mdi:filmstrip",
  game: "mdi:gamepad-variant",
};

// Weekends and short breaks are normal; beyond this the card flags the data as old.
const SYNC_STALE_DAYS = 4;

const TEXT = {
  de: {
    syncAt: (d) => `Datenstand der Bücherei: ${d}`,
    hoursOpen: (t) => `Geöffnet bis ${t}`,
    hoursClosed: "Geschlossen",
    hoursOpens: (d) => `Geschlossen, öffnet ${d}`,
    hoursUnsure: "Heute nur unter Vorbehalt geöffnet",
    hoursHint: "Reguläre Öffnungszeiten, an Feiertagen können sie abweichen.",
    hoursMore: "Alle Zeiten",
    hoursLess: "Weniger",
    hoursDayClosed: "geschlossen",
    hoursCond: "siehe Bücherei",
    loans: "Ausleihen",
    none: "Keine Ausleihen – alles zurückgegeben.",
    overdue: (n) => `${n} überfällig`,
    today: "heute fällig",
    tomorrow: "morgen fällig",
    inDays: (n) => `in ${n} Tagen`,
    overdueDays: (n) => (n === 1 ? "seit 1 Tag überfällig" : `seit ${n} Tagen überfällig`),
    renewable: "verlängerbar",
    pending: "Verlängerung beantragt",
    block: {
      limit: "Verlängerungen ausgeschöpft",
      reserved: "Vorbestellt",
      too_early: "Noch nicht verlängerbar",
      other: "Nicht verlängerbar",
    },
    renewAll: (n) => `${n} verlängern`,
    renewing: "Verlängerung wird beantragt…",
    renewed: "Verlängerung beantragt. Neue Fristen erscheinen ggf. erst nach dem nächsten Abgleich.",
    failed: "Verlängerung fehlgeschlagen",
    more: (n) => `+ ${n} weitere`,
    missing: (e) => `Entität ${e} nicht gefunden`,
    next: "nächste Rückgabe",
    renewOne: "Nur dieses Medium verlängern",
    noticeMore: "Mehr anzeigen",
    noticeLess: "Weniger anzeigen",
    noticeSite: "Vollständig auf der Webseite der Bibliothek lesen",
    sync: "Jetzt mit der Bücherei abgleichen",
    synced: "Konto abgeglichen.",
    items: (n) => (n === 1 ? "1 Medium" : `${n} Medien`),
    cats: { book: "Bücher", tonie: "Tonies", cd: "CDs", video: "Filme", game: "Spiele" },
    cardValid: (d) => `Ausweis gültig bis ${d}`,
    cardExpired: (d) => `Ausweis abgelaufen seit ${d}`,
  },
  en: {
    syncAt: (d) => `Library data from ${d}`,
    hoursOpen: (t) => `Open until ${t}`,
    hoursClosed: "Closed",
    hoursOpens: (d) => `Closed, opens ${d}`,
    hoursUnsure: "Open today only under certain conditions",
    hoursHint: "Regular opening hours; they can differ on holidays.",
    hoursMore: "All hours",
    hoursLess: "Less",
    hoursDayClosed: "closed",
    hoursCond: "ask the library",
    loans: "Loans",
    none: "No loans – everything returned.",
    overdue: (n) => `${n} overdue`,
    today: "due today",
    tomorrow: "due tomorrow",
    inDays: (n) => `in ${n} days`,
    overdueDays: (n) => (n === 1 ? "1 day overdue" : `${n} days overdue`),
    renewable: "renewable",
    pending: "renewal requested",
    block: {
      limit: "Renewal limit reached",
      reserved: "Reserved",
      too_early: "Not yet renewable",
      other: "Not renewable",
    },
    renewAll: (n) => `Renew ${n}`,
    renewing: "Requesting renewal…",
    renewed: "Renewal requested. New due dates may only appear after the library's next sync.",
    failed: "Renewal failed",
    more: (n) => `+ ${n} more`,
    missing: (e) => `Entity ${e} not found`,
    next: "next due",
    renewOne: "Renew only this item",
    noticeMore: "Show more",
    noticeLess: "Show less",
    noticeSite: "Read the full notice on the library's website",
    sync: "Sync with the library now",
    synced: "Account synced.",
    items: (n) => (n === 1 ? "1 item" : `${n} items`),
    cats: { book: "Books", tonie: "Tonies", cd: "CDs", video: "Videos", game: "Games" },
    cardValid: (d) => `Library card valid until ${d}`,
    cardExpired: (d) => `Library card expired on ${d}`,
  },
};

const LABELS = {
  de: {
    entity: "Ausleihen-Sensor",
    title: "Titel (leer = Kontoname)",
    show_renew: "Verlängern-Knopf anzeigen",
    show_covers: "Cover anzeigen",
    show_card_expiry: "Ausweis-Gültigkeit anzeigen",
    show_announcement: "Mitteilung der Bibliothek anzeigen",
    show_hours: "Öffnungszeiten anzeigen",
    show_last_sync: "Datenstand der Bücherei anzeigen",
    max_items: "Höchstens anzeigen (0 = alle)",
    warn_days: "Warnen ab Tagen vor Rückgabe",
    group_by: "Gruppieren (aufklappbar)",
    max_height: "Maximale Listenhöhe in px (0 = keine, sonst scrollbar)",
  },
  en: {
    entity: "Loans sensor",
    title: "Title (empty = account name)",
    show_renew: "Show renew button",
    show_covers: "Show covers",
    show_card_expiry: "Show library card expiry",
    show_announcement: "Show library announcement",
    show_hours: "Show opening hours",
    show_last_sync: "Show library data date",
    max_items: "Maximum items (0 = all)",
    warn_days: "Warn days before due",
    group_by: "Group (collapsible)",
    max_height: "Maximum list height in px (0 = none, else scrollable)",
  },
};

const DEFAULTS = {
  show_renew: true,
  show_covers: true,
  show_card_expiry: true,
  show_announcement: true,
  show_hours: true,
  show_last_sync: true,
  max_items: 0,
  warn_days: 3,
  group_by: "due",
  max_height: 400,
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
    this._config = { ...DEFAULTS, ...config };
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
    const cardSensor = deviceId ? findEntity(hass, deviceId, "sensor", "card_valid_until") : undefined;
    const cardState = cardSensor ? hass.states[cardSensor] : undefined;
    const noticeId = deviceId ? findEntity(hass, deviceId, "sensor", "announcement") : undefined;
    const notice = noticeId ? hass.states[noticeId] : undefined;
    const syncSensor = deviceId ? findEntity(hass, deviceId, "sensor", "last_sync") : undefined;
    const syncState = syncSensor ? hass.states[syncSensor] : undefined;
    const openSensor = deviceId ? findEntity(hass, deviceId, "binary_sensor", "open_now") : undefined;
    const openState = openSensor ? hass.states[openSensor] : undefined;
    const device = deviceId ? hass.devices?.[deviceId] : undefined;
    const entryId = device?.primary_config_entry || device?.config_entries?.[0];

    // Re-render only when something visible changed; hass updates arrive constantly.
    const key = JSON.stringify([
      st?.last_updated, st?.state, renewId, syncId, entryId, cardState?.state,
      notice?.last_updated, this._noticeOpen, syncState?.state, openState?.last_updated, this._hoursOpen, this._busy, this._busyItem, this._syncing, this._config, lang(hass), [...(this._open || [])],
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

    const row = (i) => `
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
            ${i.renew_requested ? `<span class="chip pending">${esc(t.pending)}</span>` : ""}
            ${
              t.block[i.renew_block]
                ? `<span class="chip block ${i.renew_block === "too_early" ? "early" : ""}" title="${esc(i.note)}">${esc(t.block[i.renew_block])}</span>`
                : ""
            }
            ${
              i.renewable && entryId && this._config.show_renew
                ? `<button class="icon-btn item-renew" data-mednr="${esc(i.mednr)}" title="${esc(t.renewOne)}"
                     ${this._busy || this._busyItem ? "disabled" : ""}>
                     <ha-icon icon="${this._busyItem === i.mednr ? "mdi:timer-sand" : "mdi:book-refresh"}"></ha-icon>
                   </button>`
                : ""
            }
          </div>
        </div>`;

    // Accordion: group by due date (mirrors the loan length per media type) or by category.
    const rank = { overdue: 0, soon: 1, ok: 2 };
    const groupBy = this._config.group_by;
    const groups = [];
    if (groupBy === "due" || groupBy === "category") {
      const byKey = new Map();
      for (const i of shown) {
        const k = groupBy === "due" ? i.due : i.category;
        if (!byKey.has(k)) byKey.set(k, []);
        byKey.get(k).push(i);
      }
      for (const [k, list] of byKey) {
        const lvl = list.map((i) => level(i.days_left)).sort((a, b) => rank[a] - rank[b])[0];
        const label =
          groupBy === "due"
            ? `${fmtDate(k)} · ${dueText(list[0].days_left)}`
            : `${t.cats[k] || k} · ${t.next} ${fmtDate(list[0].due)}`;
        groups.push({ key: k, list, lvl, label });
      }
      if (groupBy === "category") groups.sort((a, b) => (a.list[0].due < b.list[0].due ? -1 : 1));
    }
    if (!this._open || this._openFor !== groupBy) {
      this._openFor = groupBy;
      this._open = new Set();
      this._seen = new Set();
    }
    // Default per group, decided the first time it appears: urgent open, the rest collapsed;
    // a single group is always open. Later taps override it.
    for (const g of groups) {
      const k = String(g.key);
      if (this._seen.has(k)) continue;
      this._seen.add(k);
      if (g.lvl !== "ok" || groups.length === 1) this._open.add(k);
    }
    const rows = groups.length
      ? groups
          .map((g) => {
            const open = this._open.has(String(g.key));
            const ren = g.list.filter((i) => i.renewable).length;
            return `
        <button class="group ${g.lvl}" data-key="${esc(g.key)}" aria-expanded="${open}">
          <ha-icon icon="${open ? "mdi:chevron-down" : "mdi:chevron-right"}"></ha-icon>
          <span class="glabel">${esc(g.label)}</span>
          ${ren ? `<span class="chip">${esc(t.renewable)} ${ren}</span>` : ""}
          <span class="gcount">${esc(t.items(g.list.length))}</span>
        </button>
        ${open ? `<div class="gbody">${g.list.map(row).join("")}</div>` : ""}`;
          })
          .join("")
      : shown.map(row).join("");

    const showRenew = this._config.show_renew && renewId && renewable > 0;
    let cardLine = "";
    if (this._config.show_card_expiry && /^\d{4}-\d{2}-\d{2}$/.test(cardState?.state || "")) {
      const days = Number(cardState.attributes?.days_left);
      const d = new Date(`${cardState.state}T12:00:00`).toLocaleDateString(locale, {
        day: "numeric", month: "long", year: "numeric",
      });
      const lvl = days < 0 ? "overdue" : days <= 30 ? "soon" : "ok";
      cardLine = `<div class="cardline ${lvl}"><ha-icon icon="mdi:card-account-details"></ha-icon>${esc(
        days < 0 ? t.cardExpired(d) : t.cardValid(d),
      )}</div>`;
    }
    let syncLine = "";
    const synced = this._config.show_last_sync ? new Date(syncState?.state || "") : null;
    if (synced && !isNaN(synced)) {
      const stale = Date.now() - synced.getTime() > SYNC_STALE_DAYS * 86400000;
      syncLine = `<div class="cardline ${stale ? "soon" : "ok"}"><ha-icon icon="mdi:database-clock-outline"></ha-icon>${esc(
        t.syncAt(synced.toLocaleString(locale, { day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" })),
      )}</div>`;
    }
    let hoursBlock = "";
    const ha = openState?.attributes;
    if (this._config.show_hours && ha?.hours && openState.state !== "unavailable") {
      const opens = ha.next_open ? new Date(ha.next_open) : null;
      const opensText = opens && opens.toLocaleString(locale, { weekday: "short", hour: "2-digit", minute: "2-digit" });
      const status = openState.state === "on" && ha.closes_at ? t.hoursOpen(ha.closes_at)
        : openState.state === "off" ? (opensText ? t.hoursOpens(opensText) : t.hoursClosed)
        : t.hoursUnsure;
      const open = !!this._hoursOpen;
      const dayName = (i) => new Date(2024, 0, 1 + i).toLocaleDateString(locale, { weekday: "short" }); // 2024-01-01 is a Monday
      const week = Object.entries(ha.hours).map(([day, times], i) => `<tr><td>${esc(dayName(i))}</td><td>${esc(
        (ha.conditional_days || []).includes(day) ? [...times, t.hoursCond].join(", ") : times.join(", ") || t.hoursDayClosed,
      )}</td></tr>`).join("");
      hoursBlock = `<div class="hours">
        <div class="hstatus ${openState.state === "on" ? "isopen" : ""}"><ha-icon icon="mdi:clock-outline"></ha-icon>${esc(status)}
          <button id="hours-toggle" class="link">${esc(open ? t.hoursLess : t.hoursMore)}</button></div>
        ${open ? `<table class="hweek">${week}</table>${ha.note ? `<div class="hint">${esc(ha.note)}</div>` : ""}` : ""}
        <div class="hint">${esc(t.hoursHint)}</div>
      </div>`;
    }
    let noticeBlock = "";
    const na = notice?.attributes;
    if (this._config.show_announcement && notice && !["unknown", "unavailable"].includes(notice.state) && na) {
      const open = !!this._noticeOpen;
      const http = (u) => typeof u === "string" && /^https?:\/\//i.test(u);
      const imgs = open ? (na.images || []).filter(http) : [];
      noticeBlock = `<div class="notice ${na.kind === "closure" ? "closure" : "info"}">
        <div class="ntitle"><ha-icon icon="${na.kind === "closure" ? "mdi:store-clock" : "mdi:information-outline"}"></ha-icon>${esc(notice.state)}</div>
        <div class="ntext ${open ? "open" : ""}">${esc(na.truncated && http(na.url) ? na.text.replace(/…$/, "") : na.text)}${na.truncated && http(na.url) ? ` <a href="${esc(na.url)}" target="_blank" rel="noopener noreferrer" title="${esc(t.noticeSite)}">…</a>` : ""}</div>
        ${imgs.map((u) => `<img class="nimg" src="${esc(u)}" alt="" loading="lazy" referrerpolicy="no-referrer">`).join("")}
        ${(na.text || "").length > 140 || (na.images || []).length ? `<button id="notice-toggle" class="link">${esc(open ? t.noticeLess : t.noticeMore)}</button>` : ""}
      </div>`;
    }
    const maxH = Number(this._config.max_height) || 0;
    const scrollTop = this.shadowRoot.querySelector(".list")?.scrollTop || 0;
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="header">
          <div class="titlebox"><div class="title">${esc(title)}</div>${cardLine}${syncLine}</div>
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
        ${hoursBlock}
        ${noticeBlock}
        <div class="list" style="${maxH > 0 ? `max-height:${maxH}px;overflow-y:auto` : ""}">
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
    const list = this.shadowRoot.querySelector(".list");
    if (list) list.scrollTop = scrollTop; // keep position across hass updates
    this.shadowRoot.querySelectorAll("button.group").forEach((btn) =>
      btn.addEventListener("click", () => {
        const k = btn.dataset.key;
        if (this._open.has(k)) this._open.delete(k);
        else this._open.add(k);
        this._render();
      }),
    );
    this.shadowRoot.getElementById("hours-toggle")?.addEventListener("click", () => {
      this._hoursOpen = !this._hoursOpen;
      this._render();
    });
    this.shadowRoot.getElementById("notice-toggle")?.addEventListener("click", () => {
      this._noticeOpen = !this._noticeOpen;
      this._render();
    });
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
  .cardline { display: flex; align-items: center; gap: 4px; font-size: .8em; color: var(--secondary-text-color); }
  .cardline ha-icon { --mdc-icon-size: 16px; }
  .cardline.soon { color: var(--warning-color); }
  .cardline.overdue { color: var(--error-color); font-weight: 500; }
  .hours { margin: 8px 0; font-size: .9em; }
  .hstatus { display: flex; align-items: center; gap: 4px; }
  .hstatus ha-icon { --mdc-icon-size: 16px; }
  .hstatus.isopen { color: var(--success-color, #43a047); }
  .hstatus .link { margin-left: auto; }
  .hweek { border-collapse: collapse; margin-top: 4px; }
  .hweek td { padding: 1px 12px 1px 0; }
  .hint { margin-top: 2px; font-size: .85em; color: var(--secondary-text-color); }
  .notice { margin: 8px 0; padding: 8px 12px; border-radius: 8px; border-left: 4px solid var(--info-color, #039be5);
            background: var(--secondary-background-color); }
  .notice.closure { border-left-color: var(--warning-color, #ffa600); }
  .ntitle { display: flex; align-items: center; gap: 6px; font-weight: 500; }
  .ntitle ha-icon { --mdc-icon-size: 18px; flex: none; }
  .ntext { margin-top: 4px; font-size: .9em; white-space: pre-line; overflow-wrap: anywhere; }
  .ntext:not(.open) { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .nimg { display: block; max-width: 100%; margin-top: 8px; border-radius: 4px; }
  .link { border: none; background: none; padding: 4px 0 0; cursor: pointer; color: var(--primary-color); font: inherit; font-size: .85em; }
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
  .list { overscroll-behavior: contain; scrollbar-width: thin; }
  .group { display: flex; align-items: center; gap: 6px; width: 100%; border: none; cursor: pointer; font: inherit;
           text-align: left; padding: 8px 4px; margin-top: 4px; border-radius: 8px;
           background: var(--secondary-background-color); color: var(--primary-text-color); }
  .group .glabel { flex: 1; font-weight: 500; }
  .group .gcount { font-size: .85em; color: var(--secondary-text-color); }
  .group.soon .glabel { color: var(--warning-color); }
  .group.overdue .glabel { color: var(--error-color); }
  .group .chip { margin-top: 0; }
  .gbody { padding: 0 4px 0 8px; }
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
  .chip.pending { border-color: var(--info-color, #039be5); color: var(--info-color, #039be5); }
  .chip.block { border-color: var(--warning-color, #ffa600); color: var(--warning-color, #ffa600); }
  .chip.block.early { border-color: var(--divider-color); color: var(--secondary-text-color); }
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
    this._form.data = { ...DEFAULTS, ...this._config };
    this._form.computeLabel = (s) => labels[s.name] || s.name;
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { filter: { integration: DOMAIN, domain: "sensor" } } } },
      { name: "title", selector: { text: {} } },
      { name: "show_renew", selector: { boolean: {} } },
      { name: "show_covers", selector: { boolean: {} } },
      { name: "show_card_expiry", selector: { boolean: {} } },
      { name: "show_announcement", selector: { boolean: {} } },
      { name: "show_hours", selector: { boolean: {} } },
      { name: "show_last_sync", selector: { boolean: {} } },
      { name: "max_items", selector: { number: { min: 0, max: 50, mode: "box" } } },
      { name: "warn_days", selector: { number: { min: 0, max: 14, mode: "box" } } },
      {
        name: "group_by",
        selector: {
          select: {
            mode: "dropdown",
            options: lang(this._hass) === "de"
              ? [{ value: "due", label: "Nach Rückgabedatum" }, { value: "category", label: "Nach Medienart" }, { value: "none", label: "Nicht gruppieren" }]
              : [{ value: "due", label: "By due date" }, { value: "category", label: "By media type" }, { value: "none", label: "No grouping" }],
          },
        },
      },
      { name: "max_height", selector: { number: { min: 0, max: 2000, step: 50, mode: "box" } } },
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
