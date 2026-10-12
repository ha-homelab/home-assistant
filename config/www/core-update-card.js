/* Core update approvals: HA owns authentication; this card never receives a secret. */
class CoreUpdateCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { entity: "update.home_assistant_core", title: "Core updates" };
    this._busy = false;
    this._message = "";
    this._build();
  }

  setConfig(config) {
    const entity = config.entity || "update.home_assistant_core";
    if (!/^update\.[a-z0-9_]+$/.test(entity)) {
      throw new Error("Core update card requires an update entity.");
    }
    this._config = { entity, title: config.title || "Core updates" };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 4; }
  getGridOptions() { return { columns: 12, rows: 6 }; }

  static getStubConfig() {
    return { entity: "update.home_assistant_core", title: "Core updates" };
  }

  _element(tag, className, parent, text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
  }

  _build() {
    const style = this._element("style", "", this.shadowRoot);
    style.textContent = `
      :host { display: block; color: var(--primary-text-color, #e6edf3); }
      ha-card { display: block; padding: 22px; color: inherit;
        background: var(--ha-card-background, var(--card-background-color, #161b22)); }
      .header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
      .eyebrow { font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
        color: var(--secondary-text-color, #a7b1bd); margin-bottom: 5px; }
      h2 { font-size: 21px; font-weight: 600; line-height: 1.3; margin: 0; }
      .badge { border: 1px solid var(--divider-color, #64748b); border-radius: 18px;
        padding: 5px 9px; font-size: 12px; white-space: nowrap; }
      .versions { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 23px 0 18px; }
      .label { color: var(--secondary-text-color, #a7b1bd); font-size: 12px; margin-bottom: 5px; }
      .version { font-size: 20px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
      .description, .result { line-height: 1.5; font-size: 14px; margin: 12px 0; overflow-wrap: anywhere; }
      .error { border-left: 3px solid currentColor; padding-left: 10px; white-space: pre-wrap; }
      .actions { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; margin-top: 18px; }
      button { border: 1px solid transparent; border-radius: 11px; padding: 12px 16px;
        font: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
        background: var(--primary-text-color, #e6edf3);
        color: var(--card-background-color, #161b22); min-height: 44px; }
      button:disabled { opacity: .55; cursor: default; }
      button:focus-visible, a:focus-visible { outline: 3px solid var(--primary-color, #03a9f4); outline-offset: 4px; }
      a { color: inherit; font-size: 14px; text-underline-offset: 3px; }
      [hidden] { display: none !important; }
      @media (max-width: 350px) { ha-card { padding: 16px; } .header { align-items: start; } }
    `;
    this._card = this._element("ha-card", "", this.shadowRoot);
    const header = this._element("div", "header", this._card);
    const heading = this._element("div", "", header);
    this._element("div", "eyebrow", heading, "Home Assistant");
    this._title = this._element("h2", "", heading);
    this._badge = this._element("span", "badge", header);
    const versions = this._element("div", "versions", this._card);
    const installed = this._element("div", "", versions);
    this._element("div", "label", installed, "Installed");
    this._installed = this._element("div", "version", installed);
    const available = this._element("div", "", versions);
    this._element("div", "label", available, "Offered version");
    this._available = this._element("div", "version", available);
    this._description = this._element("p", "description", this._card);
    this._error = this._element("p", "description error", this._card);
    this._result = this._element("p", "result", this._card);
    this._result.setAttribute("role", "status");
    this._result.setAttribute("aria-live", "polite");
    const actions = this._element("div", "actions", this._card);
    this._button = this._element("button", "", actions);
    this._button.type = "button";
    this._release = this._element("a", "", actions, "Release notes");
    this._release.target = "_blank";
    this._release.rel = "noopener noreferrer";
    this._render();
  }

  _snapshot() {
    const entity = this._hass?.states?.[this._config.entity];
    const attributes = entity?.attributes || {};
    const version = typeof attributes.target_version === "string" ? attributes.target_version : "";
    const candidate = typeof attributes.candidate_id === "string" ? attributes.candidate_id : "";
    const validVersion = /^[0-9]{4}\.[0-9]{1,2}\.[0-9]+$/.test(version);
    const connected = Boolean(entity && !["unknown", "unavailable"].includes(entity.state));
    return Object.freeze({
      version,
      candidate,
      validVersion,
      connected,
      stage: connected && typeof attributes.stage === "string" ? attributes.stage : "unavailable",
      installed: typeof attributes.installed_version === "string" ? attributes.installed_version : "—",
      error: connected && typeof attributes.last_error === "string" ? attributes.last_error.slice(0, 2000) : "",
      approvable: connected && entity.state === "on" && attributes.stage === "available"
        && !attributes.in_progress && /^[0-9a-f]{32}$/.test(candidate) && validVersion
        && attributes.latest_version === version,
    });
  }

  _render() {
    if (!this._card) return;
    const snapshot = this._snapshot();
    const labels = {
      idle: "Up to date", available: "Approval needed", preparing: "Preparing",
      backup: "Backing up", preflight: "Checking", deploying: "Installing",
      verifying: "Verifying", succeeded: "Updated", failed: "Failed",
      recovery_required: "Recovery required", unavailable: "Unavailable",
    };
    const descriptions = {
      idle: "No Core update is waiting for approval.",
      available: "Approve this version to start a backup and configuration checks. Home Assistant will restart during installation.",
      preparing: "The independent updater is preparing the approved operation.",
      backup: "The updater is creating the backup required before installation.",
      preflight: "The updater is checking the new version before deployment.",
      deploying: "Installation is running. This page may disconnect while Home Assistant restarts.",
      verifying: "The updater is checking Home Assistant and its required integrations.",
      succeeded: "The approved version passed the updater’s post-install checks.",
      failed: "The update did not complete successfully. Review the result before trying again.",
      recovery_required: "Manual recovery is required. Do not start another update.",
      unavailable: "Updater status is unavailable. Approval is disabled until it reconnects.",
    };
    this._title.textContent = this._config.title;
    this._badge.textContent = labels[snapshot.stage] || "Status unknown";
    this._installed.textContent = snapshot.installed;
    this._available.textContent = snapshot.validVersion ? snapshot.version : "—";
    this._description.textContent = descriptions[snapshot.stage] || "Review the updater status before continuing.";
    this._error.textContent = snapshot.error;
    this._error.hidden = !snapshot.error;
    this._result.textContent = this._message;
    this._result.hidden = !this._message;
    this._button.disabled = this._busy || !snapshot.approvable;
    this._button.textContent = this._busy ? "Submitting approval…"
      : snapshot.approvable ? `Install ${snapshot.version}` : "Approval unavailable";
    this._card.setAttribute("aria-busy", String(this._busy));
    // The handler owns the exact snapshot rendered above. Never read a new
    // candidate after opening the confirmation dialog or while submitting.
    this._button.onclick = () => this._approve(snapshot);
    this._release.hidden = !snapshot.validVersion;
    if (snapshot.validVersion) {
      this._release.href = `https://github.com/home-assistant/core/releases/tag/${snapshot.version}`;
    } else {
      this._release.removeAttribute("href");
    }
  }

  async _approve(snapshot) {
    if (this._busy || !snapshot.approvable || !this._hass) return;
    const client = this._hass;
    const request = Object.freeze({ target_version: snapshot.version, candidate_id: snapshot.candidate });
    this._busy = true;
    this._message = "";
    this._render();
    try {
      if (!window.confirm(`Install Home Assistant ${request.target_version}?\n\nThe updater will back up and check the configuration first. Home Assistant will restart. This approval applies only to this version.`)) {
        return;
      }
      await client.callService("script", "core_update_approve", request);
      this._message = `Request sent for ${request.target_version}. Check the updater status for acceptance and progress.`;
    } catch (_) {
      this._message = `Approval for ${request.target_version} was not confirmed. Check the updater status before trying again; it may already have accepted the request.`;
    } finally {
      this._busy = false;
      this._render();
    }
  }
}

if (!customElements.get("core-update-card")) {
  customElements.define("core-update-card", CoreUpdateCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "core-update-card")) {
  window.customCards.push({
    type: "core-update-card", name: "Core updates", preview: false,
    description: "Review and explicitly approve one Home Assistant Core update.",
  });
}
