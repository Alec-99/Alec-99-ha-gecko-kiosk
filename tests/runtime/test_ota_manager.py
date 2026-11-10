"""OTA orchestration contracts against the real HA APIs (no running HA needed)."""

import asyncio
import hashlib
import io
import zipfile
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web, ClientSession
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.http import KEY_HASS
from custom_components.ha_gecko_kiosk import DOMAIN
from custom_components.ha_gecko_kiosk.ota import Candidate, OtaDownloadView, OtaManager


class OtaManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.options = {
            "ota_repository": "Example/kiosk-builds",
            "ota_branch": "trusted-builds",
            "ota_workflow": "build.yml",
            "ota_token": "synthetic-github-token",
        }
        self.kiosk = {
            "id": "tablet_a",
            "availability": "online",
            "capabilities": {"compatible": True, "capabilities": ["ota.install"]},
            "ota": {"version_code": 10, "version_name": "1.0", "status": "idle"},
        }
        self.hass = SimpleNamespace(
            data={DOMAIN: {"kiosks": {"tablet_a": self.kiosk}}},
            config=SimpleNamespace(
                path=lambda *parts: str(Path(self.temp.name).joinpath(*parts))
            ),
            async_add_executor_job=lambda fn, *args: asyncio.to_thread(fn, *args),
        )
        self.timer_patch = patch(
            "custom_components.ha_gecko_kiosk.ota.async_call_later",
            return_value=lambda: None,
        )
        self.timer = self.timer_patch.start()
        self.addCleanup(self.timer_patch.stop)
        self.manager = OtaManager(self.hass, SimpleNamespace(options=self.options))
        self.hass.data[DOMAIN]["ota_manager"] = self.manager
        self.manager.candidate = Candidate(7, "1.1", "a" * 40)
        self.manager.check = AsyncMock()
        self.manifest = {
            "version_name": "1.1",
            "version_code": 11,
            "sha256": "b" * 64,
            "size": 12,
        }
        self.apk = Path(self.temp.name) / "fixture.apk"
        self.apk.write_bytes(b"fake fixture")
        self.manager.prepare = AsyncMock(return_value=(self.manifest, self.apk))

    async def test_scoped_download_and_command_do_not_expose_source_credential(self):
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as publish:
            await self.manager.install("tablet_a")
        args = publish.call_args
        self.assertEqual("ha_kiosk/tablet_a/command/ota", args.args[1])
        body = json.loads(args.args[2])
        self.assertNotIn(self.options["ota_token"], args.args[2])
        self.assertEqual({"qos": 1, "retain": False}, args.kwargs)
        self.assertGreater(body["expires_at_ms"], time.time() * 1000)
        request = SimpleNamespace(
            app={KEY_HASS: self.hass},
            headers={"Authorization": "Bearer " + body["download_token"]},
        )
        response = await OtaDownloadView().get(
            request, body["download_path"].split("/")[-1]
        )
        self.assertEqual("no-store", response.headers["Cache-Control"])
        self.assertNotIn("download_token", json.dumps(self.kiosk))
        request.headers = {"Authorization": "Bearer wrong"}
        with self.assertRaises(web.HTTPUnauthorized):
            await OtaDownloadView().get(request, body["download_path"].split("/")[-1])
        request.headers = {"Authorization": "Bearer non-ascii-\u00e9"}
        with self.assertRaises(web.HTTPUnauthorized):
            await OtaDownloadView().get(request, body["download_path"].split("/")[-1])
        request.headers = {"Authorization": "Bearer " + body["download_token"]}
        next(iter(self.manager.jobs.values()))["expires"] = 0
        with self.assertRaises(web.HTTPUnauthorized):
            await OtaDownloadView().get(request, body["download_path"].split("/")[-1])

    async def test_artifact_http_endpoint_streams_only_with_live_artifact_grant(self):
        self.manager.jobs["fixture"] = {
            "token": "synthetic-artifact-grant",
            "path": self.apk,
            "expires": time.monotonic() + 60,
        }
        app = web.Application()
        app[KEY_HASS] = self.hass
        view = OtaDownloadView()

        async def get(request):
            return await view.get(request, request.match_info["job_id"])

        app.router.add_get("/artifact/{job_id}", get)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as client:
                async with client.get(
                    f"http://127.0.0.1:{port}/artifact/fixture"
                ) as response:
                    self.assertEqual(401, response.status)
                async with client.get(
                    f"http://127.0.0.1:{port}/artifact/fixture",
                    headers={"Authorization": "Bearer synthetic-artifact-grant"},
                ) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual(self.apk.read_bytes(), await response.read())
                    self.assertEqual("no-store", response.headers["Cache-Control"])
        finally:
            await runner.cleanup()

    async def test_private_source_authentication_is_not_forwarded_to_storage_redirect(
        self,
    ):
        candidate = Candidate(7, "1.1", "a" * 40)
        manifest = {
            "schema": 1,
            "package_id": "com.alec.hageckokiosk",
            "version_name": "1.1",
            "version_code": 11,
            "source_commit": "a" * 40,
            "apk_filename": "fixture.apk",
            "size": self.apk.stat().st_size,
            "sha256": hashlib.sha256(self.apk.read_bytes()).hexdigest(),
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as bundle:
            bundle.writestr("ota-manifest.json", json.dumps(manifest))
            bundle.writestr("fixture.apk", self.apk.read_bytes())
        body = output.getvalue()

        class Response:
            def __init__(self, status, headers, payload=b""):
                self.status, self.headers, self.payload = status, headers, payload
                self.content_length = len(payload)
                self.content = self

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def iter_chunked(self, size):
                for start in range(0, len(self.payload), size):
                    yield self.payload[start : start + size]

        calls = []
        responses = [
            Response(
                302, {"Location": "https://fixture.blob.core.windows.net/artifact"}
            ),
            Response(200, {}, body),
        ]

        def get(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0)

        real = OtaManager(self.hass, SimpleNamespace(options=self.options))
        with patch(
            "custom_components.ha_gecko_kiosk.ota.async_get_clientsession",
            return_value=SimpleNamespace(get=get),
        ):
            received, path = await real.prepare(candidate)
        self.assertEqual(manifest, received)
        self.assertEqual(self.apk.read_bytes(), path.read_bytes())
        self.assertEqual(
            "Bearer synthetic-github-token", calls[0][1]["headers"]["Authorization"]
        )
        self.assertNotIn("headers", calls[1][1])
        self.assertFalse(calls[0][1]["allow_redirects"])
        self.assertFalse(calls[1][1]["allow_redirects"])
        responses[:] = [
            Response(302, {"Location": "https://example.invalid/untrusted"})
        ]
        rejected = OtaManager(self.hass, SimpleNamespace(options=self.options))
        with patch(
            "custom_components.ha_gecko_kiosk.ota.async_get_clientsession",
            return_value=SimpleNamespace(get=get),
        ):
            with self.assertRaises(HomeAssistantError):
                await rejected.prepare(candidate)
        self.assertEqual(3, len(calls), "Untrusted storage origin was contacted")

    async def test_lost_request_times_out_and_revokes_artifact_grant(self):
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ):
            await self.manager.install("tablet_a")
        self.timer.call_args.args[2](None)
        self.assertEqual("error", self.kiosk["ota"]["status"])
        self.assertEqual("timeout", self.kiosk["ota"]["detail"])
        self.assertFalse(self.manager.jobs)

    async def test_offline_downgrade_and_parallel_requests_are_blocked(self):
        with patch(
            "custom_components.ha_gecko_kiosk.ota.mqtt.async_publish",
            new_callable=AsyncMock,
        ) as publish:
            self.kiosk["availability"] = "offline"
            with self.assertRaises(HomeAssistantError):
                await self.manager.install("tablet_a")
            self.kiosk["availability"] = "online"
            self.manifest["version_code"] = 9
            with self.assertRaises(HomeAssistantError):
                await self.manager.install("tablet_a")
            self.manifest["version_code"] = 11
            await asyncio.gather(
                self.manager.install("tablet_a"),
                self.manager.install("tablet_a"),
                return_exceptions=True,
            )
            self.assertEqual(1, publish.await_count)

    async def test_ota_state_is_bounded_and_stale_job_cannot_overwrite_request(self):
        self.kiosk["ota"].update(status="requested", request_id="a" * 32)
        body = {
            "schema": 1,
            "status": "downloading",
            "request_id": "b" * 32,
            "version_code": 10,
            "version_name": "1.0",
            "progress": 25,
            "download_token": "synthetic-private-grant",
            "detail": "https://example.invalid/private",
        }
        self.manager.receive("tablet_a", json.dumps(body))
        self.assertEqual("requested", self.kiosk["ota"]["status"])
        body["request_id"] = "a" * 32
        self.manager.receive("tablet_a", json.dumps(body))
        self.assertEqual(25, self.kiosk["ota"]["progress"])
        self.assertNotIn("download_token", self.kiosk["ota"])
        self.assertNotIn("detail", self.kiosk["ota"])

    async def test_only_successful_same_repository_trusted_branch_build_is_selected(
        self,
    ):
        real = OtaManager(self.hass, SimpleNamespace(options=self.options))
        base = {
            "conclusion": "success",
            "event": "push",
            "head_branch": "trusted-builds",
            "head_repository": {"full_name": "Example/kiosk-builds"},
            "head_sha": "a" * 40,
            "id": 4,
        }
        fake_runs = [
            dict(base, head_branch="untrusted"),
            dict(base, event="pull_request"),
            dict(base, head_repository={"full_name": "Other/fork"}),
            base,
        ]
        artifact = {
            "name": "ha-gecko-kiosk-v1.1-sm-t580-run-1-attempt-1",
            "id": 7,
            "expired": False,
            "size_in_bytes": 100,
        }

        async def github(path):
            if "workflows" in path:
                return {"workflow_runs": fake_runs}
            self.assertIn("/runs/4/", path)
            return {"artifacts": [artifact]}

        real.github_json = github
        await real.check()
        self.assertEqual(Candidate(7, "1.1", "a" * 40), real.candidate)
