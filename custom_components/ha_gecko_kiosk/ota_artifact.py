"""Bounded validation of the CI-generated APK archive; no HA runtime required."""

from dataclasses import dataclass
import hashlib
import json
import re
import zipfile

MAX_APK = 256 * 1024 * 1024
MAX_ARCHIVE = MAX_APK + 8 * 1024 * 1024
PACKAGE = "com.alec.hageckokiosk"
ARTIFACT_NAME = re.compile(
    r"ha-gecko-kiosk-v([A-Za-z0-9][A-Za-z0-9._-]*)-sm-t580-run-\d+-attempt-\d+"
)


@dataclass(frozen=True)
class Candidate:
    artifact_id: int
    version_name: str
    source_commit: str


def validate_manifest(value, expected_version, expected_commit):
    """Validate a tiny CI-generated manifest before extracting any APK."""
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Invalid OTA manifest")
    if (
        value.get("package_id") != PACKAGE
        or value.get("version_name") != expected_version
        or value.get("source_commit") != expected_commit
        or type(value.get("version_code")) is not int
        or not 0 < value["version_code"] < 2**31
        or type(value.get("size")) is not int
        or not 0 < value["size"] <= MAX_APK
        or not isinstance(value.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
        or not isinstance(value.get("apk_filename"), str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.apk", value["apk_filename"])
    ):
        raise ValueError("Invalid OTA manifest fields")
    return value


def extract_verified_archive(archive, directory, candidate):
    """Bound decompression, hash the APK and atomically cache it by digest."""
    temporary = directory / "candidate.apk.part"
    try:
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if len(entries) != 2 or len({item.filename for item in entries}) != 2:
                raise ValueError("Expected one APK and ota-manifest.json")
            info = bundle.getinfo("ota-manifest.json")
            if info.file_size > 4096:
                raise ValueError("OTA manifest too large")
            manifest = validate_manifest(
                json.loads(bundle.read(info)),
                candidate.version_name,
                candidate.source_commit,
            )
            apk = bundle.getinfo(manifest["apk_filename"])
            if apk.file_size != manifest["size"]:
                raise ValueError("APK size mismatch")
            digest = hashlib.sha256()
            size = 0
            with bundle.open(apk) as source, temporary.open("wb") as destination:
                while chunk := source.read(256 * 1024):
                    size += len(chunk)
                    if size > manifest["size"]:
                        raise ValueError("APK exceeds manifest size")
                    digest.update(chunk)
                    destination.write(chunk)
            if size != manifest["size"] or digest.hexdigest() != manifest["sha256"]:
                raise ValueError("APK digest mismatch")
            target = directory / (manifest["sha256"] + ".apk")
            temporary.replace(target)
            return manifest, target
    finally:
        temporary.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
