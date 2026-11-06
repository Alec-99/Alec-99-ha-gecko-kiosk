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
