"""APK metadata contracts with no Android or Home Assistant dependencies."""

import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
import zipfile
import warnings

ROOT = Path(__file__).resolve().parents[2]
package = types.ModuleType("apk_contract_tested")
package.__path__ = [str(ROOT / "custom_components/ha_gecko_kiosk")]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(
    "apk_fixture", ROOT / "tests/apk_fixture.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
from apk_contract_tested.apk import ApkError, inspect_apk, manifest_metadata


class ApkMetadataTest(unittest.TestCase):
    def test_utf8_and_utf16_manifests_report_real_package_and_version(self):
        for utf8 in (True, False):
            self.assertEqual(
                {
                    "package_id": fixtures.PACKAGE,
                    "version_code": 18,
                    "version_name": "0.8.7-test",
                },
                manifest_metadata(fixtures.binary_manifest(utf8=utf8)),
            )

    def test_wrong_app_wrong_namespace_and_invalid_versions_are_rejected(self):
        for parameters in (
            {"package": "example.other"},
            {"version_code": 0},
            {"version_code": 2**31},
            {"version_name": "invalid/version"},
            {"android_namespace": "https://example.invalid/android"},
        ):
            with self.subTest(parameters=parameters), self.assertRaises(ApkError):
                manifest_metadata(fixtures.binary_manifest(**parameters))

    def test_truncated_and_inconsistent_binary_chunks_are_rejected(self):
        data = fixtures.binary_manifest()
        for sample in (data[:7], data[:-1], b"<manifest/>", data[:8] + b"\0" * 8):
            with self.assertRaises(ApkError):
                manifest_metadata(sample)
        corrupted = bytearray(data)
        struct.pack_into("<I", corrupted, 8 + 4, 0)
        with self.assertRaises(ApkError):
            manifest_metadata(corrupted)

    def test_actual_uploaded_bytes_determine_hash_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arbitrary-filename.apk"
            raw = fixtures.apk_bytes()
            path.write_bytes(raw)
            metadata = inspect_apk(path)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata["sha256"])
            self.assertEqual(len(raw), metadata["size"])
            self.assertEqual(18, metadata["version_code"])

    def test_invalid_zip_and_duplicate_or_missing_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.apk"
            for content in (b"", b"not an APK", fixtures.apk_bytes()[:-10]):
                path.write_bytes(content)
                with self.assertRaises(ApkError):
                    inspect_apk(path)
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("unrelated.txt", b"test")
            with self.assertRaises(ApkError):
                inspect_apk(path)
            path.write_bytes(fixtures.apk_bytes())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "a") as bundle:
                    bundle.writestr("AndroidManifest.xml", fixtures.binary_manifest())
            with self.assertRaises(ApkError):
                inspect_apk(path)
            raw = bytearray(fixtures.apk_bytes())
            name_length, extra_length = struct.unpack_from("<HH", raw, 26)
            raw[30 + name_length + extra_length] = 0x07
            path.write_bytes(raw)
            with self.assertRaises(ApkError):
                inspect_apk(path)

    def test_oversized_zip_directory_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.apk"
            raw = bytearray(fixtures.apk_bytes())
            struct.pack_into("<H", raw, len(raw) - 22 + 10, 30000)
            struct.pack_into("<H", raw, len(raw) - 22 + 8, 30000)
            path.write_bytes(raw)
            with self.assertRaises(ApkError):
                inspect_apk(path)
