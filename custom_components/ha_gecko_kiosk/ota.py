"""Private CI artifact broker; repository credentials never leave Home Assistant."""

from __future__ import annotations

import asyncio
import hmac
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import quote, urlparse

from aiohttp import web
from homeassistant.components import mqtt
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN, _ensure_kiosk, _require_capability, _state

from .ota_artifact import (
    Candidate,
    MAX_ARCHIVE,
    ARTIFACT_NAME,
    extract_verified_archive,
)

ACTIVE = {
    "requested",
    "downloading",
    "verifying",
    "permission_required",
    "awaiting_confirmation",
    "installing",
}
STATUSES = ACTIVE | {"idle", "installed", "error", "cancelled"}


class OtaDownloadView(HomeAssistantView):
    """Short-lived artifact-only grant, never a HA or GitHub access token."""

    url = "/api/ha_gecko_kiosk/ota/{job_id}"
    name = "api:ha_gecko_kiosk:ota"
    requires_auth = False

    async def get(self, request, job_id):
        hass = request.app[KEY_HASS]
        manager = hass.data.get(DOMAIN, {}).get("ota_manager")
        job = manager.jobs.get(job_id) if manager else None
        supplied = request.headers.get("Authorization", "")
        if (
            job is None
            or job["expires"] < time.monotonic()
            or not supplied.isascii()
            or not hmac.compare_digest(supplied, "Bearer " + job["token"])
        ):
            raise web.HTTPUnauthorized()
        return web.FileResponse(
            job["path"],
            headers={
                "Cache-Control": "no-store",
                "Content-Type": "application/vnd.android.package-archive",
            },
        )


class OtaManager:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.candidate = None
        self.last_check = 0.0
        self.jobs = {}
        self.lock = asyncio.Lock()
        self.download_lock = asyncio.Lock()
        self.directory = Path(hass.config.path(".storage", "ha_gecko_kiosk_ota"))
        self.prepared = None
        self.error = None
        self.pending_installs = set()
        self.expiry_timers = []
        self.stopped = False

    @property
    def configured(self):
        options = self.entry.options
        return bool(
            options.get("ota_repository")
            and options.get("ota_branch")
            and options.get("ota_token")
        )

    def notify(self, kiosk_id):
        manager = self.hass.data[DOMAIN].get("registry_manager")
        if manager:
            manager.update(kiosk_id)

    async def github_json(self, path):
        session = async_get_clientsession(self.hass)
        headers = {
            "Authorization": "Bearer " + self.entry.options["ota_token"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with session.get(
            "https://api.github.com/" + path,
            headers=headers,
            timeout=30,
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise HomeAssistantError(
                    f"OTA source request failed (HTTP {response.status})"
                )
            if response.content_length and response.content_length > 2 * 1024 * 1024:
                raise HomeAssistantError("OTA source response too large")
            chunks = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                chunks.extend(chunk)
                if len(chunks) > 2 * 1024 * 1024:
                    raise HomeAssistantError("OTA source response too large")
            return json.loads(chunks)

    async def check(self, force=False):
        if self.stopped:
            return
        if not self.configured:
            self.candidate = None
            return
        async with self.lock:
            if not force and time.monotonic() - self.last_check < 600:
                return
            repository = self.entry.options["ota_repository"]
            workflow = quote(
                self.entry.options.get("ota_workflow", "build-ha-gecko-kiosk.yml"),
                safe="",
            )
            branch = quote(self.entry.options["ota_branch"], safe="")
            try:
                runs = await self.github_json(
                    f"repos/{repository}/actions/workflows/{workflow}/runs?status=success&branch={branch}&per_page=10"
                )
                candidate = None
                for run in runs.get("workflow_runs", []):
                    if (
                        run.get("conclusion") != "success"
                        or run.get("event") not in ("push", "workflow_dispatch")
                        or run.get("head_branch") != self.entry.options["ota_branch"]
                        or run.get("head_repository", {}).get("full_name", "").lower()
                        != repository.lower()
                        or not re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))
                    ):
                        continue
                    artifacts = await self.github_json(
                        f"repos/{repository}/actions/runs/{int(run['id'])}/artifacts?per_page=100"
                    )
                    for artifact in artifacts.get("artifacts", []):
                        match = ARTIFACT_NAME.fullmatch(artifact.get("name", ""))
                        if (
                            match
                            and not artifact.get("expired")
                            and type(artifact.get("id")) is int
                            and 0 < artifact.get("size_in_bytes", 0) <= MAX_ARCHIVE
                        ):
                            candidate = Candidate(
                                artifact["id"], match[1], run["head_sha"]
                            )
                            break
                    if candidate:
                        break
                self.candidate = candidate
                self.error = None
                self.last_check = time.monotonic()
            except Exception:
                # Do not put request headers, URLs or exception bodies into state/logs.
                self.error = "source_unavailable"
                self.last_check = time.monotonic()
                raise HomeAssistantError(
                    "OTA source unavailable; check repository, branch and Actions-read credential"
                ) from None
        for kiosk_id in list(_state(self.hass)):
            self.notify(kiosk_id)

    async def prepare(self, candidate):
        async with self.download_lock:
            if self.prepared and self.prepared[0] == candidate:
                return self.prepared[1:]
            await self.hass.async_add_executor_job(
                self.directory.mkdir, 0o700, True, True
            )
            archive = self.directory / "download.zip.part"
            session = async_get_clientsession(self.hass)
            repository = self.entry.options["ota_repository"]
            headers = {
                "Authorization": "Bearer " + self.entry.options["ota_token"],
                "Accept": "application/vnd.github+json",
            }
            source = f"https://api.github.com/repos/{repository}/actions/artifacts/{candidate.artifact_id}/zip"
            try:
                async with session.get(
                    source, headers=headers, allow_redirects=False, timeout=30
                ) as response:
                    if response.status == 302:
                        location = response.headers.get("Location", "")
                    elif response.status == 200:
                        location = None
                        await self._save_response(response, archive)
                    else:
                        raise ValueError("Artifact access denied")
                if location is not None:
                    url = urlparse(location)
                    if (
                        url.scheme != "https"
                        or url.username
                        or url.password
                        or not url.hostname
                        or not any(
                            url.hostname.endswith(suffix)
                            for suffix in (
                                ".blob.core.windows.net",
                                ".githubusercontent.com",
                                ".actions.githubusercontent.com",
                            )
                        )
                    ):
                        raise ValueError("Invalid artifact redirect")
                    # GitHub credentials must not follow the storage redirect.
                    async with session.get(
                        location, allow_redirects=False, timeout=300
                    ) as response:
                        if response.status != 200:
                            raise ValueError("Artifact download failed")
                        await self._save_response(response, archive)
                manifest, path = await self.hass.async_add_executor_job(
                    extract_verified_archive, archive, self.directory, candidate
                )
                self.prepared = candidate, manifest, path
                keep = {path} | {
                    job["path"]
                    for job in self.jobs.values()
                    if job["expires"] > time.monotonic()
                }
                await self.hass.async_add_executor_job(self._prune_cache, keep)
                return manifest, path
            except Exception:
                await self.hass.async_add_executor_job(archive.unlink, True)
                raise HomeAssistantError(
                    "OTA artifact could not be downloaded or verified"
                ) from None

    def _prune_cache(self, keep):
        for path in self.directory.glob("*.apk"):
            if path not in keep:
                path.unlink(missing_ok=True)

    async def _save_response(self, response, path):
        if response.content_length and response.content_length > MAX_ARCHIVE:
            raise ValueError("Archive too large")
        stream = await self.hass.async_add_executor_job(path.open, "wb")
        try:
            size = 0
            async for chunk in response.content.iter_chunked(256 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError("Archive too large")
                await self.hass.async_add_executor_job(stream.write, chunk)
        finally:
            await self.hass.async_add_executor_job(stream.close)

    async def install(self, kiosk_id):
        if kiosk_id in self.pending_installs:
            raise HomeAssistantError("An OTA update is already being prepared")
        self.pending_installs.add(kiosk_id)
        try:
            await self._install(kiosk_id)
        finally:
            self.pending_installs.discard(kiosk_id)

    async def _install(self, kiosk_id):
        if self.stopped:
            raise HomeAssistantError("OTA controller is unloading")
        _require_capability(self.hass, kiosk_id, "ota.install")
        state = _state(self.hass).get(kiosk_id, {})
        if state.get("availability") != "online":
            raise HomeAssistantError("Kiosk is offline")
        if state.get("ota", {}).get("status") in ACTIVE:
            raise HomeAssistantError("An OTA update is already active")
        await self.check()
        candidate = self.candidate
        if candidate is None:
            raise HomeAssistantError("No successful OTA build is available")
        manifest, path = await self.prepare(candidate)
        if self.stopped:
            raise HomeAssistantError("OTA controller is unloading")
        # Require a real version-code report, never infer Android ordering from a label.
        current = _state(self.hass)[kiosk_id].get("ota", {}).get("version_code")
        if type(current) is not int or manifest["version_code"] <= current:
            raise HomeAssistantError("OTA requires a newer Android version code")
        if _state(self.hass)[kiosk_id].get("availability") != "online":
            raise HomeAssistantError("Kiosk went offline")
        _require_capability(self.hass, kiosk_id, "ota.install")
        now = time.monotonic()
        self.jobs = {
            key: value for key, value in self.jobs.items() if value["expires"] > now
        }
        if len(self.jobs) >= 32:
            raise HomeAssistantError("Too many pending OTA downloads")
        request_id = secrets.token_hex(16)
        job_id = secrets.token_hex(16)
        grant = secrets.token_urlsafe(32)
        self.jobs[job_id] = {
            "kiosk": kiosk_id,
            "request_id": request_id,
            "token": grant,
            "path": path,
            "expires": now + 600,
        }
        payload = {
            "schema": 1,
            "request_id": request_id,
            "expires_at_ms": int(time.time() * 1000) + 120000,
            "download_path": f"/api/ha_gecko_kiosk/ota/{job_id}",
            "download_token": grant,
            "sha256": manifest["sha256"],
            "size": manifest["size"],
            "version_code": manifest["version_code"],
            "version_name": manifest["version_name"],
        }

        @callback
        def expired(_now):
            job = self.jobs.pop(job_id, None)
            current = _state(self.hass).get(kiosk_id, {}).get("ota", {})
            if (
                job is not None
                and current.get("request_id") == request_id
                and current.get("status") in {"requested", "downloading", "verifying"}
            ):
                current.update(status="error", detail="timeout")
                self.notify(kiosk_id)

        self.expiry_timers.append(async_call_later(self.hass, 600, expired))
        state.setdefault("ota", {}).update(
            status="requested", progress=0, request_id=request_id
        )
        self.notify(kiosk_id)
        try:
            await mqtt.async_publish(
                self.hass,
                f"ha_kiosk/{kiosk_id}/command/ota",
                json.dumps(payload),
                qos=1,
                retain=False,
            )
        except Exception:
            self.jobs.pop(job_id, None)
            state["ota"].update(status="error", detail="publish_failed")
            self.notify(kiosk_id)
            raise HomeAssistantError("OTA command could not be sent") from None

    def receive(self, kiosk_id, payload):
        if len(payload) > 2048:
            return
        try:
            value = json.loads(payload)
            if (
                not isinstance(value, dict)
                or value.get("schema") != 1
                or value.get("status") not in STATUSES
            ):
                return
            if (
                type(value.get("version_code")) is not int
                or not 0 < value["version_code"] < 2**31
            ):
                return
            if not isinstance(value.get("version_name"), str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", value["version_name"]
            ):
                return
            clean = {
                key: value[key] for key in ("status", "version_code", "version_name")
            }
            if type(value.get("progress")) is int and 0 <= value["progress"] <= 100:
                clean["progress"] = value["progress"]
            if isinstance(value.get("request_id"), str) and re.fullmatch(
                r"[0-9a-f]{32}", value["request_id"]
            ):
                clean["request_id"] = value["request_id"]
            if value.get("detail") in {
                "download_failed",
                "verification_failed",
                "permission_required",
                "installer_failed",
                "interrupted",
                "expired",
                "cancelled",
                "installed",
            }:
                clean["detail"] = value["detail"]
            state = _ensure_kiosk(self.hass, kiosk_id)
            previous = state.get("ota", {})
            # Reject a stale retained job snapshot while a new request is active.
            if previous.get("status") in ACTIVE and previous.get(
                "request_id"
            ) != clean.get("request_id"):
                return
            state["ota"] = clean
            self.notify(kiosk_id)
        except (TypeError, ValueError):
            return

    def stop(self):
        self.stopped = True
        self.jobs.clear()
        for cancel in self.expiry_timers:
            cancel()
        self.expiry_timers.clear()
