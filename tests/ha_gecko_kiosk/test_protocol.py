"""Contract tests with a stubbed HA host (not a replacement for a live HA integration test).

This checks our command/response logic without starting a broker, operating a door,
or importing the complete Home Assistant runtime on a GitHub Actions worker.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import time
import types
import unittest


def install_stubs():
    def module(name):
        m = types.ModuleType(name)
        sys.modules[name] = m
        parent, _, attr = name.rpartition(".")
        if parent:
            setattr(sys.modules[parent], attr, m)
        return m

    module("homeassistant")
    module("homeassistant.components")
    mqtt = module("homeassistant.components.mqtt")
    module("homeassistant.components.panel_custom")
    ws = module("homeassistant.components.websocket_api")
    module("homeassistant.components.http").StaticPathConfig = type("StaticPathConfig", (), {})
    module("homeassistant.config_entries").ConfigEntry = type("ConfigEntry", (), {})
    module("homeassistant.const").EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
    core = module("homeassistant.core")
    core.Event = type("Event", (), {})
    core.HomeAssistant = type("HomeAssistant", (), {})
    core.ServiceCall = type("ServiceCall", (), {})
    core.callback = lambda f: f
    module("homeassistant.helpers")
    cv = module("homeassistant.helpers.config_validation")
    cv.string = str
    cv.boolean = bool
    cv.empty_config_schema = lambda domain: {}
    module("homeassistant.helpers.typing").ConfigType = dict

    vol = module("voluptuous")
    vol.Invalid = type("Invalid", (Exception,), {})
    vol.Required = lambda key, **kw: key
    vol.Optional = lambda key, **kw: key
    vol.Schema = lambda item: item
    vol.All = lambda *values: values
    vol.In = lambda options: options
    vol.Length = lambda **kw: kw
    vol.Coerce = lambda kind: kind
    vol.Range = lambda **kw: kw
    vol.Match = lambda pattern: pattern

    ws.websocket_command = lambda schema: (lambda fn: fn)
    ws.require_admin = lambda fn: fn
    ws.ActiveConnection = type("ActiveConnection", (), {})
    return mqtt


mqtt_stub = install_stubs()
path = Path(__file__).resolve().parents[2] / "custom_components/ha_gecko_kiosk/__init__.py"
spec = importlib.util.spec_from_file_location("kiosk_protocol_tested", path)
kiosk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kiosk)


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, name, data):
        self.events.append((name, data))


class FakeHass:
    def __init__(self):
        self.data = {kiosk.DOMAIN: {}}
        self.bus = FakeBus()
        self.publishes = []


async def async_publish(hass, topic, payload, qos=0, retain=False):
    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError):
        decoded = payload
    hass.publishes.append((topic, decoded, qos, retain))


mqtt_stub.async_publish = async_publish


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.hass = FakeHass()

    def test_popup_response_must_match_origin_and_is_single_use(self):
        data = {
            "kiosk": "tablet_a",
            "kind": "confirmation",
            "camera": "doorbell",
            "popup_name": "garage_gate",
            "title": "Garagepoort bedienen?",
            "message": "Wil je de garagepoort bedienen?",
            "confirm_label": "Bevestigen",
            "cancel_label": "Annuleren",
        }
        asyncio.run(kiosk._service_popup(self.hass, types.SimpleNamespace(data=data)))
        topic, payload, qos, retain = self.hass.publishes[-1]
        self.assertEqual("ha_kiosk/tablet_a/command/popup", topic)
        self.assertFalse(retain)
        self.assertEqual(1, qos)
        self.assertGreater(payload["expires_at_ms"], int(time.time() * 1000))
        popup_id = payload["popup_id"]

        # A different device may not consume or acknowledge the pending request.
        wrong = types.SimpleNamespace(
            topic="ha_kiosk/tablet_b/popup/response",
            payload=json.dumps({"popup_id": popup_id, "response": "confirm"}),
        )
        kiosk._handle_popup_response(self.hass, wrong)
        self.assertEqual([], self.hass.bus.events)
        self.assertIn(popup_id, self.hass.data[kiosk.DOMAIN]["pending_popups"])

        valid = types.SimpleNamespace(
            topic="ha_kiosk/tablet_a/popup/response",
            payload=json.dumps({"popup_id": popup_id, "response": "confirm"}),
        )
        kiosk._handle_popup_response(self.hass, valid)
        self.assertEqual(1, len(self.hass.bus.events))
        self.assertEqual("garage_gate", self.hass.bus.events[0][1]["popup_name"])
        kiosk._handle_popup_response(self.hass, valid)
        self.assertEqual(1, len(self.hass.bus.events), "Duplicate response must not retrigger gate")

    def test_settings_ack_is_correlated_to_actual_request(self):
        asyncio.run(kiosk._send_settings_command(
            self.hass, "tablet_a", "update", "screensaver",
            {"clock_text_size_sp": 116},
        ))
        topic, payload, qos, retain = self.hass.publishes[-1]
        self.assertEqual("ha_kiosk/tablet_a/command/settings", topic)
        self.assertFalse(retain)
        self.assertEqual({"clock_text_size_sp": 116}, payload["changes"])
        request_id = payload["request_id"]

        def response(device, body):
            return types.SimpleNamespace(
                topic="ha_kiosk/" + device + "/settings/response",
                payload=json.dumps(body),
            )

        kiosk._handle_settings_response(self.hass, response(
            "tablet_b", {"request_id": request_id, "status": "applied"}))
        self.assertIn(request_id, self.hass.data[kiosk.DOMAIN]["pending_settings"])
        self.assertNotIn("last_settings_response", kiosk._ensure_kiosk(self.hass, "tablet_a"))
        kiosk._handle_settings_response(self.hass, response("tablet_a", [1, 2]))
        kiosk._handle_settings_response(self.hass, response(
            "tablet_a", {"request_id": "forged-id", "status": "applied"}))
        self.assertIn(request_id, self.hass.data[kiosk.DOMAIN]["pending_settings"])
        kiosk._handle_settings_response(self.hass, response(
            "tablet_a", {"request_id": request_id, "status": "applied"}))
        result = kiosk._ensure_kiosk(self.hass, "tablet_a")["last_settings_response"]
        self.assertEqual(request_id, result["request_id"])
        self.assertEqual("applied", result["status"])

    def test_notification_is_not_retained_and_has_expiry(self):
        call = types.SimpleNamespace(data={
            "kiosk": "tablet_a", "action": "show", "notification_id": "garage_open",
            "level": "warning", "title": "Garage",
            "message": "De poort staat open.", "duration_seconds": 60,
            "show_screensaver": True,
        })
        before = int(time.time() * 1000)
        asyncio.run(kiosk._service_notification(self.hass, call))
        topic, payload, qos, retain = self.hass.publishes[-1]
        self.assertEqual("ha_kiosk/tablet_a/command/notification", topic)
        self.assertFalse(retain)
        self.assertEqual("garage_open", payload["id"])
        self.assertTrue(before + 59_000 <= payload["expires_at_ms"] <= before + 61_000)
        self.assertTrue(payload["show_screensaver"])

    def test_capability_manifest_is_versioned_sorted_and_keeps_unknown_capabilities(self):
        message = types.SimpleNamespace(
            topic="ha_kiosk/tablet_a/status/capabilities",
            payload=json.dumps({
                "schema": 1,
                "protocol_version": 1,
                "capabilities": ["diagnostics.basic", "display.power", "vendor.custom"],
                "resources": {"cameras": ["entry_cam", "yard"]},
            }),
        )
        kiosk._handle_status(self.hass, message)
        manifest = kiosk._ensure_kiosk(self.hass, "tablet_a")["capabilities"]
        self.assertTrue(manifest["compatible"])
        self.assertEqual(
            ["diagnostics.basic", "display.power", "vendor.custom"],
            manifest["capabilities"],
        )
        self.assertEqual(["entry_cam", "yard"], manifest["resources"]["cameras"])

    def test_invalid_or_unsupported_capability_manifest_fails_closed(self):
        for payload in (
            "not-json",
            '{"schema":1,"protocol_version":1,"capabilities":["\\ud800"]}',
            json.dumps({"schema": 1, "protocol_version": 1, "capabilities": ["bad/id"]}),
            json.dumps({"schema": 1, "protocol_version": 1, "capabilities": ["camera.external"],
                        "resources": {"cameras": ["bad/id"]}}),
            json.dumps({"schema": 1, "protocol_version": 2, "capabilities": ["display.power"]}),
        ):
            parsed = kiosk._parse_capability_manifest(payload)
            self.assertFalse(parsed["compatible"])

    def test_explicit_capabilities_gate_commands_but_legacy_devices_keep_working(self):
        kiosk._handle_status(self.hass, types.SimpleNamespace(
            topic="ha_kiosk/tablet_a/status/capabilities",
            payload=json.dumps({"schema": 1, "protocol_version": 1, "capabilities": ["display.power"]}),
        ))
        with self.assertRaises(kiosk.vol.Invalid):
            asyncio.run(kiosk._service_device(self.hass, types.SimpleNamespace(data={
                "kiosk": "tablet_a", "command": "screensaver", "value": "ON",
            })))
        asyncio.run(kiosk._service_device(self.hass, types.SimpleNamespace(data={
            "kiosk": "legacy_tablet", "command": "screensaver", "value": "ON",
        })))
        self.assertEqual("ha_kiosk/legacy_tablet/command/device/screensaver", self.hass.publishes[-1][0])

    def test_capability_gate_covers_camera_notification_and_popup_services(self):
        kiosk._handle_status(self.hass, types.SimpleNamespace(
            topic="ha_kiosk/tablet_a/status/capabilities",
            payload=json.dumps({"schema": 1, "protocol_version": 1,
                               "capabilities": ["display.power"]}),
        ))
        calls = (
            (kiosk._service_camera, {"kiosk": "tablet_a", "action": "show", "camera": "front"}),
            (kiosk._service_notification, {"kiosk": "tablet_a", "action": "show",
                                           "notification_id": "test", "level": "info",
                                           "title": "Test", "message": "Synthetic",
                                           "duration_seconds": 10, "show_screensaver": False}),
            (kiosk._service_popup, {"kiosk": "tablet_a", "kind": "confirmation",
                                    "popup_name": "test", "title": "Test",
                                    "message": "Synthetic", "confirm_label": "Yes",
                                    "cancel_label": "No", "camera": "front"}),
        )
        for service, data in calls:
            with self.subTest(service=service.__name__), self.assertRaises(kiosk.vol.Invalid):
                asyncio.run(service(self.hass, types.SimpleNamespace(data=data)))
        self.assertEqual([], self.hass.publishes)


if __name__ == "__main__":
    unittest.main()
