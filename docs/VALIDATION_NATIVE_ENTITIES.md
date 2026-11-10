# Native HA devices and entities — 10 November 2026

Integration 0.3.0 was exercised against a disposable Home Assistant 2026.11.1
instance and an isolated loopback MQTT broker, with fictional devices only.

`tests/runtime/check_native_entities.py` verifies:

- One integration device and 18 capability/state-evidenced entities for a generic
  kiosk without MQTT discovery, including version metadata.
- State changes, non-optimistic controls, QoS 1 non-retained expiring commands,
  correlated acknowledgements, offline handling and capability revocation.
- Config-entry reload with retained state and stable entity IDs.
- Real MQTT device discovery: existing battery entity reused, physical identity
  linked across HA's per-config-entry devices. A short settlement window avoids
  a duplicate native entity while MQTT asynchronously registers discovery.

The test requires a disposable loopback HA URL, broker, `HA_TEST_TOKEN` admin
credential in the environment, aiohttp and paho-mqtt. It mutates only named QA
fixtures and reloads this integration. Do not run it against a household instance.
Credentials and runtime captures are not stored in this repository.

Fast CI separately checks protocol contracts and frontend behavior. No physical
tablet was available. App reload stability and APK installation are separate
Android validation concerns.
