class HaGeckoKioskPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._kiosks = [];
    this._timer = null;
    this._loading = false;
    this._busy = false;
    this._loadError = "";
    this._tab = "overview";
    this._selectedKiosk = "";
    this._drafts = new Map();
    this._message = "";
    this._messageKind = "info";
  }

  set hass(value) {
    this._hass = value;
    this._startPolling();
  }

  _startPolling() {
    if (this.isConnected && this._hass && !this._timer) {
      this._refresh();
      this._timer = window.setInterval(() => this._refresh(), 2000);
    }
  }

  set panel(value) { this._panel = value; }
  connectedCallback() { this._render(); this._startPolling(); }
  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
  }

  async _refresh() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const result = await this._hass.connection.sendMessagePromise({ type: "ha_gecko_kiosk/list" });
      this._captureState();
      const previousSelection = this._selectedKiosk;
      this._kiosks = Array.isArray(result.kiosks) ? result.kiosks : [];
      this._loadError = "";
      if (!this._kiosks.some(kiosk => kiosk.id === this._selectedKiosk)) {
        this._selectedKiosk = this._kiosks[0]?.id || "";
      }
      if (this._tab === "settings" && previousSelection === this._selectedKiosk &&
          this.shadowRoot.querySelector("[data-key]")) this._updateSettings();
      else this._render();
    } catch (error) {
      console.error("Vernieuwen van kioskgegevens mislukt", error);
      this._loadError = "Kioskgegevens konden niet worden geladen. Controleer de verbinding en probeer opnieuw.";
      if (this._tab === "settings" && this.shadowRoot.querySelector("[data-key]")) this._updateSettings();
      else this._render();
    } finally {
      this._loading = false;
    }
  }

  _escape(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  _selected() { return this._kiosks.find(kiosk => kiosk.id === this._selectedKiosk); }

  _supports(kiosk, capability) {
    const manifest = kiosk?.capabilities;
    if (manifest == null) return true; // Legacy Gecko clients did not publish a manifest.
    return manifest.compatible === true && Array.isArray(manifest.capabilities) &&
      manifest.capabilities.includes(capability);
  }

  _controls(kiosk) {
    const groups = [];
    const display = kiosk?.display || {}, audio = kiosk?.audio || {};
    const readiness = String(display.power_control_ready ?? "").toLowerCase();
    const powerOffUnavailable = ["false", "off", "0", "no"].includes(readiness);
    if (this._supports(kiosk, "display.power")) groups.push(`
      <div class="control-group"><h3><ha-icon icon="mdi:monitor"></ha-icon> Scherm</h3><p class="muted">Status: ${this._escape(display.power ?? "onbekend")}${display.power_state_detail ? ` · ${this._escape(display.power_state_detail)}` : ""}</p><div class="actions"><button data-action="device" data-command="screen" data-value="ON">Inschakelen</button><button class="secondary" data-action="device" data-command="screen" data-value="OFF" ${powerOffUnavailable ? "disabled title=\"Scherm uitschakelen vereist apparaatbeheer\"" : ""}>Uitschakelen</button></div>${powerOffUnavailable ? `<p class="muted" role="status">Uitschakelen vereist apparaatbeheer op de kiosk.</p>` : ""}</div>`);
    if (this._supports(kiosk, "display.brightness")) groups.push(`
      <div class="control-group"><h3><ha-icon icon="mdi:brightness-6"></ha-icon> Helderheid</h3>${this._controlRange(kiosk, "display", "brightness_percent", "Helderheid (%)", display.brightness_percent, 1)}<button data-action="control" data-command="brightness" data-target="display:brightness_percent">Helderheid toepassen</button></div>`);
    if (this._supports(kiosk, "audio.volume") || this._supports(kiosk, "audio.mute")) groups.push(`
      <div class="control-group"><h3><ha-icon icon="mdi:volume-high"></ha-icon> Audio</h3>${this._supports(kiosk, "audio.volume") ? `${this._controlRange(kiosk, "audio", "volume_percent", "Volume (%)", audio.volume_percent)}<button data-action="control" data-command="volume" data-target="audio:volume_percent">Volume toepassen</button>` : ""}${this._supports(kiosk, "audio.mute") ? `<button class="secondary" data-action="device" data-command="mute" data-value="${this._isTrue(audio.muted) ? "OFF" : "ON"}">${this._isTrue(audio.muted) ? "Geluid inschakelen" : "Dempen"}</button>` : ""}</div>`);
    if (this._supports(kiosk, "dashboard.reload")) groups.push(`
      <div class="control-group"><h3><ha-icon icon="mdi:refresh"></ha-icon> Dashboard</h3><button data-action="device" data-command="reload_dashboard" data-value="reload">Dashboard vernieuwen</button></div>`);
    if (this._supports(kiosk, "screensaver.activate")) groups.push(`
      <div class="control-group"><h3><ha-icon icon="mdi:weather-night"></ha-icon> Schermbeveiliging</h3><button data-action="device" data-command="screensaver" data-value="ON">Tonen</button><button class="secondary" data-action="device" data-command="screensaver" data-value="OFF">Verbergen</button></div>`);
    const manifest = kiosk?.capabilities;
    const cameraIds = manifest == null ? ["doorbell"] :
      this._supports(kiosk, "camera.external") && Array.isArray(manifest.resources?.cameras)
        ? manifest.resources.cameras : [];
    for (const cameraId of cameraIds) groups.push(`
      <div class="control-group"><h3><ha-icon icon="mdi:cctv"></ha-icon> Camera: ${this._escape(cameraId)}</h3><button data-action="camera" data-camera="${this._escape(cameraId)}" data-value="prewarm">Voorladen</button><button data-action="camera" data-camera="${this._escape(cameraId)}" data-value="show">Tonen</button><button class="secondary" data-action="camera" data-camera="${this._escape(cameraId)}" data-value="hide">Verbergen</button><button class="secondary" data-action="camera" data-camera="${this._escape(cameraId)}" data-value="stop">Stoppen</button></div>`);
    if (groups.length) return `<div class="control-grid">${groups.join("")}</div>`;
    if (kiosk?.capabilities?.compatible === false) return `<p class="muted" role="status">Dit apparaat gebruikt een niet-ondersteunde capabilityversie. De bediening is uitgeschakeld.</p>`;
    return `<p class="muted" role="status">Dit apparaat heeft geen bedienbare capabilities opgegeven.</p>`;
  }

  _controlRange(kiosk, section, key, label, value, minimum = 0) {
    const draftKey = `${kiosk.id}:${section}:${key}`;
    const parsed = Number(value);
    const serverValue = Number.isFinite(parsed) ? String(Math.max(minimum, Math.min(100, parsed))) : "";
    const current = this._drafts.has(draftKey) ? this._drafts.get(draftKey) : serverValue;
    return `<label class="field range-field"><span>${label}<output>${this._escape(current || "—")}</output></span><input type="range" min="${minimum}" max="100" step="1" value="${this._escape(current)}" aria-label="${label}" data-control-section="${section}" data-control-key="${key}" data-control-kiosk="${this._escape(kiosk.id)}" data-server-value="${this._escape(JSON.stringify(serverValue))}"></label>`;
  }

  _settingsStatusText(kiosk) {
    const response = kiosk.last_settings_response;
    const request = kiosk.last_settings_request;
    if (request && response?.request_id !== request) {
      const requestAt = Number(kiosk.last_settings_request_at_ms) || Date.now();
      return Date.now() - requestAt > 65_000
        ? "Geen bevestiging ontvangen (time-out na 65 seconden)"
        : "Verzonden; wachten op bevestiging van de tablet";
    }
    if (response) return response.status === "applied"
      ? "Bevestigd door de tablet" : `Geweigerd: ${String(response.detail || "onbekende fout")}`;
    return "Nog geen configuratieantwoord ontvangen";
  }

  _deviceCommandStatusText(kiosk) {
    const request = kiosk.last_device_request;
    const response = kiosk.last_device_response;
    if (!request) return "Geen recente opdrachtbevestiging";
    if (response?.request_id !== request) {
      const requestedAt = Number(kiosk.last_device_request_at_ms) || Date.now();
      return Date.now() - requestedAt > 65_000
        ? "Geen tabletbevestiging ontvangen (time-out na 65 seconden)"
        : "Opdracht verzonden; wachten op tabletbevestiging";
    }
    const labels = {
      applied: "Bevestigd door de tablet",
      rejected: "Geweigerd door de tablet",
      unsupported: "Niet ondersteund door de tablet",
      unavailable: "Tijdelijk niet beschikbaar op de tablet",
      expired: "Verlopen voordat de tablet de opdracht uitvoerde",
      error: "Fout tijdens uitvoering op de tablet",
    };
    const label = labels[response.status] || "Onbekende tabletrespons";
    return response.detail ? `${label}: ${response.detail}` : label;
  }

  _captureState() {
    const active = this.shadowRoot.activeElement;
    const focus = active?.dataset?.focusKey;
    const scrolls = [];
    for (let element = this; element; element = element.parentElement || element.getRootNode()?.host) {
      scrolls.push({ element, top: element.scrollTop, left: element.scrollLeft });
    }
    const navLeft = this.shadowRoot.querySelector("nav")?.scrollLeft || 0;
    const windowPosition = { top: window.scrollY, left: window.scrollX };
    for (const input of this.shadowRoot.querySelectorAll("[data-section][data-key]")) {
      const key = `${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
      const value = input.type === "checkbox" ? input.checked : input.value;
      if (JSON.stringify(value) === input.dataset.serverValue) this._drafts.delete(key);
      else this._drafts.set(key, value);
    }
    for (const input of this.shadowRoot.querySelectorAll("[data-control-section][data-control-key]")) {
      const key = `${input.dataset.controlKiosk}:${input.dataset.controlSection}:${input.dataset.controlKey}`;
      if (JSON.stringify(String(input.value)) === input.dataset.serverValue) this._drafts.delete(key);
      else this._drafts.set(key, String(input.value));
    }
    return { focus, scrolls, navLeft, windowPosition };
  }

  _field(kiosk, section, key, label, value, type = "number", min = "", max = "") {
    const id = this._escape(kiosk.id);
    const draftKey = `${kiosk.id}:${section}:${key}`;
    const serverValue = type === "checkbox" ? Boolean(value) : String(value ?? "");
    const current = this._drafts.has(draftKey) ? this._drafts.get(draftKey) : serverValue;
    const checked = type === "checkbox" && current ? "checked" : "";
    const bounds = type === "number" ? `min="${min}" max="${max}" step="1"` : "";
    const val = type === "checkbox" ? "" : `value="${this._escape(current ?? "")}"`;
    return `<label class="field"><span>${label}</span><input aria-label="${label}" type="${type}" ${type === "number" || type === "color" ? "required" : ""} ${bounds} ${val} ${checked} data-kiosk="${id}" data-section="${section}" data-key="${key}" data-server-value="${this._escape(JSON.stringify(serverValue))}"></label>`;
  }

  _settings(kiosk) {
    const settings = kiosk.settings;
    const hasScreensaver = this._supports(kiosk, "screensaver.settings");
    const hasCameraPopup = this._supports(kiosk, "camera.popup_settings");
    if (!hasScreensaver && !hasCameraPopup) return `<p class="muted">Dit apparaat ondersteunt geen extern wijzigbare instellingen.</p>`;
    if ((hasScreensaver && !settings?.screensaver) || (hasCameraPopup && !settings?.camera_popup)) return `<p class="muted">De tablet heeft nog geen instellingen teruggestuurd.</p><button data-action="get-settings">Instellingen ophalen</button>`;
    const s = settings.screensaver, c = settings.camera_popup;
    return `<div class="settings-grid">
      ${hasScreensaver ? `<section class="setting-group"><h3><ha-icon icon="mdi:weather-night"></ha-icon> Schermbeveiliging</h3>
        ${this._field(kiosk,"screensaver","enabled","Screensaver inschakelen",s.enabled,"checkbox")}
        ${this._field(kiosk,"screensaver","inactivity_timeout_seconds","Wachttijd (seconden)",s.inactivity_timeout_seconds,"number",5,86400)}
        ${this._field(kiosk,"screensaver","consume_wake_touch","Eerste tik maakt alleen wakker",s.consume_wake_touch,"checkbox")}
        <h4>Klok en uiterlijk</h4>
        ${this._field(kiosk,"screensaver","show_clock","Klok tonen",s.show_clock,"checkbox")}
        ${this._field(kiosk,"screensaver","show_date","Datum tonen",s.show_date,"checkbox")}
        ${this._field(kiosk,"screensaver","clock_text_size_sp","Klokgrootte (sp)",s.clock_text_size_sp,"number",12,200)}
        ${this._field(kiosk,"screensaver","date_text_size_sp","Datumgrootte (sp)",s.date_text_size_sp,"number",10,100)}
        ${this._field(kiosk,"screensaver","clock_update_interval_seconds","Klokverversing (seconden)",s.clock_update_interval_seconds,"number",1,3600)}
        ${this._field(kiosk,"screensaver","background_color","Achtergrondkleur",s.background_color || "#000000","color")}
        ${this._field(kiosk,"screensaver","text_color","Tekstkleur",s.text_color || "#ffffff","color")}
        <div class="actions"><button data-action="save" data-section="screensaver">Screensaver verzenden</button><button class="secondary" data-action="reset" data-section="screensaver">Herstellen</button><button class="secondary" data-action="discard" data-section="screensaver">Tabletwaarden gebruiken</button></div>
      </section>` : ""}
      ${hasCameraPopup ? `<section class="setting-group"><h3><ha-icon icon="mdi:cctv"></ha-icon> Camera-popup</h3>
        ${this._field(kiosk,"camera_popup","width_percent","Breedte (%)",c.width_percent,"number",40,100)}
        ${this._field(kiosk,"camera_popup","height_percent","Hoogte (%)",c.height_percent,"number",40,100)}
        ${this._field(kiosk,"camera_popup","dim_percent","Achtergrond verduisteren (%)",c.dim_percent,"number",0,95)}
        <div class="actions"><button data-action="save" data-section="camera_popup">Camera-popup verzenden</button><button class="secondary" data-action="reset" data-section="camera_popup">Herstellen</button><button class="secondary" data-action="discard" data-section="camera_popup">Tabletwaarden gebruiken</button></div>
      </section>` : ""}
      </div>`;
  }

  _chargingText(value) {
    if ([true, "true", "ON", "on", "1"].includes(value)) return "Opladen";
    if ([false, "false", "OFF", "off", "0"].includes(value)) return "Niet aan het opladen";
    return "Oplaadstatus onbekend";
  }

  _isTrue(value) { return [true, "true", "on", "1"].includes(typeof value === "string" ? value.toLowerCase() : value); }

  _overview() {
    if (!this._kiosks.length) return `<section class="empty"><ha-icon icon="mdi:tablet"></ha-icon><h2>Nog geen kiosken</h2><p>Een kiosk verschijnt hier na een MQTT-statusbericht.</p></section>`;
    return `<div class="overview-grid">${this._kiosks.map(kiosk => {
      const state = String(kiosk.availability || "unknown").toLowerCase();
      const stateClass = ["online", "offline"].includes(state) ? state : "unknown";
      const status = kiosk.status || {}, battery = kiosk.battery || {};
      const selected = kiosk.id === this._selectedKiosk;
      return `<button class="kiosk-card ${selected ? "selected" : ""}" data-action="select" data-kiosk="${this._escape(kiosk.id)}" aria-pressed="${selected}">
        <span class="card-top"><strong>${this._escape(kiosk.id)}</strong><span class="pill ${stateClass}">${this._escape(state)}</span></span>
        <span class="metrics"><span><ha-icon icon="mdi:battery"></ha-icon>${this._escape(battery.level ?? "—")}${battery.level == null ? "" : "%"}</span><span><ha-icon icon="mdi:cctv"></ha-icon>${this._escape(status.camera_state ?? "—")}</span></span>
        <span class="muted">${this._chargingText(battery.charging)}</span>
      </button>`;
    }).join("")}</div>`;
  }

  _diagnostics(kiosk) {
    if (!kiosk) return `<p class="muted">Selecteer een kiosk om diagnostiek te bekijken.</p>`;
    const battery = kiosk.battery || {}, status = kiosk.status || {}, diagnostics = kiosk.diagnostics || {};
    const manifest = kiosk.capabilities;
    const capabilityNames = Array.isArray(manifest?.capabilities) ? manifest.capabilities : [];
    const capabilityText = manifest == null ? "Legacy (geen manifest)"
      : manifest.compatible ? (capabilityNames.join(", ") || "Geen")
        : `Niet compatibel (protocol ${manifest.protocol_version ?? "onbekend"})`;
    return `<dl class="diagnostics"><dt>Verbinding</dt><dd>${this._escape(kiosk.availability || "unknown")}</dd>
      <dt>Protocol</dt><dd>${this._escape(capabilityText)}</dd>
      <dt>Camera</dt><dd>${this._escape(status.camera_state ?? "—")}</dd>
      <dt>Scherm</dt><dd>${this._escape(kiosk.display?.power ?? "—")}${kiosk.display?.power_state_detail ? ` · ${this._escape(kiosk.display.power_state_detail)}` : ""}</dd>
      <dt>Helderheid</dt><dd>${this._escape(kiosk.display?.brightness_percent ?? "—")}${kiosk.display?.brightness_percent == null ? "" : "%"}</dd>
      <dt>Power-bediening gereed</dt><dd>${this._escape(kiosk.display?.power_control_ready ?? "—")}</dd>
      <dt>Volume</dt><dd>${this._escape(kiosk.audio?.volume_percent ?? "—")}${kiosk.audio?.volume_percent == null ? "" : "%"}</dd>
      <dt>Gedempt</dt><dd>${this._escape(kiosk.audio?.muted ?? "—")}</dd>
      <dt>App-versie</dt><dd>${this._escape(diagnostics.app_version ?? "—")}</dd>
      <dt>Watchdog</dt><dd>${this._escape(diagnostics.watchdog_status ?? "—")}</dd>
      <dt>Watchdog-herstarts</dt><dd>${this._escape(diagnostics.watchdog_restart_count ?? "—")}</dd>
      <dt>MQTT-reconnects</dt><dd>${this._escape(diagnostics.mqtt_reconnect_count ?? "—")}</dd>
      <dt>Laatste bediening</dt><dd role="status">${this._escape(this._deviceCommandStatusText(kiosk))}</dd>
      <dt>Batterij</dt><dd>${this._escape(battery.level ?? "—")}${battery.level == null ? "" : "%"}</dd>
      <dt>Opladen</dt><dd>${this._chargingText(battery.charging)}</dd>
      <dt>Batterijtemperatuur</dt><dd>${this._escape(battery.temperature ?? "—")}</dd>
      <dt>Instellingenstatus</dt><dd role="status">${this._escape(this._settingsStatusText(kiosk))}</dd></dl>
      ${this._supports(kiosk, "screensaver.settings") || this._supports(kiosk, "camera.popup_settings")
        ? `<button class="secondary" data-action="get-settings">Instellingen opnieuw opvragen</button>` : ""}`;
  }

  async _call(service, data, successText) {
    if (this._busy) return;
    this._busy = true;
    this.shadowRoot.querySelectorAll("button[data-action]").forEach(button => {
      if (!["tab", "select", "discard"].includes(button.dataset.action)) button.disabled = true;
    });
    try {
      await this._hass.callService("ha_gecko_kiosk", service, data);
      this._message = successText;
      this._messageKind = "info";
      if (service === "device") this._message = "Opdracht verzonden. De tabletrespons verschijnt bij Bediening en Diagnostiek wanneer de client dit ondersteunt.";
      if (["set_screensaver", "set_camera_popup", "reset_settings"].includes(service)) {
        this._message = "Opdracht naar Home Assistant verzonden. De tabletstatus staat hieronder.";
      }
    } catch (error) {
      console.error(`HA-service ${service} mislukt`, error);
      this._message = `Opdracht mislukt: ${error?.message || "Home Assistant heeft de servicecall afgewezen."}`;
      this._messageKind = "error";
    }
    this._busy = false;
    this._render();
    await this._refresh();
  }

  _updateSettings(forceSection) {
    const kiosk = this._selected();
    for (const input of this.shadowRoot.querySelectorAll("[data-key]")) {
      const key = `${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
      const raw = kiosk?.settings?.[input.dataset.section]?.[input.dataset.key];
      if (raw == null) continue;
      const value = input.type === "checkbox" ? Boolean(raw) : String(raw);
      if (!this._drafts.has(key) || forceSection === input.dataset.section) {
        if (input.type === "checkbox" && input.checked !== value) input.checked = value;
        else if (input.type !== "checkbox" && input.value !== value) input.value = value;
      }
      input.dataset.serverValue = JSON.stringify(value);
    }
    this.shadowRoot.querySelector("[data-settings-status]").textContent = this._settingsStatusText(kiosk);
    this.shadowRoot.querySelector("[data-load-error]").textContent = this._loadError;
    this.shadowRoot.querySelector("[data-load-error]").hidden = !this._loadError;
  }

  _render() {
    if (!this.shadowRoot) return;
    const state = this._captureState();
    const kiosk = this._selected();
    const tabs = [["overview","Overzicht","mdi:view-dashboard"],["controls","Bediening","mdi:gesture-tap-button"],["settings","Instellingen","mdi:cog-outline"],["diagnostics","Diagnostiek","mdi:heart-pulse"]];
    let content = "";
    if (this._tab === "overview") content = this._overview();
    if (this._tab === "controls") content = kiosk ? `<section class="surface"><h2>Bediening <span class="muted">${this._escape(kiosk.id)}</span></h2>${kiosk.last_device_request ? `<p class="notice" role="status">${this._escape(this._deviceCommandStatusText(kiosk))}</p>` : ""}${this._controls(kiosk)}</section>` : `<p class="muted">Selecteer eerst een kiosk in Overzicht.</p>`;
    if (this._tab === "settings") content = kiosk ? `<section class="surface"><h2>Instellingen <span class="muted">${this._escape(kiosk.id)}</span></h2><p class="notice" role="status" data-settings-status>${this._escape(this._settingsStatusText(kiosk))}</p><p class="muted">Een verzonden opdracht is pas toegepast nadat de tablet deze heeft bevestigd.</p>${this._settings(kiosk)}</section>` : `<p class="muted">Selecteer eerst een kiosk in Overzicht.</p>`;
    if (this._tab === "diagnostics") content = `<section class="surface"><h2>Diagnostiek</h2>${this._diagnostics(kiosk)}</section>`;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;box-sizing:border-box;min-height:100%;padding:clamp(12px,3vw,28px);color-scheme:dark;--primary-text-color:#f7f8fa;--secondary-text-color:#b8c0cb;--primary-background-color:#171b21;--secondary-background-color:#2b2f36;--card-background-color:#2b2f36;--primary-color:#ff8a00;--text-primary-color:#11151d;--divider-color:#4b5563;--success-color:#71c785;--error-color:#ff7a70;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}
      *{box-sizing:border-box}header{display:flex;align-items:center;gap:14px;margin:0 0 20px}.brand{width:40px;height:40px;object-fit:contain}h1{font-size:clamp(22px,4vw,30px);margin:0}h2{font-size:20px;margin:0 0 16px}h3{font-size:16px;margin:0 0 12px}h4{margin:16px 0 8px}.muted{color:var(--secondary-text-color);font-weight:400;font-size:.9em}
      nav{display:flex;gap:8px;overflow-x:auto;border-bottom:1px solid var(--divider-color);margin-bottom:20px}nav button{white-space:nowrap;border-radius:10px 10px 0 0;background:transparent;color:var(--secondary-text-color);border-bottom:3px solid transparent}nav button[aria-current=page]{color:var(--primary-text-color);border-bottom-color:var(--primary-color)}
      button{font:inherit;min-height:44px;padding:9px 14px;border:0;border-radius:10px;background:var(--primary-color);color:var(--text-primary-color,white);cursor:pointer}button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color)}button:hover{filter:brightness(1.08)}button:focus-visible,input:focus-visible{outline:3px solid var(--primary-color);outline-offset:2px}
      .overview-grid,.control-grid,.settings-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:14px}.kiosk-card,.surface,.setting-group,.empty{display:block;text-align:left;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:var(--ha-card-border-radius,14px);box-shadow:var(--ha-card-box-shadow,0 2px 6px rgba(0,0,0,.12));padding:18px}.kiosk-card{width:100%}.kiosk-card.selected{border-color:var(--primary-color);box-shadow:0 0 0 1px var(--primary-color)}.card-top,.metrics{display:flex;align-items:center;justify-content:space-between;gap:12px}.metrics{justify-content:flex-start;margin:18px 0 12px}.metrics span{display:inline-flex;align-items:center;gap:6px}.pill{border-radius:99px;padding:5px 10px;font-size:12px;text-transform:capitalize}.pill.online{color:var(--success-color,#2e7d32);background:color-mix(in srgb,var(--success-color,#2e7d32) 14%,transparent)}.pill.offline{color:var(--error-color,#b3261e);background:color-mix(in srgb,var(--error-color,#b3261e) 14%,transparent)}.pill.unknown{color:var(--secondary-text-color);background:var(--secondary-background-color)}
      .control-group,.setting-group{display:flex;flex-direction:column;align-items:flex-start;gap:10px}.field{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;min-height:42px;width:100%}.field input[type=number]{width:112px}.field input[type=color]{width:54px;height:38px}.field input{font:inherit;color:var(--primary-text-color);background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:8px;padding:8px}.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.diagnostics{display:grid;grid-template-columns:minmax(130px,1fr) minmax(0,2fr);gap:10px 16px}.diagnostics dt{color:var(--secondary-text-color)}.diagnostics dd{margin:0;overflow-wrap:anywhere}.notice{margin:0 0 16px;padding:12px 14px;border-radius:10px;background:var(--secondary-background-color);border-inline-start:4px solid var(--primary-color)}.notice.error{border-color:var(--error-color,#b3261e)}ha-icon{--mdc-icon-size:20px;vertical-align:middle;margin-inline-end:5px}
      @media(max-width:600px){.surface,.setting-group,.kiosk-card{padding:14px}.diagnostics{grid-template-columns:1fr auto}.field{grid-template-columns:1fr auto}nav{margin-inline:-4px}}
      </style>
      <header><img class="brand" src="/ha_gecko_kiosk_static/icon.png" alt=""><h1>Gecko-kiosken</h1></header>
      <nav aria-label="Kioskbeheer">${tabs.map(([id,label,icon])=>`<button data-action="tab" data-tab="${id}" aria-current="${this._tab===id?"page":"false"}"><ha-icon icon="${icon}"></ha-icon>${label}</button>`).join("")}</nav>
      <div class="notice error" role="alert" data-load-error ${this._loadError ? "" : "hidden"}>${this._escape(this._loadError)}</div>
      ${this._message?`<div class="notice ${this._messageKind}" role="${this._messageKind==="error"?"alert":"status"}">${this._escape(this._message)}</div>`:""}${content}`;
    for (const input of this.shadowRoot.querySelectorAll("[data-section][data-key]")) {
      input.dataset.focusKey=`${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
      const rememberDraft = () => {
        const key = `${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
        const value = input.type === "checkbox" ? input.checked : input.value;
        if (JSON.stringify(value) === input.dataset.serverValue) this._drafts.delete(key);
        else this._drafts.set(key, value);
      };
      input.addEventListener("input", rememberDraft);
      input.addEventListener("change", rememberDraft);
    }
    for (const input of this.shadowRoot.querySelectorAll("[data-control-section][data-control-key]")) {
      input.dataset.focusKey = `${input.dataset.controlKiosk}:${input.dataset.controlSection}:${input.dataset.controlKey}`;
      const rememberDraft = () => {
        const key = `${input.dataset.controlKiosk}:${input.dataset.controlSection}:${input.dataset.controlKey}`;
        const value = String(input.value);
        if (JSON.stringify(value) === input.dataset.serverValue) this._drafts.delete(key);
        else this._drafts.set(key, value);
        const output = input.parentElement.querySelector("output");
        if (output) output.textContent = value;
      };
      input.addEventListener("input", rememberDraft);
      input.addEventListener("change", rememberDraft);
    }
    for (const button of this.shadowRoot.querySelectorAll("button[data-action]")) {
      button.dataset.focusKey = [button.dataset.action, button.dataset.tab, button.dataset.kiosk, button.dataset.section, button.dataset.value].join(":");
    }
    for (const { element, top, left } of state.scrolls) {
      element.scrollTop = top;
      element.scrollLeft = left;
    }
    this.shadowRoot.querySelector("nav").scrollLeft = state.navLeft;
    if (window.scrollY !== state.windowPosition.top || window.scrollX !== state.windowPosition.left) {
      window.scrollTo(state.windowPosition.left, state.windowPosition.top);
    }
    if(state.focus) [...this.shadowRoot.querySelectorAll("[data-focus-key]")]
      .find(item => item.dataset.focusKey === state.focus)?.focus({preventScroll:true});
    this.shadowRoot.querySelectorAll("button[data-action]").forEach(button => {
      button.disabled = button.disabled || this._busy;
      button.addEventListener("click", () => this._handleAction(button));
    });
  }

  async _handleAction(button) {
    const action=button.dataset.action, kiosk=button.dataset.kiosk||this._selectedKiosk;
    if(action==="tab"){this._tab=button.dataset.tab;this._message="";this._render();return;}
    if(action==="select"){this._selectedKiosk=kiosk;this._message="";this._render();return;}
    if(action==="discard"){
      this._captureState();
      for (const input of this.shadowRoot.querySelectorAll("[data-key]")) {
        if (input.dataset.section === button.dataset.section) this._drafts.delete(`${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`);
      }
      this._updateSettings(button.dataset.section);
      return;
    }
    if(action==="device"){await this._call("device",{kiosk,command:button.dataset.command,value:button.dataset.value},"Opdracht verzonden.");return;}
    if(action==="control"){
      const [section, key] = button.dataset.target.split(":");
      const input = [...this.shadowRoot.querySelectorAll("[data-control-kiosk]")].find(item =>
        item.dataset.controlKiosk === kiosk && item.dataset.controlSection === section && item.dataset.controlKey === key);
      if (!input || !/^\d{1,3}$/.test(input.value) || Number(input.value) < Number(input.min) || Number(input.value) > 100) return;
      await this._call("device",{kiosk,command:button.dataset.command,value:input.value},button.dataset.command === "brightness" ? "Helderheid verzonden." : "Volume verzonden.");return;
    }
    if(action==="camera"){await this._call("camera",{kiosk,action:button.dataset.value,camera:button.dataset.camera||"doorbell"},"Cameraopdracht verzonden.");return;}
    if(action==="get-settings"){await this._call("get_settings",{kiosk},"Instellingen opgevraagd.");return;}
    if(action==="reset"){
      if(!window.confirm("Instellingen herstellen naar de oorspronkelijke kioskconfiguratie?"))return;
      await this._call("reset_settings",{kiosk,section:button.dataset.section},"Herstelopdracht verzonden; wachten op tabletbevestiging.");return;
    }
    if(action==="save"){
      const section=button.dataset.section, fields=[...this.shadowRoot.querySelectorAll("[data-kiosk][data-section][data-key]")]
        .filter(field => field.dataset.kiosk === kiosk && field.dataset.section === section);
      const invalid=fields.find(field=>!field.checkValidity());if(invalid){invalid.reportValidity();return;}
      const payload={kiosk};for(const field of fields)payload[field.dataset.key]=field.type==="checkbox"?field.checked:field.type==="number"?Number(field.value):field.value;
      await this._call(section==="screensaver"?"set_screensaver":"set_camera_popup",payload,"Instellingen verzonden; wachten op tabletbevestiging.");
    }
  }
}

customElements.define("ha-gecko-kiosk-panel", HaGeckoKioskPanel);
