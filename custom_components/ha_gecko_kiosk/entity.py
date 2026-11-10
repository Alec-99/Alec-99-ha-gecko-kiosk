"""Push-based kiosk device and entity registration over the existing protocol."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import time
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.event import async_call_later

from . import DOMAIN, _state, _valid_segment


@dataclass(frozen=True)
class KioskSpec:
    key: str
    name: str
    group: str
    field: str
    capability: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    device_class: str | None = None
    diagnostic: bool = False
    command: str | None = None
    suffix: str | None = None


SPECS = {
    "binary_sensor": (
        KioskSpec("online", "Online", "", "availability", device_class="connectivity", diagnostic=True),
        KioskSpec("running", "Kiosk actief", "status", "kiosk_running", suffix="status/kiosk_running", diagnostic=True),
        KioskSpec("charging", "Opladen", "battery", "charging", device_class="battery_charging", suffix="battery/charging"),
        KioskSpec("power_ready", "Schermbediening beschikbaar", "display", "power_control_ready", "display.power", suffix="display/power_control_ready", diagnostic=True),
    ),
    "sensor": (
        KioskSpec("battery", "Batterij", "battery", "level", minimum=0, maximum=100, unit="%", device_class="battery", suffix="battery/level"),
        KioskSpec("battery_temperature", "Batterijtemperatuur", "battery", "temperature", minimum=-50, maximum=150, unit="°C", device_class="temperature", suffix="battery/temperature"),
        KioskSpec("battery_voltage", "Batterijspanning", "battery", "voltage", minimum=0, maximum=100, unit="V", device_class="voltage", suffix="battery/voltage", diagnostic=True),
        KioskSpec("app_version", "Appversie", "diagnostics", "app_version", suffix="app/version", diagnostic=True),
        KioskSpec("watchdog", "Watchdogstatus", "diagnostics", "watchdog_status", suffix="watchdog/status", diagnostic=True),
        KioskSpec("restarts", "Watchdog-herstarts", "diagnostics", "watchdog_restart_count", minimum=0, suffix="watchdog/restart_count", diagnostic=True),
        KioskSpec("reconnects", "MQTT-herverbindingen", "diagnostics", "mqtt_reconnect_count", minimum=0, suffix="mqtt/reconnect_count", diagnostic=True),
        KioskSpec("command_result", "Laatste opdrachtresultaat", "last_device_response", "status", "command.acknowledged", diagnostic=True),
    ),
    "switch": (
        KioskSpec("screen", "Scherm", "display", "power", "display.power", command="screen", suffix="display/power"),
        KioskSpec("screensaver", "Schermbeveiliging", "status", "screensaver", "screensaver.activate", command="screensaver", suffix="status/screensaver"),
        KioskSpec("mute", "Dempen", "audio", "muted", "audio.mute", command="mute", suffix="audio/muted"),
    ),
    "number": (
        KioskSpec("brightness", "Schermhelderheid", "display", "brightness_percent", "display.brightness", minimum=1, maximum=100, unit="%", command="brightness", suffix="display/brightness_percent"),
        KioskSpec("volume", "Mediavolume", "audio", "volume_percent", "audio.volume", minimum=0, maximum=100, unit="%", command="volume", suffix="audio/volume_percent"),
    ),
    "update": (KioskSpec("app_update", "App-update", "ota", "version_code", "ota.install"),),
    "button": (
        KioskSpec("reload", "Dashboard vernieuwen", "", "", "dashboard.reload", command="reload_dashboard"),
    ),
}


def supported(state: dict, spec: KioskSpec) -> bool:
    manifest = state.get("capabilities")
    if spec.capability and manifest is not None:
        return manifest.get("compatible", False) and spec.capability in manifest.get("capabilities", [])
    if spec.key == "online":
        return True
    # Legacy clients retain only entities evidenced by their actual state.
    if spec.key == "reload" and manifest is None:
        return state.get("status", {}).get("kiosk_running") is not None
    return spec.field in (state.get(spec.group, {}) if spec.group else state)


def raw_value(state: dict, spec: KioskSpec) -> str | None:
    value = (state.get(spec.group, {}) if spec.group else state).get(spec.field)
    return value if isinstance(value, str) else None


def numeric_value(state: dict, spec: KioskSpec) -> float | None:
    try:
        value = float(raw_value(state, spec))
    except (ValueError, TypeError):
        return None
    if (not math.isfinite(value) or spec.minimum is not None and value < spec.minimum
            or spec.maximum is not None and value > spec.maximum):
        return None
    return value


class KioskRegistry:
    """One config-entry owner, with additive platforms and stable unique IDs."""
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.listeners: set[Callable] = set()
        self.devices: dict[str, str] = {}
        self.pending_discovery: dict[str, Callable] = {}

    def metadata(self, kiosk_id):
        return self.hass.data[DOMAIN].get("discovery_metadata", {}).get(kiosk_id, {})

    def device_info_values(self, kiosk_id):
        state = _state(self.hass)[kiosk_id]
        meta = self.metadata(kiosk_id)
        identifiers = {(DOMAIN, kiosk_id)}
        identifiers.update(("mqtt", item) for item in meta.get("identifiers", []))
        info = {"identifiers": identifiers, "name": meta.get("name", f"Kiosk {kiosk_id}"),
                "configuration_url": "homeassistant://ha-gecko-kiosk"}
        for field in ("manufacturer", "model"):
            if meta.get(field): info[field] = meta[field]
        version = state.get("diagnostics", {}).get("app_version")
        if version: info["sw_version"] = version
        return info

    def device_info(self, kiosk_id):
        return DeviceInfo(**self.device_info_values(kiosk_id))

    @callback
    def update(self, kiosk_id):
        if len(kiosk_id) > 64 or not _valid_segment(kiosk_id) or kiosk_id not in _state(self.hass): return
        info = self.device_info_values(kiosk_id)
        registry = dr.async_get(self.hass)
        # Preserve the proven physical MQTT identity. HA versions with per-entry
        # devices expose this as a linked device. Never infer it from a topic alias.
        device = registry.async_get_or_create(config_entry_id=self.entry.entry_id, **info)
        self.devices[kiosk_id] = device.id
        for listener in tuple(self.listeners): listener(kiosk_id)

    @callback
    def listen(self, listener):
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    @callback
    def metadata_updated(self, kiosk_id):
        if kiosk_id not in self.metadata_ids:
            return
        if cancel := self.pending_discovery.pop(kiosk_id, None):
            cancel()

        @callback
        def settled(_now):
            self.pending_discovery.pop(kiosk_id, None)
            self.update(kiosk_id)

        self.pending_discovery[kiosk_id] = async_call_later(self.hass, 2.1, settled)

    @property
    def metadata_ids(self):
        return self.hass.data[DOMAIN].get("discovery_metadata", {})

    def legacy_exists(self, platform, kiosk_id, spec):
        unique_id = self.metadata(kiosk_id).get("entities", {}).get(f"{platform}:{spec.suffix}")
        if unique_id is None:
            return False
        if er.async_get(self.hass).async_get_entity_id(platform, "mqtt", unique_id) is not None:
            return True
        # MQTT registers device-discovery entities asynchronously. Wait for its
        # registry entry before deciding that a native fallback is necessary.
        return time.monotonic() - self.metadata(kiosk_id).get("received_at", 0) < 2

    @callback
    def stop(self):
        self.listeners.clear()
        for cancel in self.pending_discovery.values():
            cancel()
        self.pending_discovery.clear()


class KioskEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, manager, kiosk_id, spec):
        self.manager = manager
        self.kiosk_id = kiosk_id
        self.spec = spec
        self._attr_unique_id = f"{kiosk_id}_{spec.key}"
        self._attr_name = spec.name
        self._attr_device_class = spec.device_class
        if spec.diagnostic: self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def kiosk(self): return _state(self.hass).get(self.kiosk_id, {})

    @property
    def device_info(self): return self.manager.device_info(self.kiosk_id)

    @property
    def available(self):
        if self.spec.key == "online": return True
        return self.kiosk.get("availability") == "online" and supported(self.kiosk, self.spec)

    async def async_added_to_hass(self):
        self.async_on_remove(self.manager.listen(self._updated))

    @callback
    def _updated(self, kiosk_id):
        if kiosk_id == self.kiosk_id: self.async_write_ha_state()

    async def async_command(self, value):
        if not self.available: raise HomeAssistantError("Kiosk is offline or capability is unavailable")
        await self.hass.services.async_call(DOMAIN, "device", {
            "kiosk": self.kiosk_id, "command": self.spec.command, "value": value,
        }, blocking=True)


async def setup_platform(hass, entry, async_add_entities, platform, entity_type):
    manager = hass.data[DOMAIN]["registry_manager"]
    created: set[tuple[str, str]] = set()

    @callback
    def discover(kiosk_id):
        state = _state(hass).get(kiosk_id, {})
        entities = []
        for spec in SPECS[platform]:
            key = (kiosk_id, spec.key)
            if key in created or not supported(state, spec): continue
            if manager.legacy_exists(platform, kiosk_id, spec): continue
            created.add(key)
            entities.append(entity_type(manager, kiosk_id, spec))
        if entities: async_add_entities(entities)

    entry.async_on_unload(manager.listen(discover))
    for kiosk_id in list(_state(hass)): discover(kiosk_id)
