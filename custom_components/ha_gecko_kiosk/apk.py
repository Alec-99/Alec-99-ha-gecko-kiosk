"""Read bounded APK package/version metadata without executing or extracting it."""

import hashlib
from pathlib import Path
import re
import struct
import zipfile
import zlib

from .ota_artifact import MAX_APK, PACKAGE

ANDROID_NS = "http://schemas.android.com/apk/res/android"
NO_INDEX = 0xFFFFFFFF
MAX_MANIFEST = 4 * 1024 * 1024


class ApkError(ValueError):
    """The uploaded file is not a supported kiosk APK."""


def _bounded_zip(path):
    """Reject oversized ZIP directories before ZipFile allocates their entries."""
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 65557))
        tail = stream.read(65557)
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or position + 22 > len(tail):
        raise ApkError("Geen geldig APK-bestand.")
    _, disk, directory_disk, entries_disk, entries, size, offset, comment = (
        struct.unpack_from("<4s4H2LH", tail, position)
    )
    if (
        disk
        or directory_disk
        or entries_disk != entries
        or not 0 < entries <= 20000
        or size > 8 * 1024 * 1024
        or offset + size > path.stat().st_size
        or position + 22 + comment != len(tail)
    ):
        raise ApkError("De APK-archiefstructuur wordt niet ondersteund.")


def _strings(data, start, header_size, end):
    if header_size < 28 or start + header_size > end:
        raise ApkError("Ongeldige APK-stringtabel.")
    count, styles, flags, strings_start, styles_start = struct.unpack_from(
        "<5I", data, start + 8
    )
    offsets_end = start + header_size + 4 * (count + styles)
    strings_begin = start + strings_start
    strings_end = start + styles_start if styles_start else end
    if (
        count > 65536
        or offsets_end > strings_begin
        or strings_begin > strings_end
        or strings_end > end
    ):
        raise ApkError("Ongeldige APK-stringtabel.")

    def string(index):
        if index == NO_INDEX:
            return None
        if not 0 <= index < count:
            raise ApkError("Ongeldige APK-stringverwijzing.")
        position = (
            strings_begin
            + struct.unpack_from("<I", data, start + header_size + 4 * index)[0]
        )

        def length(width):
            nonlocal position
            if position + width > strings_end:
                raise ApkError("Afgebroken APK-string.")
            value = int.from_bytes(data[position : position + width], "little")
            position += width
            high = 1 << (width * 8 - 1)
            if value & high:
                if position + width > strings_end:
                    raise ApkError("Afgebroken APK-string.")
                value = ((value & (high - 1)) << (width * 8)) | int.from_bytes(
                    data[position : position + width], "little"
                )
                position += width
            return value

        utf8 = bool(flags & 0x100)
        units = length(1 if utf8 else 2)
        size = length(1) if utf8 else units * 2
        terminator = 1 if utf8 else 2
        if (
            size > 16384
            or position + size + terminator > strings_end
            or any(data[position + size : position + size + terminator])
        ):
            raise ApkError("Ongeldige APK-stringlengte.")
        return data[position : position + size].decode("utf-8" if utf8 else "utf-16le")

    return string


def manifest_metadata(data):
    """Read the root manifest's Android binary XML attributes only."""
    if len(data) < 8 or len(data) > MAX_MANIFEST:
        raise ApkError("Ongeldig Android-manifest.")
    kind, header_size, total = struct.unpack_from("<HHI", data)
    if kind != 3 or header_size != 8 or total != len(data):
        raise ApkError("De APK bevat geen geldig binair Android-manifest.")
    position, string = 8, None
    while position < total:
        if position + 8 > total:
            raise ApkError("Afgebroken Android-manifest.")
        kind, header_size, size = struct.unpack_from("<HHI", data, position)
        end = position + size
        if header_size < 8 or size < header_size or end > total:
            raise ApkError("Ongeldige Android-manifeststructuur.")
        if kind == 1:
            if string is not None:
                raise ApkError("Dubbele APK-stringtabel.")
            string = _strings(data, position, header_size, end)
        elif kind == 0x102:
            if string is None or header_size != 16 or size < 36:
                raise ApkError("Ongeldig Android-manifestelement.")
            namespace, name, attr_start, attr_size, count = struct.unpack_from(
                "<IIHHH", data, position + 16
            )
            if (
                namespace != NO_INDEX
                or string(name) != "manifest"
                or attr_size != 20
                or count > 128
                or attr_start < 20
            ):
                raise ApkError("Ongeldige Android-manifestroot.")
            attributes = position + 16 + attr_start
            if attributes + attr_size * count > end:
                raise ApkError("Afgebroken Android-manifestattributen.")
            values = {}
            for offset in range(attributes, attributes + attr_size * count, attr_size):
                ns, key, raw, value_size, reserved, value_type, value = (
                    struct.unpack_from("<IIIHBBI", data, offset)
                )
                name, namespace = string(key), string(ns)
                if not (
                    namespace is None
                    and name == "package"
                    or namespace == ANDROID_NS
                    and name in ("versionName", "versionCode", "versionCodeMajor")
                ):
                    continue
                if name in values or value_size != 8 or reserved:
                    raise ApkError("Ongeldige APK-versiegegevens.")
                if name in ("versionCode", "versionCodeMajor"):
                    if value_type not in (0x10, 0x11):
                        raise ApkError("De APK bevat geen numeriek versienummer.")
                    values[name] = value
                elif value_type == 3:
                    values[name] = string(value)
                else:
                    raise ApkError("De APK-versienaam kan niet worden gelezen.")
            if values.get("package") != PACKAGE:
                raise ApkError("Dit is geen HA Gecko Kiosk-APK.")
            if (
                type(values.get("versionCode")) is not int
                or not 0 < values["versionCode"] < 2**31
                or values.get("versionCodeMajor", 0) != 0
                or not isinstance(values.get("versionName"), str)
                or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", values["versionName"]
                )
            ):
                raise ApkError("De APK-versie wordt niet ondersteund.")
            return {
                "package_id": PACKAGE,
                "version_code": values["versionCode"],
                "version_name": values["versionName"],
            }
        position = end
    raise ApkError("De APK heeft geen Android-manifestroot.")


def inspect_apk(path):
    """Return actual package, version, size and SHA-256 of one uploaded APK."""
    path = Path(path)
    try:
        size = path.stat().st_size
        if not 0 < size <= MAX_APK:
            raise ApkError("Kies een APK-bestand van maximaal 256 MiB.")
        _bounded_zip(path)
        with zipfile.ZipFile(path) as bundle:
            manifests = [
                entry
                for entry in bundle.infolist()
                if entry.filename == "AndroidManifest.xml"
            ]
            if len(manifests) != 1 or not 0 < manifests[0].file_size <= MAX_MANIFEST:
                raise ApkError("De APK heeft geen geldig Android-manifest.")
            if manifests[0].compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise ApkError("De APK-manifestcompressie wordt niet ondersteund.")
            metadata = manifest_metadata(bundle.read(manifests[0]))
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {"schema": 1, **metadata, "size": size, "sha256": digest}
    except ApkError:
        raise
    except (
        ValueError,
        UnicodeError,
        struct.error,
        zipfile.BadZipFile,
        zlib.error,
        RuntimeError,
        KeyError,
        EOFError,
    ):
        raise ApkError("Het APK-bestand is ongeldig of beschadigd.") from None
