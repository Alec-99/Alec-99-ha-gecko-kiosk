# Browser APK upload — 11 November 2026

Integration **0.5.0** adds browser APK uploads while preserving the Android
0.8.6 OTA protocol. No Android code change or GitHub configuration is required.

## Automated checks

- **27** fast protocol/archive/APK tests: real binary XML metadata shapes in
  UTF-8 and UTF-16, wrong package, invalid version, corrupt compression,
  truncated manifests, bounded ZIP directories, hash and size validation.
- **14** runtime tests importing real Home Assistant APIs: upload staging without
  installation or GitHub access, admin-only HTTP endpoints, scoped APK download,
  lost requests, offline/legacy/downgrade rejection, replaced-upload ID binding,
  preservation of active downloads and the previous upload after failed or
  oversized transfers, verified persistence, and update-entity build ordering
  when version labels are equal. Existing private CI-source tests remain green.
- **23** frontend tests: separate upload/install actions, authenticated raw file
  transfer, explicit kiosk selection, upload/error/progress display, no duplicate
  submission, polling without replacing the file input or losing selection,
  safe rendering, eligibility checks and the existing control/settings flows.

## Live HA and browser proof

A disposable **Home Assistant 2026.11.1**, frontend **20261028.5**, Chromium and an
isolated MQTT broker were used with fictional kiosks and no GitHub credentials.

The browser selected a real **231782661-byte APK** (0.8.6, build 17), waited through
polling, uploaded it via HA's actual authenticated route and received automatically
parsed version/build metadata. Uploading sent no install command. After explicit
selection of a synthetic kiosk reporting build 16, the Install action sent a real
MQTT request. The test client downloaded the exact APK through the scoped HA HTTP
grant, streamed it and verified its size and SHA-256. Its simulated
`awaiting_confirmation` status appeared in the panel. Desktop and 400-pixel-wide
layouts were captured and inspected; images remain outside the public repository.
The browser test client does not perform an Android installation.

HA was then stopped and restarted with the current integration. The WebSocket
read model restored the identical artifact ID and verified metadata from disk.
The real HA middleware returned 401 for unauthenticated upload/install requests.
The new endpoints require an administrator in addition to authentication.

The Android installer itself was exercised in the preceding private 0.8.6 CI:
32 regression/verification tests and a separate UI-confirmed real emulator upgrade
with restart and `installed` state. That unchanged client protocol is reused here.
No physical tablet was available, and no new APK or environment was published.
