class HaGeckoKioskPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._kiosks = [];
    this._timer = null;
    this._loading = false;
    this._view = { tab: "overview", drafts: new Map(), focus: null };
  }

  set hass(value) {
    this._hass = value;
    if (!this._timer) {
      this._refresh();
      this._timer = window.setInterval(() => this._refresh(), 2000);
    }
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    this._render();
  }

  disconnectedCallback() {
    if (this._timer) {
      window.clearInterval(this._timer);
      this._timer = null;
    }
  }

  async _refresh() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const result = await this._hass.connection.sendMessagePromise({
        type: "ha_gecko_kiosk/list",
      });
      this._kiosks = Array.isArray(result.kiosks) ? result.kiosks : [];
      this._error = "";
      // Do not destroy unsaved inputs during polling. Initial settings retrieval,
      // however, must populate the open panel instead of appearing to do nothing.
      const opened = this.shadowRoot.querySelector("details.settings[open]");
      if (!opened) {
        this._render();
      } else {
        const kioskId = opened.dataset.kiosk;
        const kiosk = this._kiosks.find(k => k.id === kioskId);
        const settingsJustArrived = kiosk?.settings?.screensaver &&
          kiosk?.settings?.camera_popup &&
          !opened.querySelector('[data-section="screensaver"][data-key]');
        if (settingsJustArrived) {
          this._render();
          const restored = [...this.shadowRoot.querySelectorAll("details.settings")]
            .find(el => el.dataset.kiosk === kioskId);
          if (restored) restored.open = true;
        } else {
          const message = opened.querySelector(".settings-help");
          if (message && kiosk) message.textContent = this._settingsStatusText(kiosk);
        }
      }
    } catch (error) {
      console.error("Vernieuwen van kioskgegevens mislukt", error);
      this._error = "Kioskgegevens konden niet worden geladen. Controleer de verbinding en probeer opnieuw.";
      this._render();
    } finally {
      this._loading = false;
    }
  }

  async _camera(kiosk, action) {
    await this._hass.callService("ha_gecko_kiosk", "camera", {
      kiosk,
      action,
      camera: "doorbell",
    });
  }

  async _device(kiosk, command, value) {
    await this._hass.callService("ha_gecko_kiosk", "device", { kiosk, command, value });
  }

  _settingsStatusText(kiosk) {
    const response = kiosk.last_settings_response;
    const lastRequest = kiosk.last_settings_request;
    if (lastRequest && response?.request_id !== lastRequest) {
      const requestAt = Number(kiosk.last_settings_request_at_ms) || Date.now();
      return Date.now() - requestAt > 65_000
        ? "Geen bevestiging van de tablet ontvangen (time-out)"
        : "Instellingen verzonden; wachten op bevestiging van de tablet";
    }
    return response
      ? (response.status === "applied" ? "Laatste opdracht bevestigd door de tablet" :
        "Laatste opdracht geweigerd: " + String(response.detail || "onbekende fout"))
      : "Nog geen configuratieantwoord ontvangen";
  }

  _settingsMarkup(kiosk) {
    const id = this._escape(kiosk.id);
    const settings = kiosk.settings;
    const responseText = this._escape(this._settingsStatusText(kiosk));

    if (!settings?.screensaver || !settings?.camera_popup) {
      return `
        <div class="settings-help">De tablet heeft nog geen instellingen teruggestuurd.</div>
        <button class="refresh-settings" data-kiosk="${id}">Instellingen ophalen</button>`;
    }
    const screen = settings.screensaver;
    const camera = settings.camera_popup;
    const switches = [
      ["enabled", "Screensaver inschakelen"],
      ["show_clock", "Klok tonen"],
      ["show_date", "Datum tonen"],
      ["consume_wake_touch", "Eerste tik enkel wakker maken"],
    ];
    const ints = [
      ["inactivity_timeout_seconds", "Wachttijd (s)", 5, 86400],
      ["clock_text_size_sp", "Klokgrootte (sp)", 12, 200],
      ["date_text_size_sp", "Datumgrootte (sp)", 10, 100],
      ["clock_update_interval_seconds", "Verversing klok (s)", 1, 3600],
    ];
    const fields = [
      ...switches.map(([key, label]) => `<label class="setting-row">
        <span>${label}</span>
        <input type="checkbox" data-section="screensaver" data-key="${key}" ${screen[key] ? "checked" : ""}>
      </label>`),
      ...ints.map(([key, label, min, max]) => `<label class="setting-row">
        <span>${label}</span>
        <input type="number" min="${min}" max="${max}" step="1"
          data-section="screensaver" data-key="${key}"
          value="${Number(screen[key])}">
      </label>`),
      ...[["background_color", "Achtergrondkleur"], ["text_color", "Tekstkleur"]]
        .map(([key, label]) => `<label class="setting-row">
          <span>${label}</span>
          <input type="color" data-section="screensaver" data-key="${key}"
            value="${this._escape(screen[key] || "#ffffff")}">
        </label>`),
    ].join("");
    const cameraFields = [
      ["width_percent", "Breedte popup (%)", 40, 100],
      ["height_percent", "Hoogte popup (%)", 40, 100],
      ["dim_percent", "Achtergrond verduisteren (%)", 0, 95],
    ].map(([key, label, min, max]) => `<label class="setting-row">
      <span>${label}</span>
      <input type="number" min="${min}" max="${max}" step="1"
        data-section="camera_popup" data-key="${key}"
        value="${Number(camera[key])}">
    </label>`).join("");
    return `
      <div class="settings-help">${responseText}</div>
      <div class="actions">
        <button class="refresh-settings" data-kiosk="${id}">Instellingen ophalen</button>
      </div>
      <h3>Screensaver</h3>
      <div class="settings-fields">${fields}</div>
      <div class="actions">
        <button class="save-settings" data-kiosk="${id}" data-section="screensaver">Opslaan</button>
        <button class="reset-settings" data-kiosk="${id}" data-section="screensaver">Herstellen</button>
      </div>
      <h3>Camera-popup</h3>
      <div class="settings-fields">${cameraFields}</div>
      <div class="actions">
        <button class="save-settings" data-kiosk="${id}" data-section="camera_popup">Opslaan</button>
        <button class="reset-settings" data-kiosk="${id}" data-section="camera_popup">Herstellen</button>
      </div>`;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _render() {
    if (!this.shadowRoot) return;

    const active = this.shadowRoot.activeElement;
    const focusKey = active?.dataset?.focusKey;
    const scrollTop = this.shadowRoot.scrollTop;
    const opened = [...this.shadowRoot.querySelectorAll("details[open]")]
      .map(el => `${el.className}:${el.dataset.kiosk || ""}`);
    for (const input of this.shadowRoot.querySelectorAll("[data-section][data-key]")) {
      const key = `${input.closest("details.settings")?.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
      this._view.drafts.set(key, input.type === "checkbox" ? input.checked : input.value);
    }

    const cards = this._kiosks.length
      ? this._kiosks.map((kiosk) => {
          const id = this._escape(kiosk.id);
          const availability = this._escape(kiosk.availability || "unknown");
          const status = kiosk.status || {};
          const battery = kiosk.battery || {};
          const state = String(kiosk.availability || "unknown").toLowerCase();
          const online = state === "online";
          const stateClass = online ? "online" : state === "offline" ? "offline" : "unknown";
          return `
            <article class="card">
              <div class="header">
                <div>
                  <h2>${id}</h2>
                  <div class="availability ${stateClass}" role="status" aria-label="Verbinding: ${availability}">
                    ${availability}
                  </div>
                </div>
                <div class="battery" aria-label="Batterij">${this._escape(battery.level ?? "—")}${battery.level == null ? "" : "%"}</div>
              </div>

              <dl>
                <dt>Camera</dt><dd>${this._escape(status.camera_state ?? "—")}</dd>
                <dt>Opladen</dt><dd>${this._escape(battery.charging ?? "—")}</dd>
                <dt>Batterijtemperatuur</dt><dd>${this._escape(battery.temperature ?? "—")}</dd>
              </dl>

              <details class="controls">
              <summary>Bediening</summary>
              <h3>Screensaver</h3>
              <div class="actions">
                <button data-kiosk="${id}" data-command="screensaver" data-value="ON">Tonen</button>
                <button data-kiosk="${id}" data-command="screensaver" data-value="OFF">Verbergen</button>
              </div>
              <details class="settings" data-kiosk="${id}">
                <summary>Tabletinstellingen</summary>
                ${this._settingsMarkup(kiosk)}
              </details>
              <h3>Deurbelcamera</h3>
              <div class="actions">
                <button data-kiosk="${id}" data-value="prewarm" aria-label="Camera voorladen">Voorladen</button>
                <button data-kiosk="${id}" data-value="show" aria-label="Camera tonen">Tonen</button>
                <button data-kiosk="${id}" data-value="hide" aria-label="Camera verbergen">Verbergen</button>
                <button data-kiosk="${id}" data-value="stop" aria-label="Camera stoppen">Stoppen</button>
              </div>
              </details>
            </article>`;
        }).join("")
      : `<div class="empty">Nog geen kiosken gevonden. Een kiosk verschijnt na een MQTT-statusbericht.</div>`;

    const availabilityMessage = this._error ? `<div class="error" role="alert">${this._escape(this._error)}</div>` : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          box-sizing: border-box;
          padding: clamp(12px, 3vw, 28px);
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        h1 { margin: 0 0 20px; font-size: 28px; display:flex; align-items:center; gap:12px; }
        .brand { width:34px; height:34px; object-fit:contain; }
        .error { margin: 12px 0; padding: 12px; border-inline-start: 4px solid var(--error-color, #b3261e); background: var(--card-background-color); }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(min(100%, 290px), 1fr));
          gap: 16px;
        }
        .card {
          background: var(--card-background-color);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.15));
          padding: 18px;
        }
        .header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        h2 { margin: 0; font-size: 20px; }
        h3 { margin: 18px 0 8px; font-size: 14px; font-weight: 600; }
        .availability { margin-top: 4px; font-size: 13px; text-transform: uppercase; }
        .online { color: var(--success-color, #43a047); }
        .offline { color: var(--error-color, #db4437); }
        .unknown { color: var(--secondary-text-color); }
        .battery { font-size: 24px; font-weight: 500; }
        dl { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; margin: 18px 0 0; }
        dt { color: var(--secondary-text-color); }
        dd { margin: 0; text-align: right; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; }
        button {
          border: none;
          border-radius: 18px;
          padding: 8px 14px;
          cursor: pointer;
          background: var(--primary-color);
          color: var(--text-primary-color, white);
          font: inherit;
        }
        button:active { transform: scale(.97); }
        button { min-height: 44px; }
        button:focus-visible, summary:focus-visible, input:focus-visible { outline: 3px solid var(--primary-color); outline-offset: 2px; }
        .empty { color: var(--secondary-text-color); padding: 24px 0; }
        details.settings { margin-top: 18px; padding: 12px 0; border-top: 1px solid var(--divider-color); }
        details.settings summary { cursor: pointer; font-size: 16px; font-weight: 600; margin-bottom: 12px; }
        .settings-help { font-size: 12px; color: var(--secondary-text-color); margin: 10px 0; }
        .settings-fields { display: flex; flex-direction: column; gap: 10px; margin: 12px 0; }
        .setting-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 14px; }
        .setting-row input[type=number] { width: 98px; }
        .setting-row input[type=color] { width: 50px; }
        .setting-row input { background: var(--input-fill-color, var(--card-background-color)); color: var(--primary-text-color);
          border: 1px solid var(--divider-color); border-radius: 6px; padding: 6px; }
        .settings button { background: var(--secondary-background-color, #333); }
        .settings button.save-settings { background: var(--primary-color); }
      </style>
      <h1><img class="brand" src="/ha_gecko_kiosk_static/icon.png" alt="">Gecko-kiosken</h1>
      ${availabilityMessage}
      <div class="grid">${cards}</div>
    `;

    for (const input of this.shadowRoot.querySelectorAll("[data-section][data-key]")) {
      const key = `${input.closest("details.settings")?.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
      if (this._view.drafts.has(key)) {
        if (input.type === "checkbox") input.checked = this._view.drafts.get(key);
        else input.value = this._view.drafts.get(key);
      }
      input.dataset.focusKey = `${input.closest("details.settings")?.dataset.kiosk}:${input.dataset.section}:${input.dataset.key}`;
    }
    for (const details of this.shadowRoot.querySelectorAll("details")) {
      if (opened.includes(`${details.className}:${details.dataset.kiosk || ""}`)) details.open = true;
    }
    this.shadowRoot.scrollTop = scrollTop;
    if (focusKey) this.shadowRoot.querySelector(`[data-focus-key="${CSS.escape(focusKey)}"]`)?.focus({preventScroll:true});

    this.shadowRoot.querySelectorAll("button[data-command], button[data-value]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          button.disabled = true;
          if (button.dataset.command) {
            await this._device(button.dataset.kiosk, button.dataset.command, button.dataset.value);
          } else {
            await this._camera(button.dataset.kiosk, button.dataset.value);
          }
          window.setTimeout(() => this._refresh(), 250);
        } catch (error) {
          console.error("Opdracht naar kiosk mislukt", error);
          this._error = "De opdracht kon niet worden verzonden. Controleer de integratiestatus en probeer opnieuw.";
          this._render();
        } finally {
          button.disabled = false;
        }
      });
    });
    this.shadowRoot.querySelectorAll(".refresh-settings").forEach(button => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await this._hass.callService("ha_gecko_kiosk", "get_settings", {kiosk: button.dataset.kiosk});
        } catch (error) {
          console.error("Kan kioskinstellingen niet ophalen", error);
          this._error = "Instellingen konden niet worden opgevraagd. Controleer de integratiestatus en probeer opnieuw.";
          this._render();
        } finally {
          button.disabled = false;
        }
      });
    });
    this.shadowRoot.querySelectorAll(".save-settings").forEach(button => {
      button.addEventListener("click", async () => {
        const section = button.dataset.section;
        const parent = button.closest("details.settings");
        const inputs = [...parent.querySelectorAll(`[data-section="${section}"][data-key]`)];
        if (inputs.some(x => !x.checkValidity())) {
          inputs.find(x => !x.checkValidity())?.reportValidity();
          return;
        }
        const payload = {kiosk: button.dataset.kiosk};
        for (const input of inputs) {
          payload[input.dataset.key] = input.type === "checkbox" ? input.checked
            : input.type === "number" ? Number(input.value) : input.value;
        }
        button.disabled = true;
        try {
          await this._hass.callService("ha_gecko_kiosk",
            section === "screensaver" ? "set_screensaver" : "set_camera_popup", payload);
          parent.open = false;
          // An HA service call only confirms MQTT publication, not tablet application.
          window.setTimeout(() => this._refresh(), 600);
        } catch (error) {
          console.error("Kan instellingen niet verzenden", error);
          this._error = "Instellingen konden niet worden verzonden. Je invoer is behouden; probeer opnieuw.";
          this._render();
        } finally {
          button.disabled = false;
        }
      });
    });
    this.shadowRoot.querySelectorAll(".reset-settings").forEach(button => {
      button.addEventListener("click", async () => {
        if (!window.confirm("Instellingen herstellen naar de oorspronkelijke kioskconfiguratie?")) return;
        button.disabled = true;
        try {
          await this._hass.callService("ha_gecko_kiosk", "reset_settings", {
            kiosk: button.dataset.kiosk, section: button.dataset.section,
          });
          button.closest("details.settings").open = false;
          window.setTimeout(() => this._refresh(), 600);
        } catch (error) {
          console.error("Kan instellingen niet herstellen", error);
          this._error = "Instellingen konden niet worden hersteld. Controleer de verbinding en probeer opnieuw.";
          this._render();
        } finally {
          button.disabled = false;
        }
      });
    });
  }
}

customElements.define("ha-gecko-kiosk-panel", HaGeckoKioskPanel);
