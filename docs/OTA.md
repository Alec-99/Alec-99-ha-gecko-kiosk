# APK OTA through Home Assistant

The integration brokers a private GitHub Actions artifact to an OTA-capable
kiosk. Repository credentials stay in HA config-entry options. They are never
included in the kiosk read model, entity attributes or MQTT commands.

## Setup

1. Manually install the first OTA-capable Android build (Gecko 0.8.6+) using the
   same signing key as the installed app. Do not uninstall to bypass a key mismatch.
2. Configure the integration options: `owner/repository`, trusted branch,
   workflow filename (default `build-ha-gecko-kiosk.yml`), and an Actions-read
   GitHub token restricted to that repository. No source is enabled by default.
3. Reconnect the kiosk. Its `ota.install` capability creates an **App-update**
   entity. Open that entity and select Install when a newer build is available.
4. On Android, grant this app permission to install packages if requested, return
   to the kiosk and confirm Android's installation prompt. No root or device-owner
   setup is required. Installation is deliberately user-confirmed on modern Android.

The tablet must reach `/api/ha_gecko_kiosk/ota/...` at the same HA origin as its
configured dashboard. A reverse proxy must pass this route and its Authorization
header to HA. Self-signed HTTPS certificates are not bypassed. With HTTP dashboard
origins the transfer also uses HTTP; use a trusted network or HTTPS. Tokens expire
and hashes protect integrity, but HTTP does not provide transport confidentiality.

## Source and artifact contract

Only completed successful Actions runs for the configured repository, workflow
and branch, with event `push` or `workflow_dispatch`, are selected. Fork/PR runs,
failed runs, expired artifacts and emulator artifacts are excluded. Retention is
controlled by the source workflow; the Android workflow keeps tablet artifacts
for 30 days. Source checks occur on startup and every six hours, shared across
kiosks with a ten-minute API cache. If no matching artifact exists the latest
version remains unknown.

An artifact name must match
`ha-gecko-kiosk-v<VERSION>-sm-t580-run-<NUMBER>-attempt-<NUMBER>`.
Its ZIP contains exactly one APK and `ota-manifest.json`:

```json
{
  "schema": 1,
  "package_id": "com.alec.hageckokiosk",
  "version_name": "1.2.3-test",
  "version_code": 123,
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "apk_filename": "fixture.apk",
  "size": 123456,
  "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
```

Values above are examples. The real manifest is generated from Android output
metadata and the actual built APK. Commit and version must match the selected
run/artifact; sizes, paths and decompression are bounded. APK maximum: 256 MiB.
HA extracts only the named file, computes its digest and caches it by digest.
Unused older cache files are removed when a new artifact is prepared.
GitHub authentication is sent only to `api.github.com`, and is omitted from the
validated HTTPS storage redirect.

## MQTT and download contract

HA publishes QoS 1, **not retained**, to `ha_kiosk/<id>/command/ota`:

```json
{
  "schema": 1,
  "request_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expires_at_ms": 2000000000000,
  "download_path": "/api/ha_gecko_kiosk/ota/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "download_token": "EXAMPLE_SCOPED_ARTIFACT_GRANT_REPLACE_ME",
  "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "size": 123456,
  "version_code": 123,
  "version_name": "1.2.3-test"
}
```

The grant is an artifact-only bearer credential, not a HA login or GitHub token.
It is sent in the download Authorization header, never in a query string.
It grants this APK for ten minutes and is invalidated by integration unload or
HA restart. MQTT accepts the install request for two minutes. Android rejects
retained requests, duplicate request IDs, older/equal version codes, foreign
paths, redirects, invalid content/hash/package and different signing keys.
The most recent request ID and staging metadata are persisted locally, without
persisting the download grant. Android's PackageInstaller additionally verifies
the signed APK during the in-place update; existing app data is preserved.

The kiosk publishes retained `ha_kiosk/<id>/ota/state` with schema 1,
`version_code`, `version_name`, `status`, `progress` (0–100), optional request ID
and an allowlisted detail code. Statuses: `idle`, `downloading`, `verifying`,
`permission_required`, `awaiting_confirmation`, `installing`, `installed`,
`cancelled`, `error`; HA also uses `requested`. Source credentials, download
grants, raw installer exceptions and URLs are excluded from this state.
HA rejects stale retained job snapshots while a new request is active.

## Limits

No scheduled automatic installation, backup/rollback, arbitrary URL installation,
channel publishing or bypass of Android confirmation. Configuring a trusted
branch authorizes its successful build artifacts as update candidates. Choose a
branch whose code you trust. A matching debug signing key remains essential;
losing a cached signing key breaks in-place updates.

Android may require Open on its installer screen if background relaunch is
restricted. Permission/confirmation waits remain visible in HA; rejecting the
Android prompt reports cancellation. Lost requests/downloads time out after ten
minutes. A HA restart invalidates outstanding HTTP grants; retry after the
client reports its interrupted download. Physical tablet installation remains a
separate check from emulator validation.
