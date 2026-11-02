/* A local, capability-aware radio controller. Configuration stays in Lovelace. */
(() => {
  "use strict";
  const FEATURES = { VOLUME_SET: 4, PLAY_MEDIA: 512, SELECT_SOURCE: 2048, STOP: 4096 };
  const OFFLINE = new Set(["unknown", "unavailable"]);
  const text = (value) => typeof value === "string" && value.trim().length > 0;
  const available = (state) => !!state && !OFFLINE.has(state.state);
  const has = (state, feature) => (Number(state?.attributes?.supported_features || 0) & feature) !== 0;

  function streamUrl(value) {
    if (!text(value)) throw new Error("Enter a direct audio stream URL.");
    let url;
    try { url = new URL(value.trim()); } catch (_) { throw new Error("Use a valid HTTP or HTTPS audio URL."); }
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password) {
      throw new Error("Use an HTTP or HTTPS audio URL without embedded credentials.");
    }
    return url.href;
  }

  function normalizeConfig(raw) {
    if (!raw || !Array.isArray(raw.players) || !raw.players.length) throw new Error("Configure at least one player.");
    const players = raw.players.map((p) => {
      if (!/^media_player\.[a-z0-9_]+$/.test(p.entity || "") || !text(p.name)) throw new Error("Each player needs an entity and name.");
      return { entity: p.entity, name: p.name, icon: p.icon || "mdi:speaker" };
    });
    const ids = new Set(players.map((p) => p.entity));
    if (ids.size !== players.length) throw new Error("Player entities must be unique.");
    const stations = (raw.stations || []).map((s) => {
      if (!text(s.id) || !text(s.name)) throw new Error("Each station needs a unique ID and name.");
      const sources = { ...(s.sources || {}) };
      for (const [entity, source] of Object.entries(sources)) {
        if (!ids.has(entity) || !text(source)) throw new Error("Station sources must reference configured players.");
      }
      return { id: s.id, name: s.name, url: s.url ? streamUrl(s.url) : null, sources };
    });
    if (new Set(stations.map((s) => s.id)).size !== stations.length) throw new Error("Station IDs must be unique.");
    const groups = (raw.groups || []).map((g) => {
      if (!text(g.name) || !Array.isArray(g.entities) || !g.entities.length || g.entities.some((e) => !ids.has(e))) {
        throw new Error("Groups must contain configured players.");
      }
      return { name: g.name, entities: [...new Set(g.entities)] };
    });
    const limits = (raw.limits || []).map((limit) => {
      if (!Number.isInteger(limit.max) || limit.max < 1 || !Array.isArray(limit.entities)
          || limit.entities.some((e) => !ids.has(e))) throw new Error("Invalid player capacity limit.");
      return { name: limit.name || "Phone playback", max: limit.max, entities: [...new Set(limit.entities)] };
    });
    return { title: raw.title || "Radio & speakers", players, stations, groups, limits };
  }

  function planDispatch(config, states, selected, request) {
    const plan = { calls: [], excluded: [], errors: [] };
    const players = new Map(config.players.map((p) => [p.entity, p]));
    const targets = [...new Set(selected)];
    if (!targets.length) plan.errors.push("Choose at least one speaker.");
    if (targets.some((e) => !players.has(e))) plan.errors.push("Selection contains an unconfigured speaker.");
    if (!["play", "stop", "volume"].includes(request.action)) plan.errors.push("Unsupported action.");
    let station, url;
    if (request.action === "play") {
      if (request.customUrl !== undefined) {
        try { url = streamUrl(request.customUrl); } catch (error) { plan.errors.push(error.message); }
      } else {
        station = config.stations.find((s) => s.id === request.stationId);
        if (!station) plan.errors.push("Choose a station.");
        else url = station.url;
      }
    }
    if (request.action === "volume" && (!Number.isFinite(request.volume) || request.volume < 0 || request.volume > 1)) {
      plan.errors.push("Volume must be between 0 and 100 percent.");
    }
    if (plan.errors.length) return plan;
    for (const entity of targets) {
      const player = players.get(entity), state = states[entity];
      const skip = (reason) => plan.excluded.push({ entity, name: player.name, reason });
      if (!available(state)) { skip("Offline — not sent"); continue; }
      let service, data = { entity_id: entity };
      if (request.action === "play") {
        const source = station?.sources[entity];
        if (source) {
          if (!has(state, FEATURES.SELECT_SOURCE) || !state.attributes?.source_list?.includes(source)) {
            skip("Station source is not currently available on this speaker"); continue;
          }
          service = "select_source"; data.source = source;
        } else {
          if (!has(state, FEATURES.PLAY_MEDIA) || !url) { skip("This speaker cannot play this stream"); continue; }
          service = "play_media";
          Object.assign(data, { media_content_id: url, media_content_type: "music",
            extra: { metadata: { title: station?.name || "Custom audio stream" } } });
        }
      } else if (request.action === "stop") {
        if (!has(state, FEATURES.STOP)) { skip("Stop is not supported by this speaker"); continue; }
        service = "media_stop";
      } else {
        if (!has(state, FEATURES.VOLUME_SET)) { skip("Volume adjustment is not supported by this speaker"); continue; }
        service = "volume_set"; data.volume_level = request.volume;
      }
      plan.calls.push({ entity, name: player.name, domain: "media_player", service, data });
    }
    if (request.action === "play") {
      for (const limit of config.limits) {
        const count = plan.calls.filter((call) => limit.entities.includes(call.entity)).length;
        if (count > limit.max) plan.errors.push(`${limit.name}: choose at most ${limit.max} available speakers (${count} selected). Nothing was sent.`);
      }
    }
    if (plan.errors.length) plan.calls = [];
    if (!plan.calls.length && !plan.errors.length) plan.errors.push("No selected speaker can receive this action.");
    return plan;
  }

  async function executePlan(hass, plan, report = () => {}) {
    if (plan.errors.length) return [];
    const results = [];
    const allowed = new Set(["select_source", "play_media", "media_stop", "volume_set"]);
    for (const call of plan.calls) {
      let result;
      if (call.domain !== "media_player" || !allowed.has(call.service) || call.data.entity_id !== call.entity) {
        result = { entity: call.entity, name: call.name, ok: false, message: "Unsupported request — not sent" };
      } else {
        try {
          await hass.callService(call.domain, call.service, call.data);
          result = { entity: call.entity, name: call.name, ok: true, message: "Sent" };
        } catch (_) {
          // Service errors may contain private URLs. Do not copy them to the DOM or console.
          result = { entity: call.entity, name: call.name, ok: false, message: "Request failed — check the speaker or Home Assistant" };
        }
      }
      results.push(result); report(result);
    }
    return results;
  }

  const CSS = `
    :host{display:block;min-width:0;color:var(--primary-text-color,#1c2738);font-family:var(--paper-font-body1_-_font-family,inherit)}
    ha-card{display:block;padding:22px;border-radius:20px;background:var(--ha-card-background,var(--card-background-color,#fff));overflow:hidden}
    h2{font-size:22px;line-height:1.25;margin:0 0 6px;font-weight:650}p{margin:0 0 16px;line-height:1.45;font-size:13px;color:var(--secondary-text-color,#596779)}
    .section{margin-top:20px}.label{display:block;font-size:13px;font-weight:600;margin-bottom:8px}.row,.tabs,.groups,.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
    button,input,select{font:inherit;color:var(--primary-text-color,#1c2738);box-sizing:border-box}button{cursor:pointer;border:1px solid var(--divider-color,#ced6e0);background:var(--secondary-background-color,#f2f5fa);border-radius:11px;padding:10px 12px;min-height:42px}button:hover:not(:disabled){border-color:var(--primary-color,#3975db)}
    button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--primary-color,#3975db);outline-offset:2px}button:disabled{cursor:default;opacity:.55}
    .tabs{margin-bottom:12px}.tabs button{flex:1}.tabs button[aria-pressed=true],.chip[aria-pressed=true]{border-color:var(--primary-color,#3975db);background:color-mix(in srgb,var(--primary-color,#3975db) 17%,var(--card-background-color,#fff))}
    input[type=search],input[type=url],select{width:100%;min-height:45px;border:1px solid var(--divider-color,#ced6e0);border-radius:11px;padding:10px 12px;background:var(--card-background-color,#fff);font-size:15px}select{margin-top:8px}input::placeholder{color:var(--secondary-text-color,#596779)}
    .groups{margin-bottom:10px}.groups button{font-size:12px;padding:7px 10px;min-height:34px}.players{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(190px,100%),1fr));gap:8px}
    .chip{display:flex;align-items:center;text-align:left;gap:8px;padding:11px 10px;min-width:0}.chip ha-icon{flex:0 0 24px;color:var(--secondary-text-color,#596779)}.chip[aria-pressed=true] ha-icon{color:var(--primary-color,#3975db)}.chip span{min-width:0}.name{font-size:13px;font-weight:600;overflow-wrap:anywhere;display:block}.state{font-size:11px;margin-top:3px;color:var(--secondary-text-color,#596779);display:block}.chip.offline .state{color:var(--warning-color,#956500)}
    .selection{margin:10px 0 0;font-size:12px}.actions button{flex:1;font-weight:600}.primary{background:var(--primary-color,#3975db);border-color:var(--primary-color,#3975db);color:var(--text-primary-color,#fff)}
    .volume{margin-top:14px;border-top:1px solid var(--divider-color,#ced6e0);padding-top:14px}.volume input{flex:1;min-width:70px;accent-color:var(--primary-color,#3975db)}.volume output{font-size:13px;min-width:40px}.volume button{font-size:12px}.results{list-style:none;margin:15px 0 0;padding:0;font-size:12px;line-height:1.5}.results li{padding:6px 0;border-top:1px solid var(--divider-color,#ced6e0)}.results .error{color:var(--error-color,#b71c1c)}.results .sent{color:var(--success-color,#2e7d32)}
    [hidden]{display:none!important}@media(max-width:360px){ha-card{padding:16px}.players{grid-template-columns:1fr}.actions button{flex-basis:100%}}
  `;

  const Base = typeof HTMLElement === "undefined" ? class {} : HTMLElement;
  class RadioConsoleCard extends Base {
    constructor() {
      super(); this.attachShadow({ mode: "open" }); this._selected = new Set(); this._mode = "station";
      this._stationId = ""; this._busy = false; this._volume = 35;
    }
    setConfig(config) {
      this._config = normalizeConfig(config); this._stationId = this._config.stations[0]?.id || "";
      this._selected = new Set(); this._render();
    }
    set hass(value) { this._hass = value; this._refreshState(); }
    getCardSize() { return 9; }
    getGridOptions() { return { columns: 12, min_columns: 6 }; }
    _el(tag, content, className) {
      const element = document.createElement(tag);
      if (content !== undefined) element.textContent = content;
      if (className) element.className = className;
      return element;
    }
    _button(label, action, className) {
      const b = this._el("button", label, className); b.type = "button"; b.addEventListener("click", action); return b;
    }
    _render() {
      if (!this._config) return;
      this.shadowRoot.replaceChildren();
      this.shadowRoot.append(this._el("style", CSS));
      const card = this._el("ha-card"); this.shadowRoot.append(card);
      card.append(this._el("h2", this._config.title), this._el("p", "Choose what to play and where. Mixed groups share playback; they are not synchronized."));
      const tabs = this._el("div", undefined, "tabs"); card.append(tabs);
      this._stationTab = this._button("Stations", () => this._setMode("station"));
      this._urlTab = this._button("Stream URL", () => this._setMode("url")); tabs.append(this._stationTab, this._urlTab);
      this._stationPanel = this._el("div"); card.append(this._stationPanel);
      this._search = this._el("input"); this._search.type = "search"; this._search.placeholder = "Find a station"; this._search.setAttribute("aria-label", "Find a station");
      this._search.addEventListener("input", () => this._stationOptions());
      this._stationSelect = this._el("select"); this._stationSelect.setAttribute("aria-label", "Station");
      this._stationSelect.addEventListener("change", () => { this._stationId = this._stationSelect.value; });
      this._stationPanel.append(this._search, this._stationSelect);
      this._urlPanel = this._el("div"); card.append(this._urlPanel);
      this._url = this._el("input"); this._url.type = "url"; this._url.placeholder = "https://…/audio.mp3"; this._url.setAttribute("aria-label", "Direct audio stream URL");
      this._urlPanel.append(this._url, this._el("p", "Direct HTTP(S) audio only. Speakers that only support preset stations will be skipped."));
      const targets = this._el("div", undefined, "section"); card.append(targets);
      targets.append(this._el("span", "Speakers", "label"));
      const groups = this._el("div", undefined, "groups"); targets.append(groups);
      groups.append(this._button("All available", () => {
        this._selected = new Set(this._config.players.filter((p) => available(this._hass?.states[p.entity])).map((p) => p.entity)); this._refreshState();
      }), this._button("Clear", () => { this._selected.clear(); this._refreshState(); }));
      for (const group of this._config.groups) groups.append(this._button(group.name, () => { this._selected = new Set(group.entities); this._refreshState(); }));
      this._chips = new Map(); const players = this._el("div", undefined, "players"); targets.append(players);
      for (const player of this._config.players) {
        const button = this._button("", () => {
          this._selected.has(player.entity) ? this._selected.delete(player.entity) : this._selected.add(player.entity); this._refreshState();
        }, "chip");
        const icon = this._el("ha-icon"); icon.setAttribute("icon", player.icon);
        const label = this._el("span"); const state = this._el("span", "", "state");
        label.append(this._el("span", player.name, "name"), state); button.append(icon, label);
        this._chips.set(player.entity, { button, state }); players.append(button);
      }
      this._selection = this._el("p", "", "selection"); targets.append(this._selection);
      const actions = this._el("div", undefined, "actions section"); card.append(actions);
      actions.append(this._button("Play selected", () => this._run("play"), "primary"), this._button("Stop selected", () => this._run("stop")));
      const volume = this._el("div", undefined, "row volume"); card.append(volume);
      const range = this._el("input"); range.type = "range"; range.min = "0"; range.max = "100"; range.value = String(this._volume); range.setAttribute("aria-label", "Volume to apply");
      const output = this._el("output", `${this._volume}%`); range.addEventListener("input", () => { this._volume = Number(range.value); output.textContent = `${this._volume}%`; });
      volume.append(range, output, this._button("Apply volume", () => this._run("volume")));
      this._results = this._el("ul", undefined, "results"); this._results.setAttribute("aria-live", "polite"); card.append(this._results);
      this._stationOptions(); this._setMode(this._mode); this._refreshState();
    }
    _setMode(mode) {
      this._mode = mode; this._stationPanel.hidden = mode !== "station"; this._urlPanel.hidden = mode !== "url";
      this._stationTab.setAttribute("aria-pressed", String(mode === "station")); this._urlTab.setAttribute("aria-pressed", String(mode === "url"));
    }
    _stationOptions() {
      const query = this._search.value.trim().toLocaleLowerCase();
      const stations = this._config.stations.filter((s) => s.name.toLocaleLowerCase().includes(query));
      if (!stations.some((s) => s.id === this._stationId)) this._stationId = "";
      this._stationSelect.replaceChildren(); const empty = this._el("option", stations.length ? "Choose a station" : "No matching stations"); empty.value = "";
      this._stationSelect.append(empty);
      for (const station of stations) { const option = this._el("option", station.name); option.value = station.id; this._stationSelect.append(option); }
      this._stationSelect.value = this._stationId;
    }
    _refreshState() {
      if (!this._chips) return;
      let onlineSelected = 0;
      for (const [entity, { button, state }] of this._chips) {
        const current = this._hass?.states[entity], online = available(current), selected = this._selected.has(entity);
        button.setAttribute("aria-pressed", String(selected)); button.classList.toggle("offline", !online);
        state.textContent = online ? current.state.replaceAll("_", " ") : "Offline";
        if (online && selected) onlineSelected++;
      }
      this._selection.textContent = `${this._selected.size} selected · ${onlineSelected} available. Offline speakers stay visible and are skipped.`;
      for (const element of this.shadowRoot.querySelectorAll("button,input,select")) element.disabled = this._busy || !this._hass;
    }
    _message(message, kind) { const row = this._el("li", message, kind); this._results.append(row); }
    async _run(action) {
      if (this._busy || !this._hass) return;
      const request = { action, volume: this._volume / 100 };
      if (this._mode === "station") request.stationId = this._stationId; else request.customUrl = this._url.value;
      const plan = planDispatch(this._config, this._hass.states, this._selected, request);
      this._results.replaceChildren();
      for (const entry of plan.excluded) this._message(`${entry.name}: ${entry.reason}`, "");
      for (const error of plan.errors) this._message(error, "error");
      if (plan.errors.length) return;
      this._busy = true; this._refreshState();
      try {
        await executePlan(this._hass, plan, (entry) => this._message(`${entry.name}: ${entry.message}`, entry.ok ? "sent" : "error"));
      } finally { this._busy = false; this._refreshState(); }
    }
  }
  if (typeof customElements !== "undefined" && !customElements.get("radio-console-card")) customElements.define("radio-console-card", RadioConsoleCard);
  if (typeof window !== "undefined") {
    window.customCards = window.customCards || [];
    window.customCards.push({ type: "radio-console-card", name: "Radio & speakers", description: "Choose a stream and explicitly send it to selected speakers." });
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { FEATURES, normalizeConfig, planDispatch, executePlan };
})();
