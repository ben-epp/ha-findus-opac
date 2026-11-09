// Render tests for the Lovelace card, run by `node --test` (wrapped by test_card_js.py).
// A minimal DOM stub: the card only sets innerHTML and looks up a few elements.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const defined = {};
globalThis.window = globalThis;
globalThis.customElements = { get: (n) => defined[n], define: (n, c) => (defined[n] = c) };
globalThis.HTMLElement = class {
  attachShadow() {
    const handlers = {};
    this.shadowRoot = {
      innerHTML: "",
      handlers,
      querySelector: () => null,
      querySelectorAll: () => [],
      getElementById: (id) =>
        this.shadowRoot.innerHTML.includes(`id="${id}"`)
          ? { addEventListener: (_ev, fn) => (handlers[id] = fn) }
          : null,
    };
    return this.shadowRoot;
  }
  dispatchEvent() {}
};
console.info = () => {};
vm.runInThisContext(
  readFileSync(new URL("../custom_components/findus_opac/frontend/findus-opac-card.js", import.meta.url), "utf8"),
);
const Card = defined["findus-opac-card"];

const item = (title, due, days_left, extra = {}) => ({
  title, due, days_left, category: "book", media_type: "Buch", mednr: title, renewable: false, ...extra,
});

/** A hass object with one device per account: [name, library, items, cardDays]. */
function makeHass(accounts) {
  const hass = { states: {}, entities: {}, devices: {}, locale: { language: "de" }, calls: [] };
  hass.callService = async (domain, service, data) => hass.calls.push([domain, service, data]);
  const add = (id, device, key, state, attributes = {}) => {
    hass.entities[id] = { entity_id: id, device_id: device, platform: "findus_opac", translation_key: key };
    hass.states[id] = { entity_id: id, state, attributes, last_updated: "x" };
  };
  for (const [name, library, items, cardDays = 400] of accounts) {
    const slug = name.toLowerCase();
    const device = `dev_${slug}`;
    hass.devices[device] = { name, model: library, primary_config_entry: `entry_${slug}` };
    add(`sensor.${slug}_loans`, device, "loans", String(items.length), { items });
    add(`button.${slug}_renew_all`, device, "renew_all", "unknown");
    add(`button.${slug}_sync`, device, "sync", "unknown");
    add(`sensor.${slug}_card`, device, "card_valid_until", "2027-01-01", { days_left: cardDays });
    add(`sensor.${slug}_last_sync`, device, "last_sync", new Date().toISOString());
    add(`binary_sensor.${slug}_open`, device, "open_now", "on", {
      hours: { mon: ["09:00-12:00"] }, closes_at: "12:00",
    });
    add(`sensor.${slug}_notice`, device, "announcement", `Mitteilung ${library}`, { text: "Text", kind: "info" });
  }
  return hass;
}

function render(config, hass) {
  const card = new Card();
  card.setConfig(config);
  card.hass = hass;
  return card;
}

const count = (html, needle) => html.split(needle).length - 1;

test("single account renders as before, without owner labels", () => {
  const hass = makeHass([["Lena", "alzey", [item("Drache", "2026-11-10", 2, { renewable: true })]]]);
  const html = render({ entity: "sensor.lena_loans" }, hass).shadowRoot.innerHTML;
  assert.match(html, /class="title">Lena</);
  assert.doesNotMatch(html, /class="owner"/);
  assert.match(html, /data-entry="entry_lena"/);
  assert.doesNotMatch(html, /Lena: Ausweis/);
  assert.match(html, /Ausweis gültig bis/);
});

test("family view merges accounts sorted by due date, labelled per person", () => {
  const hass = makeHass([
    ["Lena", "alzey", [item("Spaeter", "2026-11-20", 12)]],
    ["Max", "alzey", [item("Frueher", "2026-11-09", 1, { renewable: true })]],
  ]);
  const html = render({ entity: "sensor.lena_loans", entities: ["sensor.max_loans"], group_by: "none" }, hass)
    .shadowRoot.innerHTML;
  assert.match(html, /class="title">Lena, Max</);
  assert.ok(html.indexOf("Frueher") < html.indexOf("Spaeter"));
  assert.match(html, /<span class="owner">Max<\/span>/);
  assert.match(html, /data-entry="entry_max" data-mednr="Frueher"/);
  assert.match(html, /2 Ausleihen/);
  // Same library: hours, announcement and data date once, without a library name.
  assert.equal(count(html, 'class="hours"'), 1);
  assert.equal(count(html, "Mitteilung alzey"), 1);
  assert.equal(count(html, "Datenstand der Bücherei"), 1);
  assert.doesNotMatch(html, /alzey: /);
});

test("family view names the library when accounts use different ones", () => {
  const hass = makeHass([
    ["Lena", "alzey", [item("A", "2026-11-20", 12)]],
    ["Max", "bingen", [item("B", "2026-11-21", 13)]],
  ]);
  const html = render({ entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, hass).shadowRoot.innerHTML;
  assert.equal(count(html, 'class="hours"'), 2);
  assert.match(html, /alzey: Geöffnet bis 12:00/);
  assert.match(html, /bingen: Mitteilung bingen/);
  assert.match(html, /bingen: Datenstand/);
});

test("family view shows only library cards that expire soon, with the name", () => {
  const hass = makeHass([
    ["Lena", "alzey", [], 400],
    ["Max", "alzey", [], 10],
  ]);
  const html = render({ entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, hass).shadowRoot.innerHTML;
  assert.match(html, /Max: Ausweis gültig bis/);
  assert.doesNotMatch(html, /Lena: Ausweis/);
});

test("group by person", () => {
  const hass = makeHass([
    ["Lena", "alzey", [item("A", "2026-11-20", 12), item("B", "2026-11-25", 17)]],
    ["Max", "alzey", [item("C", "2026-11-09", 1)]],
  ]);
  const html = render({ entity: "sensor.lena_loans", entities: ["sensor.max_loans"], group_by: "account" }, hass)
    .shadowRoot.innerHTML;
  assert.ok(html.indexOf("Max · nächste Rückgabe") < html.indexOf("Lena · nächste Rückgabe"));
  assert.match(html, /2 Medien/);
});

test("renew all and sync press the buttons of every account involved", async () => {
  const hass = makeHass([
    ["Lena", "alzey", [item("A", "2026-11-20", 12, { renewable: true })]],
    ["Max", "alzey", [item("B", "2026-11-21", 13)]],
    ["Ida", "alzey", [item("C", "2026-11-22", 14, { renewable: true })]],
  ]);
  const card = render({ entity: "sensor.lena_loans", entities: ["sensor.max_loans", "sensor.ida_loans"] }, hass);
  assert.match(card.shadowRoot.innerHTML, /2 verlängern/);
  await card.shadowRoot.handlers.renew();
  await card.shadowRoot.handlers.sync();
  assert.deepEqual(hass.calls, [
    ["button", "press", { entity_id: ["button.lena_renew_all", "button.ida_renew_all"] }],
    ["button", "press", { entity_id: ["button.lena_sync", "button.max_sync", "button.ida_sync"] }],
  ]);
});

test("renewing one item uses that item's account", async () => {
  const hass = makeHass([
    ["Lena", "alzey", []],
    ["Max", "alzey", [item("B", "2026-11-21", 13, { renewable: true })]],
  ]);
  const card = render({ entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, hass);
  await card._renewOne("entry_max", "B");
  assert.deepEqual(hass.calls, [["findus_opac", "renew", { config_entry_id: "entry_max", media_ids: ["B"] }]]);
});

test("a missing family member is reported, the rest still renders", () => {
  const hass = makeHass([["Lena", "alzey", [item("A", "2026-11-20", 12)]]]);
  const html = render({ entity: "sensor.lena_loans", entities: ["sensor.gone_loans"] }, hass).shadowRoot.innerHTML;
  assert.match(html, /Entität sensor.gone_loans nicht gefunden/);
  assert.match(html, /class="name">A</);
});

test("config needs at least one loans sensor and entities as a list", () => {
  assert.throws(() => new Card().setConfig({}), /entity is required/);
  assert.throws(() => new Card().setConfig({ entity: "sensor.a", entities: "sensor.b" }), /must be a list/);
  assert.doesNotThrow(() => new Card().setConfig({ entities: ["sensor.a"] }));
});
