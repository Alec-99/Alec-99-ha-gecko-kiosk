# MQTT capability manifest, version 1

This document defines the generic capability advertisement shared by Gecko kiosk clients and the HA Gecko Kiosk integration. It contains no Android implementation details. A constrained client such as an ESP32 advertises only the capabilities it implements.

## Topic and payload

The device publishes a retained UTF-8 JSON document at `ha_kiosk/<device_id>/status/capabilities` after connecting and whenever its supported capability set changes. It uses the existing MQTT device identity and availability topic. The manifest is descriptive metadata; it never grants access or authorizes a caller.

```json
{
  "schema": 1,
  "protocol_version": 1,
  "capabilities": [
    "camera.external",
    "diagnostics.basic",
    "display.brightness",
    "display.power",
    "screensaver.activate"
  ],
  "resources": {
    "cameras": ["entry_cam", "yard"]
  }
}
```

`schema` versions this JSON structure. `protocol_version` versions the command and state contract. Both are positive integers. `capabilities` is an array of at most 64 unique or repeated strings matching `domain.feature` syntax (`[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+`); consumers deduplicate entries and ignore valid capabilities they do not recognize. Optional `resources.cameras` lists camera IDs only (never stream URLs); IDs use letters, digits, `.`, `_` or `-`, up to 64 characters. The panel renders camera actions for the advertised IDs. Payloads are limited to 4096 UTF-8 bytes.

The current integration supports schema 1 and protocol major 1. A malformed manifest or unsupported version is treated as incompatible and controls fail closed. A device that has not published a manifest is treated as a legacy client, preserving the existing controls and commands.

## Capability names

| Identifier | Meaning | Existing command/service mapping |
| --- | --- | --- |
| `camera.external` | Show a configured external camera | `ha_gecko_kiosk.camera` and camera popup |
| `screensaver.activate` | Show or hide the screensaver | `ha_gecko_kiosk.device`, `command: screensaver` |
| `screensaver.settings` | Read/change screensaver settings | `get_settings`, `set_screensaver`, `reset_settings` |
| `camera.popup_settings` | Configure the native camera popup | `set_camera_popup`, `reset_settings` |
| `notification.display` | Show or clear a screensaver notification | `ha_gecko_kiosk.notification` |
| `popup.confirmation` | Show a native confirmation dialog and receive its response | `ha_gecko_kiosk.popup`, `kind: confirmation` |
| `popup.message` | Show a native informational dialog | `ha_gecko_kiosk.popup`, `kind: message` |
| `display.power` | Change display power | `ha_gecko_kiosk.device`, `command: screen` |
| `display.brightness` | Change display brightness | `ha_gecko_kiosk.device`, `command: brightness` |
| `audio.volume` | Change media volume | `ha_gecko_kiosk.device`, `command: volume` |
| `audio.mute` | Mute/unmute media | `ha_gecko_kiosk.device`, `command: mute` |
| `command.acknowledged` | Accept expiring device command requests and publish correlated outcomes | `command/device/request` → `device/response` |
| `dashboard.reload` | Reload the hosted dashboard | `ha_gecko_kiosk.device`, `command: reload_dashboard` |
| `diagnostics.basic` | Publish generic health and connectivity status | Status/diagnostics only |

Capability means that the device implementation supports the operation. It does not promise the operation is ready now. For example, a display-power capability may be present while a required Android permission is missing; readiness and result reporting remain separate state. Camera URLs, credentials, device-local paths, and hardware-specific metrics do not belong in this manifest.

## Compatibility and rollout

The manifest is additive. It does not alter existing command topics or payloads. HA keeps all controls for clients with no manifest. For an explicit compatible manifest, the management panel renders only controls whose capability is present; service calls for unsupported capability mappings are rejected before MQTT publish. Unknown valid capability identifiers are retained for diagnostics but do not create arbitrary controls or topics. Invalid or major-version-incompatible manifests disable mapped commands until a compatible manifest is published.

New protocol behavior must first land with contract tests for both an Android Gecko manifest and a synthetic subset profile. Do not remove a legacy command or change its payload in the same rollout. Introduce a new protocol major only with an explicit compatibility period and an upgrade/rollback matrix.

## Privacy-safe test profiles

Full Gecko profile:

The canonical copy used by contract tests is `docs/fixtures/capability_manifest_v1.json`; the private app repository keeps an identical test resource and verifies its generated manifest against it. The fixture uses synthetic camera IDs only.

```json
{"schema":1,"protocol_version":1,"capabilities":["audio.mute","audio.volume","camera.external","camera.popup_settings","command.acknowledged","dashboard.reload","diagnostics.basic","display.brightness","display.power","notification.display","popup.confirmation","popup.message","screensaver.activate","screensaver.settings"],"resources":{"cameras":["entry_cam","yard"]}}
```

Small display profile (suitable as a synthetic constrained-device test):

```json
{"schema":1,"protocol_version":1,"capabilities":["diagnostics.basic","display.power"]}
```

The Gecko app's brightness command accepts 1–100 percent; media volume accepts 0–100 percent. Constrained devices may define their own supported capability subset, but the v1 Gecko mapping keeps these established ranges.

## Acknowledged device commands

Clients that advertise `command.acknowledged` accept non-retained QoS 1 JSON on `ha_kiosk/<device_id>/command/device/request`:

```json
{"schema":1,"request_id":"0123456789abcdef0123456789abcdef","expires_at_ms":1794000060000,"command":"brightness","value":"62"}
```

The app rejects expired or unsupported requests and publishes a non-retained QoS 1 response on `ha_kiosk/<device_id>/device/response` with the same request ID and one of `applied`, `rejected`, `unsupported`, `unavailable`, `expired` or `error`. The integration accepts a response only for an outstanding request sent to the same device; unmatched and late responses are ignored. Its panel reports a 65-second timeout. Clients without this capability continue to receive the original individual command topic and payload, so rollout does not break existing Gecko clients.

The updated Gecko development client also checks expiry immediately before device execution. It suppresses duplicate pending requests and replays completed outcomes for identical requests. Reusing an ID with different arguments is rejected. Its process-local ledger holds at most 128 requests and retains each until two minutes after expiry; a full ledger rejects new requests instead of evicting live duplicate protection. This protection is not persisted across an Android process restart. Older clients advertising the acknowledgement capability may lack this added duplicate protection; it is not a new protocol version or a durable exactly-once guarantee.

## Version compatibility and recovery

App versions, integration versions and the MQTT protocol are independent.
Integration `0.2.2` understands schema 1 / protocol 1. The Gecko
`0.8.2-gecko-experiment` development line implements this protocol, but a
version label alone does not prove which optional features a build includes.
Use the retained manifest from the running client.

| Client advertisement | Integration 0.2.2 behavior |
| --- | --- |
| No manifest (legacy client) | Existing raw command topics and payloads |
| Compatible v1 manifest without `command.acknowledged` | Only advertised controls; existing raw commands |
| Compatible v1 manifest with `command.acknowledged` | Advertised device controls use expiring requests and correlated outcomes |
| Compatible subset profile | Only its advertised capabilities; no Android-only requirement |
| Malformed manifest or unsupported major | Mapped controls disabled until compatible metadata arrives |

An acknowledged MQTT publish is not proof of device execution. Wait for the
device response or the panel's timeout. Duplicate protection is process-local;
do not blindly resend an uncertain command after an app restart.

### Upgrade

1. Back up the installed integration version and the app's private configuration.
   Keep credentials and backups outside this public repository.
2. Upgrade the HA integration, restart Home Assistant and reload the browser.
   Confirm existing legacy controls before changing the client.
3. Install only an approved APK signed with the expected key. A successful
   build or downloadable CI artifact does not establish physical-device behavior.
4. Confirm availability, the live capability manifest and a low-impact command
   with its state/result. Validate camera, settings and display permissions
   separately before replacing an existing installation.

### Rollback

Restore the previous integration source through the same installation method,
restart Home Assistant and reload the browser. Restoring an Android APK also
depends on its signing key and version code: Android may refuse a lower version
code. Do not uninstall the app to force a downgrade without a verified private
backup; uninstalling can remove settings.

When reverting to a client that never publishes a manifest, first stop the newer
client and remove **only** its retained `ha_kiosk/<device_id>/status/capabilities`
record using the broker's retained-message management. Then restart Home
Assistant to clear the integration's in-memory capability model before starting
the legacy client. An empty payload delivered to the running integration is
currently treated as an invalid manifest; it does not immediately enable legacy
mode. Leaving a newer retained manifest behind can incorrectly select the
acknowledged route for an older client.

Do not remove legacy topics during this rollout. Live HA/HACS installation,
physical tablet behavior and an actual ESP32 client still require separate
validation; a synthetic subset profile is not firmware validation.
