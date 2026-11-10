"""Tiny binary-manifest ZIP fixtures, deliberately not installable Android apps."""

import io
import struct
import zipfile

PACKAGE = "com.alec.hageckokiosk"
ANDROID_NS = "http://schemas.android.com/apk/res/android"
NONE = 0xFFFFFFFF


def binary_manifest(
    version_code=18,
    version_name="0.8.7-test",
    package=PACKAGE,
    utf8=True,
    android_namespace=ANDROID_NS,
):
    strings = [
        "manifest",
        "package",
        "versionCode",
        "versionName",
        android_namespace,
        package,
        version_name,
    ]
    encoded = bytearray()
    offsets = []
    for value in strings:
        offsets.append(len(encoded))
        if utf8:
            raw = value.encode("utf-8")
            encoded.extend(bytes([len(value), len(raw)]) + raw + b"\0")
        else:
            raw = value.encode("utf-16le")
            encoded.extend(struct.pack("<H", len(raw) // 2) + raw + b"\0\0")
    while len(encoded) % 4:
        encoded.append(0)
    start = 28 + 4 * len(strings)
    pool = struct.pack(
        "<HHI5I",
        1,
        28,
        start + len(encoded),
        len(strings),
        0,
        0x100 if utf8 else 0,
        start,
        0,
    )
    pool += struct.pack("<" + "I" * len(offsets), *offsets) + encoded
    namespace = struct.pack("<HHIIIII", 0x100, 16, 24, 1, NONE, NONE, 4)
    attributes = b"".join(
        [
            struct.pack("<IIIHBBI", NONE, 1, 5, 8, 0, 3, 5),
            struct.pack("<IIIHBBI", 4, 2, NONE, 8, 0, 0x10, version_code),
            struct.pack("<IIIHBBI", 4, 3, 6, 8, 0, 3, 6),
        ]
    )
    element = struct.pack("<HHIII", 0x102, 16, 36 + len(attributes), 1, NONE)
    element += struct.pack("<II6H", NONE, 0, 20, 20, 3, 0, 0, 0) + attributes
    return (
        struct.pack("<HHI", 3, 8, 8 + len(pool) + len(namespace) + len(element))
        + pool
        + namespace
        + element
    )


def apk_bytes(**kwargs):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("AndroidManifest.xml", binary_manifest(**kwargs))
        bundle.writestr("classes.dex", b"synthetic ZIP fixture, not executable code")
    return stream.getvalue()
