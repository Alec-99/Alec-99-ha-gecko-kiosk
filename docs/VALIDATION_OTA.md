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


Integration 0.6.0: 27 pure protocol/APK tests, 16 real-HA runtime contracts and
26 frontend tests include strict silent gating, typed platform diagnostics,
explicit legacy opt-in and separate command/download deadlines. Device Owner
installation is exercised in the Android application's separate emulator CI;
this integration suite uses synthetic MQTT clients and does not prove a physical
tablet's privileges or cross-network reachability.


The app 0.8.9 / code 20 Android CI has now completed successfully. Its raw logs
confirm 38 regression tests, an interactive installer test and an unattended
Device Owner installer test (each one instrumentation test followed by host
verification of the actually installed higher version, request ID and installed
state). The unattended test ran on API 30 with no taps and no unknown-source
app-op grant. This proves the emulator Device Owner path; it does not establish
the privileges or network reachability of a user's physical tablet, or the
Android 12+ self-update path without Device Owner.

The actual code 20 tablet APK also passed the upload manager for a synthetic
online code 18 client with explicit interactive opt-in and mocked MQTT dispatch.
Its real package metadata, size and SHA-256 were used. Android CI separately
verifies the fixed signing identity before offering the APK.


## Android 10 certificate collection correction

App 0.8.11 / code 22 fixes Android 10 / API 29 archive-certificate collection by
requesting GET_SIGNATURES as well as GET_SIGNING_CERTIFICATES, while retaining
strict comparison of current signer SHA-256 values through SigningInfo.
Integration 0.6.1 accepts the separate verify_signer_unavailable detail and gives
a source-diagnostics action when the error detail is absent.

Completed Android CI now separately covers Android 10 (API 29) and Android 11
(API 30). Each passed 38 regression tests, a real interactive higher-version APK
installation and a real unattended Device Owner installation. The silent proofs
use no taps and no unknown-source app-op grant, and verify installed version,
request ID, installed state, no user-action request and retained Device Owner.
The wrong-key test explicitly requires verify_signer_mismatch. These checks were
performed on disposable emulators; the physical tablet outcome remains separate.

Integration 0.6.1 CI passed 27 pure protocol/APK tests, 16 runtime contracts and
27 frontend tests. The actual code 23 tablet APK was also accepted by its upload
manager for a synthetic code 22 client with strict silent mode and correct
metadata/hash/size; MQTT dispatch was mocked for that additional upload check.
