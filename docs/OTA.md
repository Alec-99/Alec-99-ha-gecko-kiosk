# APK OTA through Home Assistant

From integration **0.5.0**, an administrator can upload a plain APK in the HA
browser panel and explicitly install it on a selected kiosk. No repository,
GitHub token or companion manifest is needed. The existing private CI source is
an optional alternative.

## Browser upload

1. For unattended updates, install Gecko 0.8.9+ once with the same signing key
   and configure Android installation rights (see below). Older OTA clients
   (0.8.6+) support only explicitly opted-in interactive installation.
2. Update the HA integration, restart HA, and open **Gecko-kiosken → App-updates**.
3. Choose the `.apk` file and press **APK uploaden**. HA reads the actual package,
   version name and Android build number from the APK's binary manifest, computes
   SHA-256 and stores it privately. The limit is 256 MiB. Uploading does not install.
4. Select a kiosk and press **Installeren op …**. HA requires an online OTA-capable
   client, a reported installed build number and a strictly higher uploaded build.
   The request is bound to the uploaded artifact ID so a concurrent replacement
   cannot silently substitute another file.
5. Leave **Zonder bevestiging op de tablet** enabled for remote installation.
   HA blocks unsupported clients or missing rights. Follow progress in the panel
   or **App-update** entity. Disable the checkbox only when deliberately allowing
   interactive Android settings/confirmation, for example during initial setup.

Both upload and install endpoints require an authenticated HA administrator.
Wrong apps, corrupt manifests, unsupported versions, oversized archives and
unsafe metadata are rejected before staging. The server reads bounded ZIP/binary
XML metadata without extracting or executing APK contents or adding an Android
SDK dependency. Android still verifies package signatures before installation.

The current upload is retained in HA's private `.storage/ha_gecko_kiosk_ota`
directory and verified again when the integration starts. Uploading a replacement
keeps an existing in-flight download valid. Aborted, invalid and oversized uploads
leave the previous staged file available and remove partial files. Unneeded older
APKs are pruned. A staged upload takes priority over the optional CI source.
Android build codes determine ordering, including builds with the same version
label. Source files, local paths and download grants are not exposed in the panel.

Admin upload API: `POST /api/ha_gecko_kiosk/ota_upload`, with the raw APK body and
Content-Type `application/vnd.android.package-archive` or `application/octet-stream`.
The 201 response contains `upload_id`, `version_name`, `version_code` and `size`.
An admin explicitly starts installation with `POST /api/ha_gecko_kiosk/ota_install`
and JSON `{"kiosk":"tablet_a","upload_id":"<uploaded ID>","require_silent":true}`. The existing admin
WebSocket list exposes `ota_upload` metadata for the panel, without file paths or
credentials. Omitting `require_silent` defaults to true; only an explicit false
permits interactive installation. The HA update entity always requires silent OTA.

## Historical debug APK signing

Earlier experimental Android APKs through 0.8.6 were found to use different
signing keys between CI runs. A higher build number alone cannot make those APKs
compatible. The fixed private debug signing line starts with 0.8.7 / build 18;
0.8.8 / build 19 is its matching OTA test target. Builds now verify their approved
certificate before offering an artifact.

An existing differently signed installation needs its original private key or a
one-time migration with a verified private backup of app settings. Do not remove
that installation before preserving its data. HA cannot bypass Android's signature
check. The first OTA-capable client requirement above describes protocol support,
not a guarantee that historical debug APKs share a signing identity.

## Optional private CI source

Configure the integration options with `owner/repository`, a trusted branch,
workflow filename (default `build-ha-gecko-kiosk.yml`), and an Actions-read GitHub
token restricted to that repository. Leave the token blank to preserve it; clear
the repository to disable the CI source. Credentials stay in HA and are never
included in kiosk state, entity attributes or MQTT commands. This configuration is
not required for browser uploads.

A CI artifact must follow the contract below. Select Install on the kiosk's
**App-update** entity when a newer build is available. The same Android permission
and confirmation requirements apply.

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
  "download_expires_at_ms": 2000001680000,
  "require_silent": true,
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
It grants this APK for thirty minutes and is invalidated by integration unload or
HA restart. New clients accept the install request for two minutes, with a separate thirty-minute
download deadline. Legacy interactive clients use a nine-minute command/download
deadline, below their ten-minute validation ceiling. Android rejects
retained requests, duplicate request IDs, older/equal version codes, foreign
paths, redirects, invalid content/hash/package and different signing keys.
The most recent request ID and staging metadata are persisted locally, without
persisting the download grant. Android's PackageInstaller additionally verifies
the signed APK during the in-place update; existing app data is preserved.

The kiosk publishes retained `ha_kiosk/<id>/ota/state` with schema 1,
`version_code`, `version_name`, `status`, `progress` (0–100), optional request ID
and an allowlisted detail code. Statuses: `idle`, `downloading`, `verifying`,
`permission_required`, `awaiting_confirmation`, `installing`, `installed`,
`cancelled`, `error`, `silent_unavailable`; HA also uses `requested`. Source credentials, download
grants, raw installer exceptions and URLs are excluded from this state.
HA rejects stale retained job snapshots while a new request is active.

## Limits

No scheduled automatic installation, backup/rollback, arbitrary URL installation,
channel publishing or bypass of Android installation policy. Configuring a trusted
branch authorizes its successful build artifacts as update candidates. Choose a
branch whose code you trust. A matching debug signing key remains essential;
losing the signing key breaks in-place updates.

Android may require Open on its installer screen if background relaunch is
restricted. Permission/confirmation waits remain visible in HA; rejecting the
Android prompt reports cancellation. Lost requests/downloads time out after thirty
minutes. A HA restart invalidates outstanding HTTP grants; retry after the
client reports its interrupted download. Physical tablet installation remains a
separate check from emulator validation.


## Troubleshooting across networks

The tablet initiates the download from the HA origin configured in its dashboard
URL. No inbound tablet listener or extra OTA port is used. With an existing
external HTTPS reverse proxy, the usual server-side port is 443; direct HA uses
its configured HTTP(S) port, often 8123. Existing MQTT connectivity carries the
command/status only and does not prove that the HA HTTP endpoint is reachable.
A local HA address requires routing/VPN between networks; otherwise use a reachable
HA HTTPS origin. The reverse proxy must forward the OTA path and Authorization
header and accept the browser's APK upload size.

Integration 0.5.1 displays the client's existing error code in App-updates and
Diagnostiek, and exposes it as `ota_detail` on the update entity. This identifies
whether the client reported `download_failed`, `verification_failed` or
`installer_failed`; it does not assume that every failure is a network issue.
Early app builds used broad failure codes, including some installer-preparation
errors under `download_failed`. A verification error can also mean a proxy/login
page was returned instead of the APK, not only a signing mismatch.


## Unattended installation rights (integration 0.6.0 / app 0.8.9)

Android 10/11 requires Device Owner or privileged INSTALL_PACKAGES permission for
unattended updates. Activating the ordinary device-administrator checkbox is not
sufficient. Device Owner is a one-time managed-device provisioning step; existing
accounts or another owner can prevent it. Do not factory-reset a tablet merely to
try OTA without preserving its configuration and choosing a provisioning method.

Android 12+ also supports self-updates under platform conditions, including the
app target SDK and install permissions. The app requests no user action, but stops
with `silent_unavailable` if Android still requires it. It never launches that
confirmation or unknown-source settings in strict mode. No su/root prompt is used.

The app reports `android_api`, `android_version`, `device_owner`,
`privileged_installer`, `install_method`, `silent_install_ready`,
`download_http_status` and `user_action_requested`; these also appear on the HA
update entity. Readiness reflects platform checks, not a guarantee that a particular
APK will be accepted. The app validates the actual APK target SDK before committing.

New error codes distinguish HTTP authorization, redirects, login content, TLS/DNS,
connection/timeout, incomplete download and APK hash/package/version/signer checks.
Older clients retain their broader error codes. The new 30-minute download deadline
fixes the old two-minute whole-file limit; it does not establish the cause of an
individual user's error without the reported detail code.
