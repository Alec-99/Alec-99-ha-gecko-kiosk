"""Browser upload, staging, explicit install and admin access contracts."""

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web
from homeassistant.components.http import KEY_HASS
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from custom_components.ha_gecko_kiosk import DOMAIN
from custom_components.ha_gecko_kiosk.ota import (
    OtaManager,
    OtaUploadView,
    OtaInstallView,
    OtaDownloadView,
)

spec = importlib.util.spec_from_file_location(
    "apk_upload_fixture", Path(__file__).resolve().parents[1] / "apk_fixture.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class Content:
    def __init__(self, value):
        self.value = value

    async def iter_chunked(self, size):
        for offset in range(0, len(self.value), size):
            yield self.value[offset : offset + size]


class BrowserOtaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.kiosk = {
            "id": "tablet_a",
            "availability": "online",
            "capabilities": {"compatible": True, "capabilities": ["ota.install"]},
            "ota": {"version_code": 17, "version_name": "0.8.6-test", "status": "idle"},
        }
        self.hass = SimpleNamespace(
            data={DOMAIN: {"kiosks": {"tablet_a": self.kiosk}}},
            config=SimpleNamespace(
                path=lambda *parts: str(Path(self.temp.name).joinpath(*parts))
            ),
            async_add_executor_job=lambda fn, *args: asyncio.to_thread(fn, *args),
        )
        self.entry = SimpleNamespace(options={})
        self.manager = OtaManager(self.hass, self.entry)
        self.hass.data[DOMAIN]["ota_manager"] = self.manager
        self.timer = patch(
            "custom_components.ha_gecko_kiosk.ota.async_call_later",
            return_value=lambda: None,
        )
        self.timer.start()
        self.addCleanup(self.timer.stop)

    async def test_upload_needs_no_github_and_never_installs_until_explicitly_requested(
        self,
    ):
        raw = fixtures.apk_bytes()
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as publish:
            metadata = await self.manager.upload(Content(raw))
            self.assertEqual(18, metadata["version_code"])
            self.assertEqual(len(raw), metadata["size"])
            publish.assert_not_awaited()
            self.manager.check = AsyncMock(
                side_effect=AssertionError("Upload must work without GitHub")
            )
            await self.manager.install("tablet_a", upload_id=metadata["upload_id"])
            publish.assert_awaited_once()
            command = json.loads(publish.call_args.args[2])
            self.assertEqual(18, command["version_code"])
            self.assertEqual(self.manager.uploaded[0]["sha256"], command["sha256"])
            self.assertEqual({"qos": 1, "retain": False}, publish.call_args.kwargs)
        restored = OtaManager(self.hass, self.entry)
        await restored.load_upload()
        self.assertEqual(metadata, restored.upload_summary)
        self.assertEqual(raw, restored.uploaded[1].read_bytes())

    async def test_update_entity_uses_uploaded_apk_and_build_order_for_same_version_name(
        self,
    ):
        from custom_components.ha_gecko_kiosk.update import KioskUpdate
        from custom_components.ha_gecko_kiosk.entity import SPECS

        await self.manager.upload(
            Content(fixtures.apk_bytes(version_name="0.8.6-test"))
        )
        entity = KioskUpdate(SimpleNamespace(), "tablet_a", SPECS["update"][0])
        entity.hass = self.hass
        self.assertEqual("0.8.6-test", entity.latest_version)
        self.assertTrue(entity.version_is_newer("0.8.6-test", "0.8.6-test"))
        self.assertNotIn("GitHub", entity.release_summary)
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as publish:
            await entity.async_install(None, False)
            self.assertEqual(18, json.loads(publish.call_args.args[2])["version_code"])

    async def test_failed_and_oversized_chunked_uploads_preserve_previous_apk(self):
        metadata = await self.manager.upload(Content(fixtures.apk_bytes()))

        class Disconnected:
            async def iter_chunked(self, size):
                yield b"partial APK"
                raise ConnectionResetError()

        with self.assertRaises(ConnectionResetError):
            await self.manager.upload(Disconnected())
        with patch("custom_components.ha_gecko_kiosk.ota.MAX_APK", 128):
            with self.assertRaises(web.HTTPRequestEntityTooLarge):
                await self.manager.upload(Content(b"x" * 129))
        self.assertEqual(metadata, self.manager.upload_summary)
        self.assertFalse(list(self.manager.directory.glob("*.part")))
        self.assertFalse(self.manager.uploading)

    async def test_replacing_upload_preserves_active_download_and_rejects_stale_selection(
        self,
    ):
        second = copy.deepcopy(self.kiosk)
        second["id"] = "tablet_b"
        self.hass.data[DOMAIN]["kiosks"]["tablet_b"] = second
        old = await self.manager.upload(Content(fixtures.apk_bytes()))
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as publish:
            await self.manager.install("tablet_a", upload_id=old["upload_id"])
            old_path = next(iter(self.manager.jobs.values()))["path"]
            newer = await self.manager.upload(
                Content(fixtures.apk_bytes(version_code=19, version_name="0.8.8-test"))
            )
            self.assertTrue(old_path.is_file())
            with self.assertRaises(HomeAssistantError):
                await self.manager.install("tablet_b", upload_id=old["upload_id"])
            await self.manager.install("tablet_b", upload_id=newer["upload_id"])
            self.assertEqual(2, publish.await_count)
            self.assertEqual(19, json.loads(publish.call_args.args[2])["version_code"])

    async def test_downgrade_and_legacy_clients_are_rejected_by_server(self):
        metadata = await self.manager.upload(
            Content(fixtures.apk_bytes(version_code=17))
        )
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as publish:
            with self.assertRaises(HomeAssistantError):
                await self.manager.install("tablet_a", upload_id=metadata["upload_id"])
            self.kiosk.pop("capabilities")
            with self.assertRaises(HomeAssistantError):
                await self.manager.install("tablet_a", upload_id=metadata["upload_id"])
            publish.assert_not_awaited()

    async def test_corrupt_persisted_apk_is_not_restored(self):
        await self.manager.upload(Content(fixtures.apk_bytes()))
        self.manager.uploaded[1].write_bytes(b"corrupt")
        restored = OtaManager(self.hass, self.entry)
        await restored.load_upload()
        self.assertIsNone(restored.upload_summary)

    async def test_admin_http_upload_install_and_scoped_download(self):
        @web.middleware
        async def auth(request, handler):
            if request.path.endswith(("ota_upload", "ota_install")):
                credential = request.headers.get("Authorization", "")
                if not credential:
                    raise web.HTTPUnauthorized()
                request["hass_user"] = SimpleNamespace(
                    is_admin=credential == "Bearer synthetic-admin"
                )
            try:
                return await handler(request)
            except Unauthorized:
                raise web.HTTPUnauthorized() from None

        app = web.Application(middlewares=[auth])
        app[KEY_HASS] = self.hass
        upload, install, download = OtaUploadView(), OtaInstallView(), OtaDownloadView()
        self.assertTrue(upload.requires_auth)
        self.assertTrue(install.requires_auth)
        app.router.add_post(upload.url, upload.post)
        app.router.add_post(install.url, install.post)

        async def get(request):
            return await download.get(request, request.match_info["job_id"])

        app.router.add_get(download.url, get)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        admin = {
            "Authorization": "Bearer synthetic-admin",
            "Content-Type": "application/vnd.android.package-archive",
        }
        raw = fixtures.apk_bytes()
        try:
            async with ClientSession() as client:
                for credentials in ({}, {"Authorization": "Bearer synthetic-user"}):
                    async with client.post(
                        base + upload.url, data=raw, headers=credentials
                    ) as response:
                        self.assertEqual(401, response.status)
                async with client.post(
                    base + upload.url, data=b"not an APK", headers=admin
                ) as response:
                    self.assertEqual(400, response.status)
                async with client.post(
                    base + upload.url,
                    data=fixtures.apk_bytes(package="other.app"),
                    headers=admin,
                ) as response:
                    self.assertEqual(400, response.status)
                with patch(
                    "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
                    new_callable=AsyncMock,
                ) as publish:
                    async with client.post(
                        base + upload.url, data=raw, headers=admin
                    ) as response:
                        self.assertEqual(201, response.status)
                        metadata = await response.json()
                    publish.assert_not_awaited()
                    install_admin = {"Authorization": "Bearer synthetic-admin"}
                    async with client.post(
                        base + install.url,
                        json={"kiosk": "tablet_a", "upload_id": "0" * 32},
                        headers=install_admin,
                    ) as response:
                        self.assertEqual(400, response.status)
                    for credentials in ({}, {"Authorization": "Bearer synthetic-user"}):
                        async with client.post(
                            base + install.url,
                            json={
                                "kiosk": "tablet_a",
                                "upload_id": metadata["upload_id"],
                            },
                            headers=credentials,
                        ) as response:
                            self.assertEqual(401, response.status)
                    async with client.post(
                        base + install.url,
                        json={"kiosk": "tablet_a", "upload_id": metadata["upload_id"]},
                        headers=install_admin,
                    ) as response:
                        self.assertEqual(202, response.status)
                    command = json.loads(publish.call_args.args[2])
                async with client.get(base + command["download_path"]) as response:
                    self.assertEqual(401, response.status)
                async with client.get(
                    base + command["download_path"],
                    headers={"Authorization": "Bearer " + command["download_token"]},
                ) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual(raw, await response.read())
        finally:
            await runner.cleanup()
