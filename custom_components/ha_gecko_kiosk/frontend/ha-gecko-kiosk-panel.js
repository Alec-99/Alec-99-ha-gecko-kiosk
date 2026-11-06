class HaGeckoKioskPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._kiosks = [];
    this._timer = null;
    this._loading = false;
    this._tab = "overview";
    this._selectedKiosk = "";
    this._drafts = new Map();
    this._message = "";
    this._messageKind = "info";
  }

  set hass(value) {
    this._hass = value;
    if (!this._timer) {
      this._refresh();
      this._timer = window.setInterval(() => this._refresh(), 2000);
    }
  }

  set panel(value) { this._panel = value; }
  connectedCallback() { this._render(); }
  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
  }

  async _refresh() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const result = await this._hass.connection.sendMessagePromise({ type: "ha_gecko_kiosk/list" });
      this._kiosks = Array.isArray(result.kiosks) ? result.kiosks : [];
      if (!this._kiosks.some(kiosk => kiosk.id === this._selectedKiosk)) {
        this._selectedKiosk = this._kiosks[0]?.id || "";
      }
      this._render();
    } catch (error) {
      console.error("Vernieuwen van kioskgegevens mislukt", error);
      this._message = "Kioskgegevens konden niet worden geladen. Controleer de verbinding en probeer opnieuw.";
      this._messageKind = "error";
      this._render();
    } finally {
      this._loading = false;
    }
  }

  _escape(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  _selected() { return this._kiosks.find(kiosk => kiosk.id === this._selectedKiosk); }

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

  _captureState() {
    const active = this.shadowRoot.activeElement;
    const focus = active?.dataset?.focusKey;
    const scrollTop = window.scrollY || this.shadowRoot.scrollTop;
    for (const input of this.shadowRoot.querySelectorAll("[data-section][data-key]")) {
      const key = `${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
      this._drafts.set(key, input.type === "checkbox" ? input.checked : input.value);
    }
    return { focus, scrollTop };
  }

  _field(kiosk, section, key, label, value, type = "number", min = "", max = "") {
    const id = this._escape(kiosk.id);
    const draftKey = `${kiosk.id}:${section}:${key}`;
    const current = this._drafts.has(draftKey) ? this._drafts.get(draftKey) : value;
    const checked = type === "checkbox" && current ? "checked" : "";
    const bounds = type === "number" ? `min="${min}" max="${max}" step="1"` : "";
    const val = type === "checkbox" ? "" : `value="${this._escape(current ?? "")}"`;
    return `<label class="field"><span>${label}</span><input aria-label="${label}" type="${type}" ${type === "number" || type === "color" ? "required" : ""} ${bounds} ${val} ${checked} data-kiosk="${id}" data-section="${section}" data-key="${key}"></label>`;
  }

  _settings(kiosk) {
    const settings = kiosk.settings;
    if (!settings?.screensaver || !settings?.camera_popup) return `<p class="muted">De tablet heeft nog geen instellingen teruggestuurd.</p><button data-action="get-settings">Instellingen ophalen</button>`;
    const s = settings.screensaver, c = settings.camera_popup;
    return `<div class="settings-grid">
      <section class="setting-group"><h3><ha-icon icon="mdi:weather-night"></ha-icon> Schermbeveiliging</h3>
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
        <div class="actions"><button data-action="save" data-section="screensaver">Screensaver verzenden</button><button class="secondary" data-action="reset" data-section="screensaver">Herstellen</button></div>
      </section>
      <section class="setting-group"><h3><ha-icon icon="mdi:cctv"></ha-icon> Camera-popup</h3>
        ${this._field(kiosk,"camera_popup","width_percent","Breedte (%)",c.width_percent,"number",40,100)}
        ${this._field(kiosk,"camera_popup","height_percent","Hoogte (%)",c.height_percent,"number",40,100)}
        ${this._field(kiosk,"camera_popup","dim_percent","Achtergrond verduisteren (%)",c.dim_percent,"number",0,95)}
        <div class="actions"><button data-action="save" data-section="camera_popup">Camera-popup verzenden</button><button class="secondary" data-action="reset" data-section="camera_popup">Herstellen</button></div>
      </section></div>`;
  }

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
        <span class="muted">${battery.charging == null ? "Oplaadstatus onbekend" : battery.charging ? "Opladen" : "Niet aan het opladen"}</span>
      </button>`;
    }).join("")}</div>`;
  }

  _diagnostics(kiosk) {
    if (!kiosk) return `<p class="muted">Selecteer een kiosk om diagnostiek te bekijken.</p>`;
    const battery = kiosk.battery || {}, status = kiosk.status || {};
    return `<dl class="diagnostics"><dt>Verbinding</dt><dd>${this._escape(kiosk.availability || "unknown")}</dd>
      <dt>Camera</dt><dd>${this._escape(status.camera_state ?? "—")}</dd>
      <dt>Batterij</dt><dd>${this._escape(battery.level ?? "—")}${battery.level == null ? "" : "%"}</dd>
      <dt>Opladen</dt><dd>${this._escape(battery.charging ?? "—")}</dd>
      <dt>Batterijtemperatuur</dt><dd>${this._escape(battery.temperature ?? "—")}</dd>
      <dt>Instellingenstatus</dt><dd role="status">${this._escape(this._settingsStatusText(kiosk))}</dd></dl>
      <button class="secondary" data-action="get-settings">Instellingen opnieuw opvragen</button>`;
  }

  async _call(service, data, successText) {
    try {
      await this._hass.callService("ha_gecko_kiosk", service, data);
      this._message = successText;
      this._messageKind = "info";
      if (["set_screensaver", "set_camera_popup", "reset_settings"].includes(service)) {
        this._message = "Opdracht verzonden; wachten op bevestiging van de tablet.";
      }
    } catch (error) {
      console.error(`HA-service ${service} mislukt`, error);
      this._message = `Opdracht mislukt: ${error?.message || "Home Assistant heeft de servicecall afgewezen."}`;
      this._messageKind = "error";
    }
    this._render();
  }

  _render() {
    if (!this.shadowRoot) return;
    const state = this._captureState();
    const kiosk = this._selected();
    const tabs = [["overview","Overzicht","mdi:view-dashboard"],["controls","Bediening","mdi:gesture-tap-button"],["settings","Instellingen","mdi:cog-outline"],["diagnostics","Diagnostiek","mdi:heart-pulse"]];
    let content = "";
    if (this._tab === "overview") content = this._overview();
    if (this._tab === "controls") content = kiosk ? `<section class="surface"><h2>Bediening <span class="muted">${this._escape(kiosk.id)}</span></h2><div class="control-grid">
      <div class="control-group"><h3><ha-icon icon="mdi:weather-night"></ha-icon> Schermbeveiliging</h3><button data-action="device" data-command="screensaver" data-value="ON">Tonen</button><button class="secondary" data-action="device" data-command="screensaver" data-value="OFF">Verbergen</button></div>
      <div class="control-group"><h3><ha-icon icon="mdi:cctv"></ha-icon> Deurbelcamera</h3><button data-action="camera" data-value="prewarm">Voorladen</button><button data-action="camera" data-value="show">Tonen</button><button class="secondary" data-action="camera" data-value="hide">Verbergen</button><button class="secondary" data-action="camera" data-value="stop">Stoppen</button></div>
    </div></section>` : `<p class="muted">Selecteer eerst een kiosk in Overzicht.</p>`;
    if (this._tab === "settings") content = kiosk ? `<section class="surface"><h2>Instellingen <span class="muted">${this._escape(kiosk.id)}</span></h2><p class="notice" role="status">${this._escape(this._settingsStatusText(kiosk))}</p><p class="muted">Een verzonden opdracht is pas toegepast nadat de tablet deze heeft bevestigd.</p>${this._settings(kiosk)}</section>` : `<p class="muted">Selecteer eerst een kiosk in Overzicht.</p>`;
    if (this._tab === "diagnostics") content = `<section class="surface"><h2>Diagnostiek</h2>${this._diagnostics(kiosk)}</section>`;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;box-sizing:border-box;min-height:100%;padding:clamp(12px,3vw,28px);color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}
      *{box-sizing:border-box}header{display:flex;align-items:center;gap:14px;margin:0 0 20px}.brand{width:40px;height:40px;object-fit:contain}h1{font-size:clamp(22px,4vw,30px);margin:0}h2{font-size:20px;margin:0 0 16px}h3{font-size:16px;margin:0 0 12px}h4{margin:16px 0 8px}.muted{color:var(--secondary-text-color);font-weight:400;font-size:.9em}
      nav{display:flex;gap:8px;overflow-x:auto;border-bottom:1px solid var(--divider-color);margin-bottom:20px}nav button{white-space:nowrap;border-radius:10px 10px 0 0;background:transparent;color:var(--secondary-text-color);border-bottom:3px solid transparent}nav button[aria-current=page]{color:var(--primary-text-color);border-bottom-color:var(--primary-color)}
      button{font:inherit;min-height:44px;padding:9px 14px;border:0;border-radius:10px;background:var(--primary-color);color:var(--text-primary-color,white);cursor:pointer}button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color)}button:hover{filter:brightness(1.08)}button:focus-visible,input:focus-visible{outline:3px solid var(--primary-color);outline-offset:2px}
      .overview-grid,.control-grid,.settings-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:14px}.kiosk-card,.surface,.setting-group,.empty{display:block;text-align:left;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:var(--ha-card-border-radius,14px);box-shadow:var(--ha-card-box-shadow,0 2px 6px rgba(0,0,0,.12));padding:18px}.kiosk-card{width:100%}.kiosk-card.selected{border-color:var(--primary-color);box-shadow:0 0 0 1px var(--primary-color)}.card-top,.metrics{display:flex;align-items:center;justify-content:space-between;gap:12px}.metrics{justify-content:flex-start;margin:18px 0 12px}.metrics span{display:inline-flex;align-items:center;gap:6px}.pill{border-radius:99px;padding:5px 10px;font-size:12px;text-transform:capitalize}.pill.online{color:var(--success-color,#2e7d32);background:color-mix(in srgb,var(--success-color,#2e7d32) 14%,transparent)}.pill.offline{color:var(--error-color,#b3261e);background:color-mix(in srgb,var(--error-color,#b3261e) 14%,transparent)}.pill.unknown{color:var(--secondary-text-color);background:var(--secondary-background-color)}
      .control-group,.setting-group{display:flex;flex-direction:column;align-items:flex-start;gap:10px}.field{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;min-height:42px;width:100%}.field input[type=number]{width:112px}.field input[type=color]{width:54px;height:38px}.field input{font:inherit;color:var(--primary-text-color);background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:8px;padding:8px}.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.diagnostics{display:grid;grid-template-columns:minmax(130px,1fr) minmax(0,2fr);gap:10px 16px}.diagnostics dt{color:var(--secondary-text-color)}.diagnostics dd{margin:0;overflow-wrap:anywhere}.notice{margin:0 0 16px;padding:12px 14px;border-radius:10px;background:var(--secondary-background-color);border-inline-start:4px solid var(--primary-color)}.notice.error{border-color:var(--error-color,#b3261e)}ha-icon{--mdc-icon-size:20px;vertical-align:middle;margin-inline-end:5px}
      @media(max-width:600px){.surface,.setting-group,.kiosk-card{padding:14px}.diagnostics{grid-template-columns:1fr auto}.field{grid-template-columns:1fr auto}nav{margin-inline:-4px}}
      </style>
      <header><img class="brand" src="/ha_gecko_kiosk_static/icon.png" alt=""><h1>Gecko-kiosken</h1></header>
      <nav aria-label="Kioskbeheer">${tabs.map(([id,label,icon])=>`<button data-action="tab" data-tab="${id}" aria-current="${this._tab===id?"page":"false"}"><ha-icon icon="${icon}"></ha-icon>${label}</button>`).join("")}</nav>
      ${this._message?`<div class="notice ${this._messageKind}" role="${this._messageKind==="error"?"alert":"status"}">${this._escape(this._message)}</div>`:""}${content}`;
    for (const input of this.shadowRoot.querySelectorAll("[data-section][data-key]")) input.dataset.focusKey=`${input.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
    for (const button of this.shadowRoot.querySelectorAll("button[data-action]")) {
      button.dataset.focusKey = [button.dataset.action, button.dataset.tab, button.dataset.kiosk, button.dataset.section, button.dataset.value].join(":");
    }
    this.shadowRoot.scrollTop=state.scrollTop;
    if (state.scrollTop && window.scrollY !== state.scrollTop) window.scrollTo(0, state.scrollTop);
    if(state.focus) [...this.shadowRoot.querySelectorAll("[data-focus-key]")]
      .find(item => item.dataset.focusKey === state.focus)?.focus({preventScroll:true});
    this.shadowRoot.querySelectorAll("button[data-action]").forEach(button=>button.addEventListener("click",()=>this._handleAction(button)));
  }

  async _handleAction(button) {
    const action=button.dataset.action, kiosk=button.dataset.kiosk||this._selectedKiosk;
    if(action==="tab"){this._tab=button.dataset.tab;this._message="";this._render();return;}
    if(action==="select"){this._selectedKiosk=kiosk;this._message="";this._render();return;}
    if(action==="device"){await this._call("device",{kiosk,command:button.dataset.command,value:button.dataset.value},"Opdracht verzonden.");return;}
    if(action==="camera"){await this._call("camera",{kiosk,action:button.dataset.value,camera:"doorbell"},"Cameraopdracht verzonden.");return;}
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
