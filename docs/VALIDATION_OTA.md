# HA OTA validation — 10 November 2026

Integration 0.4.2 was checked with Home Assistant 2026.11.1 / frontend 20261028.5.
All runtime data used fictional devices on isolated loopback services.

- 21 fast protocol/archive tests cover existing controls, capability parsing,
  correlation, manifest binding, bounded extraction, bad hashes and paths.
- 7 orchestration tests import the real HA runtime: trusted CI run selection,
  repository authentication omitted from storage redirects, refusal of foreign
  redirect hosts, real artifact HTTP streaming, missing/wrong/expired grants,
  offline/downgrade/concurrent requests, stale state, allowlisted diagnostics and
  lost-request timeout. Download tokens never enter the kiosk read model.
- 19 existing frontend tests remain green.
- The live HA instance was restarted with the new platforms. Real MQTT messages
  created the update entity, installed-version metadata and progress features.
  The integration options form exposes an empty password selector; it does not
  prefill the stored token. The real HA artifact endpoint returns 401 without a
  valid artifact grant. Existing native and MQTT-linked devices, controls and
  retained-state reload behavior still pass the live test.
- The public snapshot pattern check passed. Private repository names, APKs,
  credentials, screenshots and runtime logs are excluded from this repository.

Android download verification and actual PackageInstaller upgrade behavior are
validated separately in the private Android CI. These HA results do not establish
physical tablet installation, silent OTA or unattended rollback. See [OTA.md](OTA.md)
for the bootstrap install and Android confirmation requirements.

[Public CI run 42916595852](https://github.com/Alec-99/Alec-99-ha-gecko-kiosk/actions/runs/42916595852)
on `daa63e3aade37d7e536a52e83124100d58c73920` passed both validation jobs,
including all 21 fast tests, 7 runtime tests and 19 frontend tests. The source
selection test explicitly covers a freshly booted host so the initial check is
not incorrectly skipped by the ten-minute cache.

A real private tablet CI artifact (version 0.8.6, Android code 17) was also
consumed by this repository's artifact validator: actual ZIP layout, package,
source/version binding, size and digest passed. No APK was copied into this repo.
The private Android CI separately passed 32 regression/verification tests and
one installer handoff test, followed by a UI-confirmed real in-place emulator
upgrade to a higher test version, app restart and `installed` status.
