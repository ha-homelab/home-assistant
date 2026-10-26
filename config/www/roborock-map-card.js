/* Dynamic Roborock room controls for Xiaomi Vacuum Map Card 2.4.1.
 * No templates, credentials, storage, network calls, or automatic commands.
 */
function validatedRoomNames(value, allowed) {
  if (!value || typeof value !== "object" || Array.isArray(value) || !Array.isArray(allowed)) return null;
  const names = {};
  for (const [id, label] of Object.entries(value)) {
    if (!/^(0|[1-9][0-9]*)$/.test(id) || !allowed.includes(Number(id))
      || typeof label !== "string" || !label.trim() || label.length > 128) return null;
    names[id] = label.trim();
  }
  return names;
}

function projectRoborockMap(entity, allowed, roomNames = {}) {
  const fail = {valid: false, rooms: []};
  const names = validatedRoomNames(roomNames, allowed);
  if (!names) return fail;
  const point = p => Array.isArray(p) && p.length === 2 && p.every(
    n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 10000000);
  const area = p => p.reduce((s, a, i) => {
    const b = p[(i + 1) % p.length]; return s + a[0] * b[1] - b[0] * a[1];
  }, 0);
  if (!entity || typeof entity.state !== 'string'
    || ['unavailable', 'unknown'].includes(entity.state)) return fail;
  const a = entity.attributes || {}, c = a.calibration_points, rooms = a.rooms;
  if (typeof a.entity_picture !== 'string' || !a.entity_picture.trim()) return fail;
  if (!Array.isArray(c) || ![3, 4].includes(c.length)) return fail;
  for (const kind of ['map', 'vacuum']) {
    const p = c.map(v => [v?.[kind]?.x, v?.[kind]?.y]);
    if (!p.every(point)) return fail;
    for (let i = 0; i < p.length; i++) for (let j = i + 1; j < p.length; j++)
      for (let k = j + 1; k < p.length; k++)
        if (Math.abs(area([p[i], p[j], p[k]])) < 1e-9) return fail;
  }
  if (!rooms || Array.isArray(rooms) || typeof rooms !== 'object') return fail;
  let ids = Object.keys(rooms);
  if (!ids.length || ids.length > 256) return fail;
  if (!Array.isArray(allowed) || !allowed.length
    || !allowed.every(id => Number.isInteger(id) && id >= 0 && id <= 65535)
    || new Set(allowed).size !== allowed.length
    || !allowed.every(id => Object.hasOwn(rooms, String(id)))) return fail;
  ids = allowed.map(String);
  const selections = [];
  for (const key of ids.sort((a, b) => Number(a) - Number(b))) {
    if (!/^(0|[1-9][0-9]*)$/.test(key) || Number(key) > 65535) return fail;
    const id = Number(key), room = rooms[key];
    if (!room || Array.isArray(room) || typeof room !== 'object') return fail;
    if (room.number !== undefined && room.number !== id) return fail;
    const outline = room.outline ?? [
      [room.x0, room.y0], [room.x1, room.y0],
      [room.x1, room.y1], [room.x0, room.y1]];
    if (!Array.isArray(outline) || outline.length < 3 || outline.length > 2048
      || !outline.every(point) || Math.abs(area(outline)) < 1e-9) return fail;
    let center = [room.x, room.y];
    if (room.x === undefined && room.y === undefined) center = [room.pos_x, room.pos_y];
    if (center.every(n => n == null)) center = [0, 1].map(
      n => outline.reduce((sum, p) => sum + p[n], 0) / outline.length);
    if (!point(center)) return fail;
    const name = room.name == null || (typeof room.name === 'string'
      && room.name.trim().toLowerCase() === 'unknown') ? `Room ${id}` : room.name;
    if (typeof name !== 'string' || !name.trim() || name.length > 128) return fail;
    selections.push({id, outline, default_state: 'unselected',
      // Label text is passed as a string to upstream's escaped SVG template.
      // It is never evaluated as a template, HTML, or JavaScript here.
      label: {text: names[key] ?? name.trim(), x: center[0], y: center[1], offset_y: 20},
      icon: {name: 'mdi:broom', x: center[0], y: center[1]}});
  }
  const calibration = c.map(v => ({
    map: {x: v.map.x, y: v.map.y}, vacuum: {x: v.vacuum.x, y: v.vacuum.y}}));
  return {valid: true, rooms: selections, calibration};
}

function roborockInnerConfig(config, data) {
  return {
    type: "custom:xiaomi-vacuum-map-card", entity: config.entity,
    vacuum_platform: "Roborock", map_source: {camera: config.map_entity},
    calibration_source: {camera: true}, map_locked: true, two_finger_pan: true,
    icons: [], tiles: [],
    map_modes: [
      {template: "vacuum_clean_segment", run_immediately: false, predefined_selections: data.rooms},
      {template: "vacuum_clean_zone", run_immediately: false},
      {template: "vacuum_goto", run_immediately: false},
    ],
  };
}

class HomelabRoborockMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    const style = document.createElement("style");
    style.textContent = ":host{display:block}ha-card{padding:20px;color:var(--primary-text-color)}button{font:inherit;margin-top:12px;padding:8px 16px;cursor:pointer}";
    this._host = document.createElement("div");
    this.shadowRoot.append(style, this._host);
    this._generation = 0;
    this._key = null;
    this._child = null;
    this._showMessage("Waiting for map data.");
  }

  setConfig(config) {
    if (!config || !/^vacuum\.[a-z0-9_]+$/.test(config.entity)
      || !/^image\.[a-z0-9_]+$/.test(config.map_entity)
      || !Array.isArray(config.room_ids) || !config.room_ids.length
      || !config.room_ids.every(id => Number.isInteger(id) && id >= 0 && id <= 65535)
      || new Set(config.room_ids).size !== config.room_ids.length) {
      throw new Error("Choose a vacuum, an image map, and unique verified current-map segment IDs.");
    }
    const names = validatedRoomNames(config.room_names === undefined ? {} : config.room_names, config.room_ids);
    if (!names) throw new Error("Room names must map allowed segment IDs to nonblank strings up to 128 characters.");
    // Whitelist the supported fields. Extra input can never introduce actions.
    this._config = {entity: config.entity, map_entity: config.map_entity,
      room_ids: [...config.room_ids].sort((a, b) => a - b)};
    if (Object.keys(names).length) this._config.room_names = names;
    this._refresh();
  }

  set hass(hass) {
    this._hass = hass;
    this._refresh();
  }

  get hass() { return this._hass; }
  getCardSize() { return this._child?.getCardSize?.() ?? 12; }
  getGridOptions() { return {columns: "full", rows: "auto"}; }

  _showMessage(message, retry = false) {
    const card = document.createElement("ha-card");
    const text = document.createElement("div");
    text.textContent = message;
    text.setAttribute("role", "status");
    card.append(text);
    if (retry) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Retry loading map";
      button.addEventListener("click", () => {this._key = null; this._refresh();});
      card.append(button);
    }
    this._host.replaceChildren(card);
  }

  _refresh() {
    if (!this._config || !this._hass) return;
    const data = projectRoborockMap(this._hass.states?.[this._config.map_entity],
      this._config.room_ids, this._config.room_names);
    // No timestamp or token-bearing URL in the key: normal image refreshes and
    // unrelated HA updates must preserve selections. Source entity identity,
    // calibration, and approved room geometry/labels define a new selection.
    const key = data.valid ? JSON.stringify([this._config, data.calibration, data.rooms]) : "invalid";
    if (key === this._key) {
      // Xiaomi's six-minute connection timer depends on every hass assignment,
      // including updates where the map and vacuum themselves are unchanged.
      if (this._child) this._child.hass = this._hass;
      return;
    }
    this._key = key;
    const generation = ++this._generation;
    this._child = null;
    if (!data.valid) {
      this._showMessage("Map data unavailable. Wait for the selected map and its room metadata to load.");
      return;
    }
    this._showMessage("Loading interactive map…");
    this._mount(roborockInnerConfig(this._config, data), generation);
  }

  async _mount(config, generation) {
    try {
      if (!this._helpers) {
        this._helpers = Promise.resolve().then(async () => {
          const helpers = await window.loadCardHelpers();
          // Resources may execute in either order. Do not mistake HA's
          // temporary "custom element does not exist" card for a ready map.
          if (!customElements.get("xiaomi-vacuum-map-card")) {
            await new Promise((resolve, reject) => {
              const timer = setTimeout(() => reject(new Error("Map card dependency unavailable")), 10000);
              customElements.whenDefined("xiaomi-vacuum-map-card").then(() => {
                clearTimeout(timer);
                resolve();
              });
            });
          }
          return helpers;
        });
        this._helpers.catch(() => {this._helpers = null;});
      }
      const helpers = await this._helpers;
      if (generation !== this._generation) return;
      const child = await helpers.createCardElement(config);
      if (generation !== this._generation) return;
      child.hass = this._hass;
      this._child = child;
      this._host.replaceChildren(child);
    } catch (_) {
      if (generation !== this._generation) return;
      this._child = null;
      this._showMessage("Interactive map could not load. Check that Xiaomi Vacuum Map Card is installed.", true);
    }
  }
}

if (!customElements.get("homelab-roborock-map-card")) {
  customElements.define("homelab-roborock-map-card", HomelabRoborockMapCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "homelab-roborock-map-card")) {
  window.customCards.push({type: "homelab-roborock-map-card", name: "Roborock dynamic map", preview: false,
    description: "Validated dynamic room and zone controls with live Home Assistant updates."});
}
