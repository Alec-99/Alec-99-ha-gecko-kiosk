"""Archive validation contracts, without a HA host or real APK distribution."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

path = (
    Path(__file__).resolve().parents[2]
    / "custom_components/ha_gecko_kiosk/ota_artifact.py"
)
spec = importlib.util.spec_from_file_location("ota_artifact_tested", path)
ota = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ota
spec.loader.exec_module(ota)


class OtaArtifactTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.candidate = ota.Candidate(7, "1.2.3-test", "a" * 40)
        self.apk = b"synthetic archive contract fixture; not an installable APK"
        self.manifest = {
            "schema": 1,
            "package_id": ota.PACKAGE,
            "version_name": self.candidate.version_name,
            "source_commit": self.candidate.source_commit,
            "version_code": 123,
            "size": len(self.apk),
            "sha256": hashlib.sha256(self.apk).hexdigest(),
            "apk_filename": "fixture.apk",
        }

    def archive(self, extra=None):
        path = self.root / "artifact.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("ota-manifest.json", json.dumps(self.manifest))
            bundle.writestr("fixture.apk", self.apk)
            if extra:
                bundle.writestr(extra, b"unexpected")
        return path

    def test_valid_archive_is_hashed_cached_and_input_removed(self):
        source = self.archive()
        manifest, target = ota.extract_verified_archive(
            source, self.root, self.candidate
        )
        self.assertEqual(self.apk, target.read_bytes())
        self.assertEqual(self.manifest, manifest)
        self.assertFalse(source.exists())

    def test_corrupt_hash_never_produces_a_cached_apk(self):
        self.manifest["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            ota.extract_verified_archive(self.archive(), self.root, self.candidate)
        self.assertFalse(list(self.root.glob("*.apk")))

    def test_manifest_is_bound_to_build_version_commit_and_package(self):
        for field, value in [
            ("schema", True),
            ("version_name", "other"),
            ("source_commit", "b" * 40),
            ("package_id", "other.app"),
            ("version_code", True),
            ("size", ota.MAX_APK + 1),
            ("apk_filename", "../fixture.apk"),
        ]:
            invalid = dict(self.manifest, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                ota.validate_manifest(
                    invalid, self.candidate.version_name, self.candidate.source_commit
                )

    def test_unexpected_archive_entries_are_rejected(self):
        with self.assertRaises(ValueError):
            ota.extract_verified_archive(
                self.archive("../unwanted"), self.root, self.candidate
            )

    def test_declared_uncompressed_size_is_checked(self):
        self.manifest["size"] += 1
        with self.assertRaises(ValueError):
            ota.extract_verified_archive(self.archive(), self.root, self.candidate)

    def test_only_tablet_ci_artifact_names_are_selected(self):
        self.assertIsNotNone(
            ota.ARTIFACT_NAME.fullmatch(
                "ha-gecko-kiosk-v1.2.3-test-sm-t580-run-1-attempt-1"
            )
        )
        self.assertIsNone(ota.ARTIFACT_NAME.fullmatch("ha-gecko-kiosk-emulator-apks"))
