const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { JSDOM } = require('jsdom');

const source = readFileSync('custom_components/ha_gecko_kiosk/frontend/ha-gecko-kiosk-panel.js', 'utf8');
let dom;
let panel;
let calls;
let list;

function kiosk(id, availability = 'online', capabilities) {
  const device = {
    id, availability,
    status: { camera_state: 'hidden' },
    display: { power: 'ON', brightness_percent: '62', power_control_ready: 'false' },
    audio: { volume_percent: '31', muted: 'false' },
    diagnostics: { app_version: '1.2.3', watchdog_status: 'healthy', watchdog_restart_count: '2', mqtt_reconnect_count: '1' },
    battery: { level: 87, charging: false, temperature: 29 },
    settings: {
      screensaver: {
        enabled: true, inactivity_timeout_seconds: 300, show_clock: true,
        show_date: false, consume_wake_touch: true, clock_text_size_sp: 48,
        date_text_size_sp: 24, clock_update_interval_seconds: 60,
        background_color: '#000000', text_color: '#ffffff',
      },
      camera_popup: { width_percent: 80, height_percent: 70, dim_percent: 40 },
    },
  };
  if (capabilities !== undefined) device.capabilities = capabilities;
  return device;
}

function setup(kiosks = []) {
  dom?.window.close();
  dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://localhost' });
  dom.window.console.error = () => {};
  dom.window.setInterval = () => 1;
  dom.window.clearInterval = () => {};
  dom.window.confirm = () => true;
  dom.window.eval(source);
  panel = dom.window.document.createElement('ha-gecko-kiosk-panel');
  calls = [];
  list = kiosks;
  panel._hass = {
    callService: async (...args) => calls.push(args),
    connection: { sendMessagePromise: async () => ({ kiosks: list }) },
  };
  panel._kiosks = kiosks;
  panel._selectedKiosk = kiosks[0]?.id || '';
  panel._render();
  const hass = panel._hass;
  panel._hass = null;
  dom.window.document.body.append(panel);
  panel._hass = hass;
}

async function click(selector) {
  const element = panel.shadowRoot.querySelector(selector);
  assert.ok(element, `Expected element: ${selector}`);
  element.click();
  await new Promise(resolve => setTimeout(resolve, 0));
}

beforeEach(() => {});
afterEach(() => dom?.window.close());

test('overview handles empty, single and multiple kiosks with truthful availability', async () => {
  setup([]);
  assert.match(panel.shadowRoot.textContent, /Nog geen kiosken/);
  setup([kiosk('alpha')]);
  assert.equal(panel.shadowRoot.querySelectorAll('.kiosk-card').length, 1);
  assert.match(panel.shadowRoot.textContent, /online/);
  assert.match(panel.shadowRoot.querySelector('style').textContent, /color-scheme:dark/);
  assert.match(panel.shadowRoot.querySelector('style').textContent, /--primary-background-color:#171b21/);
  assert.match(panel.shadowRoot.querySelector('style').textContent, /--primary-color:#ff8a00/);
  setup([kiosk('alpha', 'offline'), kiosk('beta', 'unknown')]);
  assert.equal(panel.shadowRoot.querySelectorAll('.kiosk-card').length, 2);
  assert.ok(panel.shadowRoot.querySelector('.pill.offline'));
  assert.ok(panel.shadowRoot.querySelector('.pill.unknown'));
});

test('navigation exposes distinct overview, controls, settings and updates and diagnostics sections', async () => {
  setup([kiosk('alpha')]);
  assert.equal(panel.shadowRoot.querySelectorAll('nav [data-action="tab"]').length, 5);
  await click('[data-tab="controls"]');
  assert.match(panel.shadowRoot.textContent, /Camera: doorbell/);
  await click('[data-tab="settings"]');
  assert.match(panel.shadowRoot.textContent, /Schermbeveiliging/);
  assert.match(panel.shadowRoot.textContent, /Camera-popup/);
  await click('[data-tab="diagnostics"]');
  assert.match(panel.shadowRoot.textContent, /Batterijtemperatuur/);
  assert.match(panel.shadowRoot.textContent, /1\.2\.3/);
  assert.match(panel.shadowRoot.textContent, /healthy/);
  assert.match(panel.shadowRoot.textContent, /MQTT-reconnects/);
  assert.equal(panel.shadowRoot.querySelector('[aria-current="page"]').dataset.tab, 'diagnostics');
});

test('existing screen and camera actions call the original HA services and payloads', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="controls"]');
  await click('[data-action="device"][data-command="screensaver"][data-value="ON"]');
  await click('[data-action="device"][data-command="screensaver"][data-value="OFF"]');
  for (const action of ['prewarm', 'show', 'hide', 'stop']) await click(`[data-action="camera"][data-value="${action}"]`);
  assert.deepEqual(calls.map(([domain, service]) => [domain, service]), [
    ['ha_gecko_kiosk','device'], ['ha_gecko_kiosk','device'],
    ...Array(4).fill(['ha_gecko_kiosk','camera']),
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), { kiosk: 'alpha', command: 'screensaver', value: 'ON' });
  assert.deepEqual(JSON.parse(JSON.stringify(calls[2][2])), { kiosk: 'alpha', action: 'prewarm', camera: 'doorbell' });
});

test('capability manifests show only supported controls and legacy kiosks keep both controls', async () => {
  setup([kiosk('legacy')]);
  await click('[data-tab="controls"]');
  assert.ok(panel.shadowRoot.querySelector('[data-action="device"][data-command="screensaver"]'));
  assert.ok(panel.shadowRoot.querySelector('[data-action="camera"]'));

  setup([kiosk('display-only', 'online', {
    compatible: true, protocol_version: 1, capabilities: ['display.power', 'vendor.custom'],
  })]);
  await click('[data-tab="controls"]');
  assert.equal(panel.shadowRoot.querySelector('[data-action="device"][data-command="screensaver"]'), null);
  assert.equal(panel.shadowRoot.querySelector('[data-action="camera"]'), null);
  assert.ok(panel.shadowRoot.querySelector('[data-action="device"][data-command="screen"]'));
  await click('[data-tab="diagnostics"]');
  assert.match(panel.shadowRoot.textContent, /display\.power/);

  setup([kiosk('screensaver-only', 'online', {
    compatible: true, protocol_version: 1,
    capabilities: ['screensaver.activate', 'screensaver.settings'],
  })]);
  await click('[data-tab="controls"]');
  assert.ok(panel.shadowRoot.querySelector('[data-action="device"][data-command="screensaver"]'));
  assert.equal(panel.shadowRoot.querySelector('[data-action="camera"]'), null);
  await click('[data-tab="settings"]');
  assert.ok(panel.shadowRoot.querySelector('[data-section="screensaver"]'));
  assert.equal(panel.shadowRoot.querySelector('[data-section="camera_popup"]'), null);
});

test('generic display and audio capabilities expose controls, honor readiness and preserve slider drafts', async () => {
  const device = kiosk('generic', 'online', {
    compatible: true, protocol_version: 1,
    capabilities: ['display.power', 'display.brightness', 'audio.volume', 'audio.mute', 'dashboard.reload'],
  });
  setup([device]);
  await click('[data-tab="controls"]');
  assert.ok(panel.shadowRoot.querySelector('[data-action="device"][data-command="screen"][data-value="ON"]'));
  assert.equal(panel.shadowRoot.querySelector('[data-action="device"][data-command="screen"][data-value="OFF"]').disabled, true);
  assert.equal(panel.shadowRoot.querySelectorAll('[data-control-key]').length, 2);
  assert.equal(panel.shadowRoot.querySelector('[data-control-key="brightness_percent"]').min, '1');
  assert.equal(panel.shadowRoot.querySelector('[data-control-key="volume_percent"]').min, '0');
  assert.ok(panel.shadowRoot.querySelector('[data-command="reload_dashboard"]'));
  assert.equal(panel.shadowRoot.querySelector('[data-command="mute"]').dataset.value, 'ON');
  device.audio.muted = 'ON'; panel._render();
  assert.equal(panel.shadowRoot.querySelector('[data-command="mute"]').dataset.value, 'OFF');
  const brightness = panel.shadowRoot.querySelector('[data-control-key="brightness_percent"]');
  brightness.value = '77'; brightness.dispatchEvent(new dom.window.Event('input', { bubbles: true })); brightness.focus();
  list = [kiosk('generic', 'online', device.capabilities)];
  await panel._refresh();
  const restored = panel.shadowRoot.querySelector('[data-control-key="brightness_percent"]');
  assert.equal(restored.value, '77');
  assert.equal(panel.shadowRoot.activeElement, restored);
  await click('[data-action="control"][data-command="brightness"]');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), {
    kiosk: 'generic', command: 'brightness', value: '77',
  });
  await click('[data-action="device"][data-command="mute"]');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[1][2])), {
    kiosk: 'generic', command: 'mute', value: 'ON',
  });
});

test('an unsupported protocol manifest disables controls and explains why', async () => {
  setup([kiosk('future-device', 'online', {
    compatible: false, protocol_version: 2, capabilities: [],
  })]);
  await click('[data-tab="controls"]');
  assert.equal(panel.shadowRoot.querySelectorAll('.control-group').length, 0);
  assert.match(panel.shadowRoot.textContent, /niet-ondersteunde capabilityversie/);
  await click('[data-tab="settings"]');
  assert.match(panel.shadowRoot.textContent, /geen extern wijzigbare instellingen/);
  await click('[data-tab="diagnostics"]');
  assert.equal(panel.shadowRoot.querySelector('[data-action="get-settings"]'), null);
});

test('configured camera resources are generic and escaped before rendering commands', async () => {
  setup([kiosk('camera-device', 'online', {
    compatible: true, protocol_version: 1,
    capabilities: ['camera.external'], resources: { cameras: ['entry_cam', 'yard'] },
  })]);
  await click('[data-tab="controls"]');
  assert.deepEqual([...panel.shadowRoot.querySelectorAll('[data-action="camera"][data-value="show"]')]
    .map(button => button.dataset.camera), ['entry_cam', 'yard']);
  await click('[data-action="camera"][data-camera="yard"][data-value="show"]');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), {
    kiosk: 'camera-device', action: 'show', camera: 'yard',
  });
});

test('settings drafts and focus survive polling; validation and per-section calls remain intact', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="settings"]');
  await click('[data-tab="diagnostics"]');
  await click('[data-action="get-settings"]');
  assert.equal(calls[0][1], 'get_settings');
  await click('[data-tab="settings"]');
  const field = panel.shadowRoot.querySelector('[data-key="inactivity_timeout_seconds"]');
  field.value = '420'; field.focus();
  list = [kiosk('alpha')];
  await panel._refresh();
  const restored = panel.shadowRoot.querySelector('[data-key="inactivity_timeout_seconds"]');
  assert.equal(restored.value, '420');
  assert.equal(panel.shadowRoot.activeElement, restored);
  restored.value = '4';
  await click('[data-action="save"][data-section="screensaver"]');
  assert.equal(calls.length, 1, 'out of range input must not send');
  restored.value = '420';
  await click('[data-action="save"][data-section="screensaver"]');
  assert.equal(calls[1][1], 'set_screensaver');
  assert.equal(calls[1][2].inactivity_timeout_seconds, 420);
  await click('[data-action="reset"][data-section="camera_popup"]');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[2].slice(1))), ['reset_settings', { kiosk: 'alpha', section: 'camera_popup' }]);
  await click('[data-action="save"][data-section="camera_popup"]');
  assert.equal(calls[3][1], 'set_camera_popup');
  assert.equal(calls[3][2].width_percent, 80);
});

test('settings acknowledgement distinguishes waiting, applied, rejected and timed out', async () => {
  setup([kiosk('alpha')]);
  const item = panel._selected();
  item.last_settings_request = 'r1';
  item.last_settings_request_at_ms = Date.now();
  panel._tab = 'diagnostics'; panel._render();
  assert.match(panel.shadowRoot.textContent, /wachten op bevestiging/);
  item.last_settings_response = { request_id: 'r1', status: 'applied' };
  panel._render(); assert.match(panel.shadowRoot.textContent, /Bevestigd door de tablet/);
  item.last_settings_response = { request_id: 'r1', status: 'error', detail: 'invalid' };
  panel._render(); assert.match(panel.shadowRoot.textContent, /Geweigerd: invalid/);
  item.last_settings_response = null; item.last_settings_request_at_ms = Date.now() - 66_000;
  panel._render(); assert.match(panel.shadowRoot.textContent, /time-out na 65 seconden/);
});

test('device acknowledgements distinguish waiting, applied, rejected and timed out', async () => {
  setup([kiosk('alpha')]);
  const item = panel._selected();
  item.last_device_request = 'd1';
  item.last_device_request_at_ms = Date.now();
  panel._tab = 'diagnostics'; panel._render();
  assert.match(panel.shadowRoot.textContent, /wachten op tabletbevestiging/);
  item.last_device_response = { request_id: 'd1', status: 'applied' };
  panel._render(); assert.match(panel.shadowRoot.textContent, /Bevestigd door de tablet/);
  item.last_device_response = { request_id: 'd1', status: 'unavailable', detail: 'device_admin_required' };
  panel._tab = 'controls'; panel._render();
  assert.match(panel.shadowRoot.querySelector('[role="status"]').textContent, /device_admin_required/);
  panel._tab = 'diagnostics';
  panel._render(); assert.match(panel.shadowRoot.textContent, /Tijdelijk niet beschikbaar.*device_admin_required/);
  item.last_device_response = null; item.last_device_request_at_ms = Date.now() - 66_000;
  panel._render(); assert.match(panel.shadowRoot.textContent, /time-out na 65 seconden/);
});

test('service errors are visible and escaped MQTT identifiers are safe', async () => {
  setup([kiosk('<img src=x onerror=alert(1)>')]);
  assert.equal(panel.shadowRoot.querySelector('img[onerror]'), null);
  panel._hass.callService = async () => { throw new Error('<denied>'); };
  await click('[data-tab="controls"]');
  await click('[data-action="device"][data-value="ON"]');
  assert.match(panel.shadowRoot.querySelector('[role="alert"]:not([hidden])').textContent, /denied/);
  assert.equal(panel.shadowRoot.querySelector('[role="alert"] b'), null);
});

test('list request failures are reported inside the panel', async () => {
  setup([kiosk('alpha')]);
  panel._hass.connection.sendMessagePromise = async () => { throw new Error('offline'); };
  await panel._refresh();
  assert.match(panel.shadowRoot.querySelector('[role="alert"]:not([hidden])').textContent, /Kioskgegevens konden niet worden geladen/);
});

test('polling updates untouched fields without replacing the editor or overwriting dirty values', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="settings"]');
  const dirty = panel.shadowRoot.querySelector('[data-key="clock_text_size_sp"]');
  dirty.value = '99'; dirty.focus();
  const untouched = panel.shadowRoot.querySelector('[data-key="width_percent"]');
  list = [kiosk('alpha')];
  list[0].settings.camera_popup.width_percent = 90;
  await panel._refresh();
  assert.equal(panel.shadowRoot.querySelector('[data-key="clock_text_size_sp"]'), dirty);
  assert.equal(dirty.value, '99');
  assert.equal(panel.shadowRoot.activeElement, dirty);
  assert.equal(untouched.value, '90');
  await click('[data-action="discard"][data-section="screensaver"]');
  assert.equal(dirty.value, '48', 'discard adopts tablet values without sending MQTT');
  assert.equal(calls.length, 0);
});

test('a focused but untouched field adopts a newer tablet value without becoming a draft', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="settings"]');
  const field = panel.shadowRoot.querySelector('[data-key="width_percent"]');
  field.focus();
  list = [kiosk('alpha')];
  list[0].settings.camera_popup.width_percent = 90;
  await panel._refresh();
  await panel._refresh();
  assert.equal(panel.shadowRoot.querySelector('[data-key="width_percent"]'), field);
  assert.equal(field.value, '90');
  assert.equal(panel.shadowRoot.activeElement, field);
  assert.equal(panel._drafts.has('alpha:camera_popup:width_percent'), false);
});

test('MQTT charging strings false and unknown do not imply charging', () => {
  setup([kiosk('alpha')]);
  assert.equal(panel._chargingText('false'), 'Niet aan het opladen');
  assert.equal(panel._chargingText('true'), 'Opladen');
  assert.equal(panel._chargingText('unknown'), 'Oplaadstatus onbekend');
});

test('load errors clear after recovery while retaining the same settings editor', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="settings"]');
  const field = panel.shadowRoot.querySelector('[data-key="width_percent"]');
  const original = panel._hass.connection.sendMessagePromise;
  panel._hass.connection.sendMessagePromise = async () => { throw new Error('offline'); };
  await panel._refresh();
  assert.equal(panel.shadowRoot.querySelector('[data-load-error]').hidden, false);
  panel._hass.connection.sendMessagePromise = original;
  await panel._refresh();
  assert.equal(panel.shadowRoot.querySelector('[data-load-error]').hidden, true);
  assert.equal(panel.shadowRoot.querySelector('[data-key="width_percent"]'), field);
});

test('a pending HA service call cannot be submitted twice', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="controls"]');
  let complete;
  panel._hass.callService = () => { calls.push('call'); return new Promise(resolve => { complete = resolve; }); };
  await click('[data-action="camera"][data-value="show"]');
  assert.equal(panel.shadowRoot.querySelector('[data-action="camera"]').disabled, true);
  await click('[data-action="camera"][data-value="show"]');
  assert.equal(calls.length, 1);
  complete();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(panel.shadowRoot.querySelector('[data-action="camera"]').disabled, false);
});

test('polling restarts when the component is reconnected without a new hass assignment', async () => {
  setup([kiosk('alpha')]);
  let starts = 0, stops = 0;
  dom.window.setInterval = () => ++starts;
  dom.window.clearInterval = () => ++stops;
  panel.hass = panel._hass;
  panel.remove();
  dom.window.document.body.append(panel);
  assert.equal(starts, 2);
  assert.equal(stops, 1);
  await new Promise(resolve => setTimeout(resolve, 0));
});

test('polling retains navigation focus and scroll positions in a scrolling HA container', async () => {
  setup([kiosk('alpha')]);
  const container = dom.window.document.createElement('main');
  dom.window.document.body.append(container);
  container.append(panel);
  await new Promise(resolve => setTimeout(resolve, 0));
  const nav = panel.shadowRoot.querySelector('nav');
  nav.scrollLeft = 80;
  container.scrollTop = 240;
  panel.shadowRoot.querySelector('[data-tab="diagnostics"]').focus();
  await panel._refresh();
  assert.equal(container.scrollTop, 240);
  assert.equal(panel.shadowRoot.querySelector('nav').scrollLeft, 80);
  assert.equal(panel.shadowRoot.activeElement.dataset.tab, 'diagnostics');
});


function otaDevice(id = 'alpha', version = 17) {
  const device = kiosk(id, 'online', { compatible: true, capabilities: ['ota.install'] });
  device.ota = { status: 'idle', version_code: version, version_name: '0.8.6-test', progress: 0 };
  return device;
}

function chooseApk(name = 'kiosk.apk', size = 1024) {
  const file = new dom.window.File(['synthetic browser fixture'], name, { type: 'application/vnd.android.package-archive' });
  Object.defineProperty(file, 'size', { value: size });
  const input = panel.shadowRoot.querySelector('[data-apk-file]');
  Object.defineProperty(input, 'files', { configurable: true, value: [file] });
  input.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  return file;
}

function uploadMetadata() { return { upload_id: 'a'.repeat(32), version_name: '0.8.7-test', version_code: 18, size: 1024 }; }

test('APK upload uses HA authentication, reads metadata and installs only after an explicit target action', async () => {
  setup([otaDevice()]);
  const requests = [];
  panel._hass.fetchWithAuth = async (path, options) => {
    requests.push([path, options]);
    return { ok: true, json: async () => path.endsWith('ota_upload') ? uploadMetadata() : { status: 'requested' } };
  };
  panel._hass.connection.sendMessagePromise = async () => ({ kiosks: list, ota_upload: panel._otaUpload });
  await click('[data-tab="updates"]');
  assert.equal(panel.shadowRoot.querySelector('[data-action="ota-upload"]').disabled, true);
  const file = chooseApk();
  await click('[data-action="ota-upload"]');
  assert.equal(requests.length, 1, 'Uploading must not automatically install');
  assert.equal(requests[0][0], '/api/ha_gecko_kiosk/ota_upload');
  assert.equal(requests[0][1].body, file);
  assert.equal(requests[0][1].headers['Content-Type'], 'application/vnd.android.package-archive');
  assert.match(panel.shadowRoot.textContent, /0\.8\.7-test/);
  assert.equal(panel.shadowRoot.querySelector('[data-action="ota-install"]').disabled, false);
  await click('[data-action="ota-install"]');
  assert.equal(requests[1][0], '/api/ha_gecko_kiosk/ota_install');
  assert.deepEqual(JSON.parse(requests[1][1].body), { kiosk: 'alpha', upload_id: 'a'.repeat(32) });
  assert.equal(calls.length, 0, 'No legacy service should bypass the upload selection');
  assert.match(panel.shadowRoot.textContent, /Update aangevraagd/);
});

test('APK selection and file input survive polling; displayed progress follows the selected kiosk', async () => {
  setup([otaDevice(), otaDevice('beta')]);
  panel._otaUpload = uploadMetadata();
  panel._hass.connection.sendMessagePromise = async () => ({ kiosks: list, ota_upload: uploadMetadata() });
  await click('[data-tab="updates"]');
  const input = panel.shadowRoot.querySelector('[data-apk-file]');
  const file = chooseApk('<img onerror=alert(1)>.apk');
  list[0].ota = { ...list[0].ota, status: 'downloading', progress: 35 };
  await panel._refresh();
  assert.equal(panel.shadowRoot.querySelector('[data-apk-file]'), input);
  assert.equal(panel._apkFile, file);
  assert.equal(panel.shadowRoot.querySelector('[data-apk-filename] img'), null);
  assert.match(panel.shadowRoot.querySelector('[data-ota-status]').textContent, /35%/);
  const picker = panel.shadowRoot.querySelector('[data-ota-kiosk]');
  picker.value = 'beta'; picker.dispatchEvent(new dom.window.Event('change'));
  assert.equal(panel._selectedKiosk, 'beta');
  assert.match(panel.shadowRoot.querySelector('[data-action="ota-install"]').textContent, /beta/);
  assert.equal(panel.shadowRoot.querySelector('[data-action="ota-install"]').disabled, false);
});

test('APK controls reject other file types, oversized files, offline and legacy clients, downgrades and busy installers', async () => {
  setup([otaDevice()]);
  await click('[data-tab="updates"]');
  for (const [name, size] of [['archive.zip', 100], ['app.apk', 0], ['app.apk', 256*1024*1024+1]]) {
    chooseApk(name, size);
    assert.equal(panel._apkFile, null);
    assert.equal(panel.shadowRoot.querySelector('[data-action="ota-upload"]').disabled, true);
  }
  panel._otaUpload = uploadMetadata();
  for (const device of [kiosk('alpha'), { ...otaDevice(), availability: 'offline' }, otaDevice('alpha', 18),
                        { ...otaDevice(), ota: { status: 'awaiting_confirmation', version_code: 17 } }]) {
    panel._kiosks = [device]; panel._updateOta();
    assert.equal(panel.shadowRoot.querySelector('[data-action="ota-install"]').disabled, true);
  }
});

test('APK errors are escaped, previous upload stays usable and a pending upload cannot be submitted twice', async () => {
  setup([otaDevice()]);
  panel._otaUpload = uploadMetadata();
  await click('[data-tab="updates"]');
  chooseApk();
  let complete;
  let requests = 0;
  panel._hass.fetchWithAuth = () => { requests++; return new Promise(resolve => { complete = resolve; }); };
  const uploading = panel._uploadApk();
  await panel._uploadApk();
  assert.equal(requests, 1);
  assert.equal(panel.shadowRoot.querySelector('[data-upload-progress]').hidden, false);
  complete({ ok: false, json: async () => ({ message: '<img src=x onerror=alert(1)> Ongeldige APK' }) });
  await uploading;
  assert.equal(panel.shadowRoot.querySelector('[role="alert"] img'), null);
  assert.match(panel.shadowRoot.textContent, /Ongeldige APK/);
  assert.equal(panel._otaUpload.version_code, 18);
  assert.equal(panel.shadowRoot.querySelector('[data-action="ota-install"]').disabled, false);
});


test('OTA reports distinguish transfer, verification and Android install failures with the exact code', async () => {
  const device = otaDevice();
  setup([device]);
  await click('[data-tab="updates"]');
  for (const [detail, text] of [['download_failed', 'HA-URL'], ['verification_failed', 'ondertekening'], ['installer_failed', 'installatierechten'], ['timeout', 'niet op tijd']]) {
    device.ota = { ...device.ota, status: 'error', detail };
    panel._updateOta();
    assert.match(panel.shadowRoot.querySelector('[data-ota-status]').textContent, new RegExp(detail));
    assert.match(panel.shadowRoot.querySelector('[data-ota-status]').textContent, new RegExp(text));
  }
  await click('[data-tab="diagnostics"]');
  assert.match(panel.shadowRoot.textContent, /OTA-foutcode/);
  assert.match(panel.shadowRoot.textContent, /timeout/);
});

test('unknown OTA error text is not reflected in the update message', async () => {
  const device = otaDevice();
  device.ota = { ...device.ota, status: 'error', detail: '<img src=x onerror=alert(1)> https://example.invalid/private' };
  setup([device]);
  await click('[data-tab="updates"]');
  assert.doesNotMatch(panel.shadowRoot.querySelector('[data-ota-status]').textContent, /private|<img/);
  assert.equal(panel.shadowRoot.querySelector('[data-ota-status] img'), null);
});
