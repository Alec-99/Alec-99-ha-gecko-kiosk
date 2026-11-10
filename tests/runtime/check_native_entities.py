"""Live contract test. Use ONLY a disposable HA instance and MQTT broker.

Requires aiohttp and paho-mqtt. HA_TEST_TOKEN is an admin token for that instance.
Creates fictional devices, exercises controls and reloads only ha_gecko_kiosk.
"""
import argparse
import asyncio
import json
import os
import time
from urllib.parse import urlparse

import aiohttp
import paho.mqtt.client as mqtt

DOMAIN = "ha_gecko_kiosk"
KIOSK = "qa_native_tablet"
CAPS = ["display.power", "display.brightness", "audio.volume", "audio.mute",
        "screensaver.activate", "dashboard.reload", "command.acknowledged"]


async def main(args):
    commands = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    def received(_client, _userdata, message):
        if message.topic == f"ha_kiosk/{KIOSK}/command/device/request":
            commands.append((message.topic, json.loads(message.payload), message.qos, message.retain))
    client.on_message = received
    client.connect(args.broker, args.port)
    client.subscribe(f"ha_kiosk/{KIOSK}/command/#", qos=1)
    client.loop_start()

    def publish(suffix, value, kiosk=KIOSK):
        client.publish(f"ha_kiosk/{kiosk}/{suffix}", value if isinstance(value, str)
                       else json.dumps(value), qos=1, retain=True).wait_for_publish()

    headers = {"Authorization": "Bearer " + os.environ["HA_TEST_TOKEN"]}
    async with aiohttp.ClientSession(headers=headers) as session:
        async def api(path, data=None):
            async with session.request("GET" if data is None else "POST",
                                       args.url + path, json=data) as response:
                text = await response.text()
                if response.status >= 400:
                    raise AssertionError(f"HA API {path}: status {response.status}")
                return json.loads(text) if text else None

        async with session.ws_connect(args.url + "/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": os.environ["HA_TEST_TOKEN"]})
            assert (await ws.receive_json())["type"] == "auth_ok"
            sequence = 0

            async def request(kind, **data):
                nonlocal sequence
                sequence += 1
                await ws.send_json({"id": sequence, "type": kind, **data})
                result = await ws.receive_json()
                assert result.get("success"), result
                return result.get("result")

            async def entities(kiosk=KIOSK):
                return {e["unique_id"][len(kiosk)+1:]: e for e in
                        await request("config/entity_registry/list")
                        if e["platform"] == DOMAIN and e["unique_id"].startswith(kiosk + "_")}

            async def wait_for(check, description):
                for _ in range(80):
                    result = await check()
                    if result: return result
                    await asyncio.sleep(.1)
                raise AssertionError("Timed out: " + description)

            async def state(key):
                registry = await entities()
                if key not in registry: return None
                states = {s["entity_id"]: s["state"] for s in await api("/api/states")}
                return states.get(registry[key]["entity_id"])

            async def is_state(key, expected):
                return await state(key) == expected

            publish("status/capabilities", {"schema": 1, "protocol_version": 1, "capabilities": CAPS})
            for suffix, value in {"availability": "online", "status/kiosk_running": "true",
                                  "status/screensaver": "false", "battery/level": "73",
                                  "battery/charging": "true", "battery/temperature": "24.5",
                                  "battery/voltage": "4.05", "display/power": "ON",
                                  "display/power_control_ready": "true",
                                  "display/brightness_percent": "55", "audio/volume_percent": "20",
                                  "audio/muted": "false", "app/version": "0.8.5",
                                  "watchdog/status": "healthy", "watchdog/restart_count": "0",
                                  "mqtt/reconnect_count": "1"}.items(): publish(suffix, value)
            await wait_for(lambda: is_state("brightness", "55.0"), "brightness state")
            registry = await entities()
            assert len(registry) == 18, sorted(registry)
            assert len({e["device_id"] for e in registry.values()}) == 1
            devices = await request("config/device_registry/list")
            device = next(d for d in devices if d["id"] == registry["brightness"]["device_id"])
            assert [DOMAIN, KIOSK] in device["identifiers"]
            assert device["sw_version"] == "0.8.5"
            for key, expected in {"online": "on", "battery": "73.0", "charging": "on",
                                  "screen": "on", "screensaver": "off", "mute": "off"}.items():
                assert await state(key) == expected, (key, await state(key))

            for key, service, value in [("brightness", "number/set_value", 37),
                                        ("screensaver", "switch/turn_on", None),
                                        ("reload", "button/press", None)]:
                data = {"entity_id": registry[key]["entity_id"]}
                if value is not None: data["value"] = value
                await api("/api/services/" + service, data)
            await asyncio.sleep(.3)
            assert [item[1]["command"] for item in commands] == ["brightness", "screensaver", "system"]
            assert [item[1]["value"] for item in commands] == ["37", "ON", "reload_dashboard"]
            assert all(qos == 1 and not retained for _, _, qos, retained in commands)
            assert all(item[1]["expires_at_ms"] > int(time.time()*1000) for item in commands)
            publish("device/response", {"schema": 1, "request_id": commands[-1][1]["request_id"], "status": "applied"})
            await wait_for(lambda: is_state("command_result", "applied"), "correlated acknowledgement")
            assert await state("brightness") == "55.0", "Commands must not optimistically overwrite reported state"
            publish("display/brightness_percent", "37")
            await wait_for(lambda: is_state("brightness", "37.0"), "reported brightness")
            publish("availability", "offline")
            await wait_for(lambda: is_state("online", "off"), "offline connectivity")
            assert await state("brightness") == "unavailable"
            count = len(commands)
            try:
                await api("/api/services/number/set_value", {"entity_id": registry["brightness"]["entity_id"], "value": 25})
            except AssertionError: pass
            assert len(commands) == count, "Offline entity published a command"
            publish("availability", "online")
            publish("status/capabilities", {"schema": 1, "protocol_version": 1, "capabilities": ["dashboard.reload"]})
            await wait_for(lambda: is_state("brightness", "unavailable"), "revoked capability")
            publish("status/capabilities", {"schema": 1, "protocol_version": 1, "capabilities": CAPS})
            await wait_for(lambda: is_state("brightness", "37.0"), "restored capability")
            entry = next(e for e in await api("/api/config/config_entries/entry") if e["domain"] == DOMAIN)
            assert await api("/api/config/config_entries/entry/" + entry["entry_id"] + "/reload", {})
            await wait_for(lambda: is_state("brightness", "37.0"), "reload with retained state")
            after = await entities()
            assert {k: e["entity_id"] for k, e in after.items()} == {k: e["entity_id"] for k, e in registry.items()}
            # Android's existing device discovery must retain the same physical
            # device and MQTT entities when the custom integration attaches.
            legacy = "qa_discovery_tablet_v2"
            discovery = {
                "dev": {"ids": ["qa_discovery_device_v2"], "name": "QA discovery tablet",
                        "mf": "Synthetic", "mdl": "Test tablet"},
                "o": {"name": "Synthetic test", "sw": "1"},
                "cmps": {"battery": {"p": "sensor", "unique_id": "qa_discovery_battery_v2",
                           "name": "Battery", "state_topic": f"ha_kiosk/{legacy}/battery/level",
                           "unit_of_measurement": "%", "device_class": "battery"}},
            }
            client.publish(f"homeassistant/device/{legacy}/config", json.dumps(discovery),
                           qos=1, retain=True).wait_for_publish()
            publish("battery/level", "64", legacy)
            publish("availability", "online", legacy)
            await asyncio.sleep(3)
            all_entities = await request("config/entity_registry/list")
            mqtt_battery = [e for e in all_entities if e["platform"] == "mqtt"
                            and e["unique_id"] == "qa_discovery_battery_v2"]
            assert len(mqtt_battery) == 1, "Existing MQTT device discovery did not load"
            native = await entities(legacy)
            assert "battery" not in native, "Duplicate native battery beside MQTT discovery"
            native_device = native["online"]["device_id"]
            mqtt_device = mqtt_battery[0]["device_id"]
            if native_device != mqtt_device:
                # Recent HA versions own one registry device per config entry,
                # with explicit links for the same physical device.
                linked = await request("config/device_registry/list_linked_devices", device_id=native_device)
                assert mqtt_device in linked["linked_devices"], "Physical device identity was lost"
            print("PASS: MQTT discovery device identity and existing battery entity reused")
            print("PASS: native device, 18 entities, reported state, MQTT commands/acks, offline, capability revocation and reload")
    client.disconnect()
    client.loop_stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--confirm-isolated-test-instance", action="store_true", required=True)
    args = parser.parse_args()
    assert urlparse(args.url).hostname in ("127.0.0.1", "localhost"), "Use loopback test HA only"
    asyncio.run(main(args))
