"""Check common private material before publishing. Not a comprehensive audit."""
from pathlib import Path
import re
import struct
import sys

root = Path(__file__).resolve().parents[1]
patterns = {
    "private IPv4": re.compile(r"(?<!\d)(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?!\d)"),
    "MAC address": re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b"),
    "private source URL": re.compile("github[.]com/Alec-99/" + "sm-t580" + "-ha-panel", re.I),
    "personal share": re.compile("chatgpt[.]com/library/" + "share", re.I),
}
forbidden = ("baseline/", "downloads/", "reference/", "docs/project-memory/", "docs/reference/")
allowed_suffixes = {".py", ".js", ".json", ".md", ".yml", ".yaml", ".toml", ".xml"}
# Explicit allowlist. Other PNG files (such as private device screenshots) stay blocked.
approved_pngs = {
    "custom_components/ha_gecko_kiosk/brand/icon.png": (256, 256),
    "custom_components/ha_gecko_kiosk/brand/icon@2x.png": (512, 512),
    "custom_components/ha_gecko_kiosk/frontend/icon.png": (256, 256),
}
problems = []
for path in root.rglob("*"):
    if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts or ".pytest_cache" in path.parts:
        continue
    rel = path.relative_to(root).as_posix()
    if rel.startswith(forbidden):
        problems.append((rel, "unapproved directory"))
    if rel in approved_pngs:
        data = path.read_bytes()
        if (len(data) < 24 or len(data) > 1_000_000 or
                data[:8] != bytes.fromhex("89504e470d0a1a0a") or data[12:16] != b"IHDR"):
            problems.append((rel, "invalid or oversized PNG"))
        elif struct.unpack(">II", data[16:24]) != approved_pngs[rel]:
            problems.append((rel, "unexpected PNG dimensions"))
        continue
    if path.suffix not in allowed_suffixes:
        if rel != ".gitignore":
            problems.append((rel, "unapproved file type"))
        continue
    try:
        body = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        problems.append((rel, "not UTF-8"))
        continue
    for title, regex in patterns.items():
        if regex.search(body):
            problems.append((rel, title))
for rel, reason in problems:
    print(f"{rel}: {reason}; matched values intentionally hidden", file=sys.stderr)
if problems:
    raise SystemExit(1)
print("Pattern checks passed; manual review is still required.")
