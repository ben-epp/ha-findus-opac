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
const ActionCard = defined["findus-opac-action-card"];
const ReturnCard = defined["findus-opac-return-card"];
const LibraryCard = defined["findus-opac-library-card"];
const ChipCard = defined["findus-opac-chip-card"];

const item = (title, due, days_left, extra = {}) => ({
  title, due, days_left, category: "book", media_type: "Buch", mednr: title, renewable: false, ...extra,
});

/** A local calendar date n days from today, as the sensors report it. */
const day = (n) => {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** A hass object with one device per account: [name, library, items, cardDays, cardSoon, open]. */
function makeHass(accounts) {
  const hass = { states: {}, entities: {}, devices: {}, locale: { language: "de" }, calls: [] };
  hass.callService = async (domain, service, data) => hass.calls.push([domain, service, data]);
  const add = (id, device, key, state, attributes = {}) => {
    hass.entities[id] = { entity_id: id, device_id: device, platform: "findus_opac", translation_key: key };
    hass.states[id] = { entity_id: id, state, attributes, last_updated: "x" };
  };
  for (const [name, library, items, cardDays = 400, cardSoon, open] of accounts) {
    const slug = name.toLowerCase();
    const device = `dev_${slug}`;
    hass.devices[device] = { name, model: library, primary_config_entry: `entry_${slug}` };
    add(`sensor.${slug}_loans`, device, "loans", String(items.length), { items });
    add(`button.${slug}_renew_all`, device, "renew_all", "unknown");
    add(`button.${slug}_sync`, device, "sync", "unknown");
    add(`sensor.${slug}_card`, device, "card_valid_until", "2027-01-01", { days_left: cardDays });
    add(`binary_sensor.${slug}_card_expires_soon`, device, "card_expires_soon",
      cardSoon ?? (cardDays <= 30 ? "on" : "off"));
    add(`sensor.${slug}_last_sync`, device, "last_sync", new Date().toISOString());
    add(`binary_sensor.${slug}_open`, device, "open_now", open?.state ?? "on",
      open?.attributes ?? { hours: { mon: ["09:00-12:00"] }, closes_at: "12:00" });
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

function renderWith(CardClass, config, hass) {
  const card = new CardClass();
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

test("card expiry takes its colour from the card_expires_soon binary sensor", () => {
  const on = makeHass([["Lena", "alzey", [], 100, "on"]]);
  const soonHtml = render({ entity: "sensor.lena_loans" }, on).shadowRoot.innerHTML;
  assert.match(soonHtml, /class="cardline soon"/);

  const off = makeHass([["Lena", "alzey", [], 5, "off"]]);
  const ok = render({ entity: "sensor.lena_loans" }, off).shadowRoot.innerHTML;
  assert.match(ok, /class="cardline ok"/);
  assert.doesNotMatch(ok, /class="cardline soon"/);
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

test("a pending request shows the day it was sent, without a renew button", () => {
  const hass = makeHass([
    ["Lena", "alzey", [item("A", "2026-11-12", 3, { renew_requested: true, renew_requested_on: "2026-11-09" })]],
  ]);
  const html = render({ entity: "sensor.lena_loans" }, hass).shadowRoot.innerHTML;
  assert.match(html, /Verlängerung beantragt am 9\.11\./);
  assert.doesNotMatch(html, /class="icon-btn item-renew"/);
});

// ---- action card ----

test("action card lists only overdue, today and soon, sorted by due date", () => {
  const hass = makeHass([
    ["Lena", "alzey", [
      item("Spaeter", "2026-11-20", 8, { status: "later" }),
      item("Heute", "2026-11-12", 0, { status: "today" }),
      item("Frueher", "2026-11-10", -2, { status: "overdue" }),
      item("Bald", "2026-11-14", 2, { status: "soon" }),
    ]],
  ]);
  const html = renderWith(ActionCard, { entity: "sensor.lena_loans" }, hass).shadowRoot.innerHTML;
  assert.doesNotMatch(html, /Spaeter/);
  assert.ok(html.indexOf("Frueher") < html.indexOf("Heute"));
  assert.ok(html.indexOf("Heute") < html.indexOf("Bald"));
  assert.match(html, /class="row overdue"/);
  assert.match(html, /class="row soon"/);
});

test("action card shows a line with a check icon when nothing is due", () => {
  const hass = makeHass([["Lena", "alzey", [item("Spaeter", "2026-11-20", 8, { status: "later" })]]]);
  const html = renderWith(ActionCard, { entity: "sensor.lena_loans" }, hass).shadowRoot.innerHTML;
  assert.match(html, /mdi:check-circle-outline/);
  assert.match(html, /Nichts zu erledigen/);
});

test("action card renews an item through that item's account", async () => {
  const hass = makeHass([
    ["Lena", "alzey", [item("Bald", "2026-11-14", 2, { status: "soon", renewable: true })]],
    ["Max", "alzey", [item("Frueh", "2026-11-10", -2, { status: "overdue", renewable: true, mednr: "M-7" })]],
  ]);
  const card = renderWith(ActionCard, { entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, hass);
  assert.match(card.shadowRoot.innerHTML, /data-entry="entry_max" data-mednr="M-7"/);
  await card._renewOne("entry_max", "M-7");
  assert.deepEqual(hass.calls, [["findus_opac", "renew", { config_entry_id: "entry_max", media_ids: ["M-7"] }]]);
});

test("action card names the owner only in the family view", () => {
  const single = makeHass([["Lena", "alzey", [item("Bald", "2026-11-14", 2, { status: "soon" })]]]);
  const one = renderWith(ActionCard, { entity: "sensor.lena_loans" }, single).shadowRoot.innerHTML;
  assert.doesNotMatch(one, /class="owner"/);

  const family = makeHass([
    ["Lena", "alzey", [item("Bald", "2026-11-14", 2, { status: "soon" })]],
    ["Max", "alzey", [item("Frueh", "2026-11-10", -2, { status: "overdue" })]],
  ]);
  const two = renderWith(
    ActionCard, { entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, family,
  ).shadowRoot.innerHTML;
  assert.match(two, /<span class="owner">Lena<\/span>/);
  assert.match(two, /<span class="owner">Max<\/span>/);
});

// ---- return card ----

test("return window starts today when open and ends at the following open day", () => {
  const open = { hours: { monday: ["09:00-12:00"], wednesday: ["09:00-12:00"] }, conditional_days: [] };
  // Monday 2026-11-09, in the morning.
  assert.deepEqual(returnWindow(open, "on", new Date(2026, 10, 9, 10)), {
    o1: "2026-11-09", o2: "2026-11-11",
  });
});

test("return window starts at next_open when the library is closed", () => {
  const open = {
    hours: { tuesday: ["09:00-12:00"], thursday: ["09:00-12:00"] },
    next_open: "2026-11-10T09:00:00",
    conditional_days: [],
  };
  // Monday evening: open tomorrow and again on Thursday.
  assert.deepEqual(returnWindow(open, "off", new Date(2026, 10, 9, 18)), {
    o1: "2026-11-10", o2: "2026-11-12",
  });
});

test("return window skips the weekend", () => {
  const open = {
    hours: { monday: ["09:00-12:00"], wednesday: ["09:00-12:00"], friday: ["09:00-12:00"] },
    next_open: "2026-11-16T09:00:00",
    conditional_days: [],
  };
  // Saturday 2026-11-14: next opening Monday, the one after that Wednesday.
  assert.deepEqual(returnWindow(open, "off", new Date(2026, 10, 14, 12)), {
    o1: "2026-11-16", o2: "2026-11-18",
  });
});

test("return window counts a conditional day as open", () => {
  const open = {
    hours: { monday: ["09:00-12:00"] },
    next_open: "2026-11-16T09:00:00",
    conditional_days: ["tuesday"],
  };
  // Sunday evening: Monday is the next opening, Tuesday is conditional without hours.
  assert.deepEqual(returnWindow(open, "off", new Date(2026, 10, 15, 18)), {
    o1: "2026-11-16", o2: "2026-11-17",
  });
});

test("return window is null without usable hours", () => {
  assert.equal(returnWindow(undefined, "on", new Date(2026, 10, 9, 10)), null);
  assert.equal(returnWindow({}, "unavailable", new Date(2026, 10, 9, 10)), null);
});

test("return card lists loans due before the following opening", () => {
  const weekdays = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
  const hours = Object.fromEntries(weekdays.map((d) => [d, ["09:00-18:00"]]));
  const open = { state: "on", attributes: { hours, conditional_days: [], closes_at: "18:00" } };
  const hass = makeHass([
    ["Lena", "alzey", [
      item("Mitnehmen", day(0), 0, { status: "today" }),
      item("Verlaengerbar", day(0), 0, { status: "today", renewable: true }),
      item("Beantragt", day(0), 0, { status: "today", renew_requested: true }),
      item("Spaeter", day(1), 1, { status: "soon" }),
      item("Ueberfaellig", day(-2), -2, { status: "overdue", renewable: true }),
    ], 400, undefined, open],
  ]);
  const html = renderWith(ReturnCard, { entity: "sensor.lena_loans" }, hass).shadowRoot.innerHTML;
  assert.match(html, /Mitnehmen/);
  assert.match(html, /Ueberfaellig/);
  assert.doesNotMatch(html, /Verlaengerbar/);
  assert.doesNotMatch(html, /Beantragt/);
  assert.doesNotMatch(html, /Spaeter/);
});

test("return card falls back to the due status without hours", () => {
  const open = { state: "unavailable", attributes: {} };
  const hass = makeHass([
    ["Lena", "alzey", [
      item("Heute", day(0), 0, { status: "today" }),
      item("HeuteVerlaengerbar", day(0), 0, { status: "today", renewable: true }),
      item("Bald", day(2), 2, { status: "soon" }),
      item("Spaeter", day(9), 9, { status: "later" }),
    ], 400, undefined, open],
  ]);
  const html = renderWith(ReturnCard, { entity: "sensor.lena_loans" }, hass).shadowRoot.innerHTML;
  assert.match(html, /Heute</);
  assert.match(html, /Bald/);
  assert.doesNotMatch(html, /HeuteVerlaengerbar/);
  assert.doesNotMatch(html, /Spaeter/);
  assert.match(html, /Nichts zurückzubringen|class="row/); // card still renders
});

// ---- library card ----

test("library card shows one block per library", () => {
  const same = makeHass([
    ["Lena", "alzey", []],
    ["Max", "alzey", []],
  ]);
  const one = renderWith(
    LibraryCard, { entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, same,
  ).shadowRoot.innerHTML;
  assert.equal(count(one, 'class="libblock"'), 1);
  assert.doesNotMatch(one, /alzey: /);
  assert.match(one, /Geöffnet bis 12:00/);
  assert.match(one, /class="hweek"/); // hours are always expanded
  assert.doesNotMatch(one, /hours-toggle/);

  const different = makeHass([
    ["Lena", "alzey", []],
    ["Max", "bingen", []],
  ]);
  const two = renderWith(
    LibraryCard, { entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, different,
  ).shadowRoot.innerHTML;
  assert.equal(count(two, 'class="libblock"'), 2);
  assert.match(two, /alzey: Geöffnet bis 12:00/);
  assert.match(two, /bingen: Geöffnet bis 12:00/);
});

test("library card shows card expiry only when soon or expired", () => {
  const ok = makeHass([["Lena", "alzey", [], 100, "off"]]);
  assert.doesNotMatch(
    renderWith(LibraryCard, { entity: "sensor.lena_loans" }, ok).shadowRoot.innerHTML, /Ausweis/,
  );

  const soon = makeHass([["Lena", "alzey", [], 10, "on"]]);
  assert.match(
    renderWith(LibraryCard, { entity: "sensor.lena_loans" }, soon).shadowRoot.innerHTML,
    /Ausweis gültig bis/,
  );

  const expired = makeHass([["Lena", "alzey", [], -3, "on"]]);
  assert.match(
    renderWith(LibraryCard, { entity: "sensor.lena_loans" }, expired).shadowRoot.innerHTML,
    /Ausweis abgelaufen seit/,
  );
});

// ---- summary card ----

test("summary card totals loans and badges across accounts", () => {
  const hass = makeHass([
    ["Lena", "alzey", [
      item("A", day(0), 0, { status: "today" }),
      item("B", day(5), 5, { status: "later" }),
    ]],
    ["Max", "alzey", [
      item("C", day(-2), -2, { status: "overdue" }),
      item("D", day(2), 2, { status: "soon", renewable: true }),
    ]],
  ]);
  const html = renderWith(
    ChipCard, { entity: "sensor.lena_loans", entities: ["sensor.max_loans"] }, hass,
  ).shadowRoot.innerHTML;
  assert.match(html, /4 Medien/);
  assert.match(html, /nächste Rückgabe/);
  assert.match(html, /1 überfällig/);
  assert.match(html, /2 bald fällig/);
  assert.doesNotMatch(html, /<button|verlängerbar/);
});

test("summary card opens the first loans sensor on tap", () => {
  const hass = makeHass([["Lena", "alzey", [item("A", day(0), 0, { status: "today" })]]]);
  const card = renderWith(ChipCard, { entity: "sensor.lena_loans" }, hass);
  const events = [];
  card.dispatchEvent = (ev) => events.push(ev);
  card.shadowRoot.handlers.chiprow();
  assert.equal(events.length, 1);
  assert.equal(events[0].type, "hass-more-info");
  assert.equal(events[0].detail.entityId, "sensor.lena_loans");
});

test("every compact card needs a loans sensor", () => {
  for (const CardClass of [ActionCard, ReturnCard, LibraryCard, ChipCard]) {
    assert.throws(() => new CardClass().setConfig({}), /entity is required/);
    assert.doesNotThrow(() => new CardClass().setConfig({ entity: "sensor.a" }));
  }
});
