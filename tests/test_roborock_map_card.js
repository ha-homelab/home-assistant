"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../config/www/roborock-map-card.js"), "utf8");

class FakeElement {
  constructor() { this.children = []; this.listeners = {}; this.attributes = {}; }
  attachShadow() { this.shadowRoot = new FakeElement(); return this.shadowRoot; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function fixture() {
  return {
    states: {
      "vacuum.test_robot": {state: "docked", attributes: {supported_features: 30524}},
      "image.test_robot": {state: "2026-01-01T00:00:00Z", attributes: {
        entity_picture: "/api/image_proxy/image.test_robot?token=PRIVATE_TEST_TOKEN",
        calibration_points: [
          {map: {x: 0, y: 0}, vacuum: {x: 1000, y: 1000}},
          {map: {x: 100, y: 0}, vacuum: {x: 2000, y: 1000}},
          {map: {x: 0, y: 100}, vacuum: {x: 1000, y: 2000}},
        ],
        rooms: {18: {number: 18, name: "Example", x0: 1000, y0: 1000,
          x1: 2000, y1: 2000, pos_x: null, pos_y: null},
          7: {number: 7, name: "Unknown", x0: 0, y0: 0, x1: 10, y1: 10}},
      }},
    },
    callService() { throw new Error("No test may send a device command"); },
  };
}
const config = {entity: "vacuum.test_robot", map_entity: "image.test_robot", room_ids: [18]};
function harness(loadHelpers, mapRegistered = true) {
  const registry = new Map(), definitions = new Map(), created = [], clock = {now: 0};
  if (mapRegistered) registry.set("xiaomi-vacuum-map-card", class {});
  const customElements = {
    get: name => registry.get(name),
    define: (name, value) => {registry.set(name, value); definitions.get(name)?.resolve();},
    whenDefined: name => {
      if (registry.has(name)) return Promise.resolve();
      if (!definitions.has(name)) definitions.set(name, deferred());
      return definitions.get(name).promise;
    },
  };
  const helpers = {createCardElement(configuration) {
    const child = new FakeElement();
    child.config = configuration;
    child.assignments = 0;
    Object.defineProperty(child, "hass", {get() {return this.latestHass;}, set(value) {
      this.latestHass = value; this.lastHassUpdate = clock.now; this.assignments++;
    }});
    created.push(child);
    return child;
  }};
  const context = vm.createContext({HTMLElement: FakeElement, setTimeout, clearTimeout,
    document: {createElement() {return new FakeElement();}},
    window: {loadCardHelpers: loadHelpers || (() => Promise.resolve(helpers))},
    customElements});
  vm.runInContext(source, context);
  const card = new (registry.get("homelab-roborock-map-card"))();
  return {card, helpers, created, context, clock, customElements};
}
const image = hass => hass.states[config.map_entity];

test("all hass updates reach one child beyond six minutes without clearing selection", async () => {
  const {card, created, clock} = harness();
  card.setConfig(config);
  card.hass = fixture();
  await flush();
  const child = card._child;
  child.selection = ["user zone"];
  const updates = [fixture(), fixture(), fixture()];
  updates[0].states[config.entity].state = "cleaning";
  image(updates[1]).state = "2026-01-01T00:20:00Z";
  image(updates[1]).attributes.entity_picture = "/api/image_proxy/image.test_robot?token=ROTATED";
  image(updates[2]).attributes.unused_attribute = "irrelevant";
  for (const update of updates) {
    clock.now += 7 * 60 * 1000;
    card.hass = update;
    assert.equal(card._child, child);
    assert.equal(child.hass, update);
    assert.equal(child.lastHassUpdate, clock.now);
    assert.deepEqual(child.selection, ["user zone"]);
  }
  card.setConfig({...config});
  assert.equal(card._child, child);
  assert.equal(created.length, 1);
  assert.equal(child.assignments, 5);
});

test("geometry, calibration and source changes replace stale selectable metadata", async () => {
  const {card, created} = harness();
  card.setConfig(config); card.hass = fixture(); await flush();
  let before = card._child;
  const moved = fixture(); image(moved).attributes.rooms[18].x1 = 3000;
  card.hass = moved;
  assert.equal(card._child, null);
  assert.ok(!card._host.children.includes(before));
  await flush();
  assert.notEqual(card._child, before);
  assert.equal(card._child.config.map_modes[0].predefined_selections[0].outline[1][0], 3000);
  before = card._child;
  image(moved).attributes.calibration_points[1].map.x = 110;
  card.hass = moved; await flush();
  assert.notEqual(card._child, before);
  const switched = fixture(); switched.states["image.second_map"] = image(switched);
  card.hass = switched; await flush();
  before = card._child;
  card.setConfig({...config, map_entity: "image.second_map"}); await flush();
  assert.notEqual(card._child, before);
  assert.equal(card._child.config.map_source.camera, "image.second_map");
  assert.equal(created.length, 5);
});

test("missing data removes the command-capable child immediately and recovery recreates it", async () => {
  const {card} = harness(); card.setConfig(config); card.hass = fixture(); await flush();
  const before = card._child;
  const invalid = fixture(); delete image(invalid).attributes.rooms[18];
  card.hass = invalid;
  assert.equal(card._child, null);
  assert.ok(!card._host.children.includes(before));
  card.hass = fixture(); await flush();
  assert.ok(card._child); assert.notEqual(card._child, before);
});

test("delayed helper load uses only latest configuration and latest hass", async () => {
  const pending = deferred();
  const {card, helpers, created} = harness(() => pending.promise);
  card.setConfig(config); card.hass = fixture();
  const latest = fixture(); image(latest).attributes.rooms[18].name = "Newest";
  card.hass = latest;
  pending.resolve(helpers); await flush();
  assert.equal(created.length, 1);
  assert.equal(card._child.hass, latest);
  assert.equal(card._child.config.map_modes[0].predefined_selections[0].label.text, "Newest");
});

test("an obsolete asynchronous child can never replace new or invalid data", async () => {
  const pending = deferred(); let calls = 0;
  const {card, helpers} = harness(() => Promise.resolve({createCardElement(configuration) {
    calls++;
    return calls === 1 ? pending.promise : helpers.createCardElement(configuration);
  }}));
  card.setConfig(config); card.hass = fixture(); await flush();
  const latest = fixture(); image(latest).attributes.rooms[18].name = "Current";
  card.hass = latest; await flush();
  const current = card._child;
  pending.resolve(new FakeElement()); await flush();
  assert.equal(card._child, current);
  const invalid = fixture(); delete image(invalid).attributes.entity_picture;
  card.hass = invalid;
  assert.equal(card._child, null);
  assert.equal(calls, 2);
});

test("invalidity while helpers load prevents a late command-capable mount", async () => {
  const pending = deferred(); const {card, helpers, created} = harness(() => pending.promise);
  card.setConfig(config); card.hass = fixture();
  const invalid = fixture(); image(invalid).state = "unavailable"; card.hass = invalid;
  pending.resolve(helpers); await flush();
  assert.equal(card._child, null); assert.equal(created.length, 0);
});

test("configuration is whitelisted and map actions require explicit Run", async () => {
  const {card} = harness();
  for (const invalid of [{...config, room_ids: []}, {...config, room_ids: [18, 18]},
    {...config, room_ids: [true]}, {...config, map_entity: "camera.example"}]) {
    assert.throws(() => card.setConfig(invalid));
  }
  card.setConfig({...config, activate: {service: "evil"}, run_immediately: true});
  card.hass = fixture(); await flush();
  const inner = card._child.config;
  assert.equal(inner.calibration_source.camera, true);
  assert.equal(inner.icons.length, 0); assert.equal(inner.tiles.length, 0);
  assert.equal(inner.map_modes.length, 3);
  assert.ok(inner.map_modes.every(mode => mode.run_immediately === false));
  assert.equal(inner.map_modes[0].predefined_selections.length, 1);
  assert.equal(inner.map_modes[0].predefined_selections[0].id, 18);
  assert.equal(inner.activate, undefined);
  assert.ok(!JSON.stringify(inner).includes("PRIVATE_TEST_TOKEN"));
});

test("helper errors are sanitized and explicit retry recovers", async () => {
  let attempt = 0;
  const {card, helpers} = harness(() => ++attempt === 1
    ? Promise.reject(new Error("PRIVATE_ERROR_DETAILS")) : Promise.resolve(helpers));
  card.setConfig(config); card.hass = fixture(); await flush();
  assert.equal(card._child, null);
  const message = card._host.children[0];
  assert.ok(!message.children[0].textContent.includes("PRIVATE_ERROR_DETAILS"));
  message.children[1].listeners.click(); await flush();
  assert.ok(card._child); assert.equal(attempt, 2);
});

test("resource loading order waits for the actual map element and keeps newest metadata", async () => {
  const {card, created, customElements} = harness(undefined, false);
  card.setConfig(config); card.hass = fixture(); await flush();
  assert.equal(created.length, 0);
  const latest = fixture(); image(latest).attributes.rooms[18].name = "Loaded last";
  card.hass = latest;
  customElements.define("xiaomi-vacuum-map-card", class {}); await flush();
  assert.equal(created.length, 1);
  assert.equal(card._child.config.map_modes[0].predefined_selections[0].label.text, "Loaded last");
});

test("room name overrides remain literal strings across geometry refreshes", async () => {
  const {card, context} = harness();
  const label = '${globalThis.injected = true}<img src=x onerror="globalThis.injected=true">';
  card.setConfig({...config, room_names: {18: label}});
  card.hass = fixture(); await flush();
  assert.equal(card._child.config.map_modes[0].predefined_selections[0].label.text, label);
  assert.equal(context.injected, undefined);
  const before = card._child;
  const moved = fixture(); image(moved).attributes.rooms[18].x1 = 3000;
  card.hass = moved; await flush();
  assert.notEqual(card._child, before);
  assert.equal(card._child.config.map_modes[0].predefined_selections[0].label.text, label);
  assert.equal(context.injected, undefined);
  const invalid = fixture(); delete image(invalid).attributes.rooms[18];
  card.hass = invalid;
  assert.equal(card._child, null);
});

test("room name overrides reject unknown IDs, invalid shapes and unbounded labels", () => {
  const {card} = harness();
  for (const room_names of [null, [], {7: "Unselected"}, {"018": "Noncanonical"},
    {18: " "}, {18: "x".repeat(129)}, {18: 12}, {18: {html: "No"}}]) {
    assert.throws(() => card.setConfig({...config, room_names}), /Room names/);
  }
  const names = {18: "  Safe label  "};
  card.setConfig({...config, room_names: names});
  assert.equal(card._config.room_names[18], "Safe label");
  names[18] = "Mutated input";
  assert.equal(card._config.room_names[18], "Safe label");
});
