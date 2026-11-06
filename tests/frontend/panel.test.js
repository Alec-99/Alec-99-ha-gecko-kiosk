const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { JSDOM } = require('jsdom');

const source = readFileSync('custom_components/ha_gecko_kiosk/frontend/ha-gecko-kiosk-panel.js', 'utf8');
let dom;
let panel;
let calls;
let list;

function kiosk(id, availability = 'online') {
  return {
    id, availability,
    status: { camera_state: 'hidden' },
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
}

function setup(kiosks = []) {
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
  dom.window.document.body.append(panel);
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
  setup([kiosk('alpha', 'offline'), kiosk('beta', 'unknown')]);
  assert.equal(panel.shadowRoot.querySelectorAll('.kiosk-card').length, 2);
  assert.ok(panel.shadowRoot.querySelector('.pill.offline'));
  assert.ok(panel.shadowRoot.querySelector('.pill.unknown'));
});

test('navigation exposes distinct overview, controls, settings and diagnostics sections', async () => {
  setup([kiosk('alpha')]);
  assert.equal(panel.shadowRoot.querySelectorAll('nav [data-action="tab"]').length, 4);
  await click('[data-tab="controls"]');
  assert.match(panel.shadowRoot.textContent, /Deurbelcamera/);
  await click('[data-tab="settings"]');
  assert.match(panel.shadowRoot.textContent, /Schermbeveiliging/);
  assert.match(panel.shadowRoot.textContent, /Camera-popup/);
  await click('[data-tab="diagnostics"]');
  assert.match(panel.shadowRoot.textContent, /Batterijtemperatuur/);
  assert.equal(panel.shadowRoot.querySelector('[aria-current="page"]').dataset.tab, 'diagnostics');
});

test('existing screen and camera actions call the original HA services and payloads', async () => {
  setup([kiosk('alpha')]);
  await click('[data-tab="controls"]');
  await click('[data-action="device"][data-value="ON"]');
  await click('[data-action="device"][data-value="OFF"]');
  for (const action of ['prewarm', 'show', 'hide', 'stop']) await click(`[data-action="camera"][data-value="${action}"]`);
  assert.deepEqual(calls.map(([domain, service]) => [domain, service]), [
    ['ha_gecko_kiosk','device'], ['ha_gecko_kiosk','device'],
    ...Array(4).fill(['ha_gecko_kiosk','camera']),
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][2])), { kiosk: 'alpha', command: 'screensaver', value: 'ON' });
  assert.deepEqual(JSON.parse(JSON.stringify(calls[2][2])), { kiosk: 'alpha', action: 'prewarm', camera: 'doorbell' });
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
  item.last_settings_response = { request_id: 'r1', status: 'rejected', detail: 'invalid' };
  panel._render(); assert.match(panel.shadowRoot.textContent, /Geweigerd: invalid/);
  item.last_settings_response = null; item.last_settings_request_at_ms = Date.now() - 66_000;
  panel._render(); assert.match(panel.shadowRoot.textContent, /time-out na 65 seconden/);
});

test('service errors are visible and escaped MQTT identifiers are safe', async () => {
  setup([kiosk('<img src=x onerror=alert(1)>')]);
  assert.equal(panel.shadowRoot.querySelector('img[onerror]'), null);
  panel._hass.callService = async () => { throw new Error('<denied>'); };
  await click('[data-tab="controls"]');
  await click('[data-action="device"][data-value="ON"]');
  assert.match(panel.shadowRoot.querySelector('[role="alert"]').textContent, /denied/);
  assert.equal(panel.shadowRoot.querySelector('[role="alert"] b'), null);
});

test('list request failures are reported inside the panel', async () => {
  setup([kiosk('alpha')]);
  panel._hass.connection.sendMessagePromise = async () => { throw new Error('offline'); };
  await panel._refresh();
  assert.match(panel.shadowRoot.querySelector('[role="alert"]').textContent, /Kioskgegevens konden niet worden geladen/);
});
