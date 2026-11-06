"""Home Assistant management layer for HA Gecko Kiosk tablets."""

from __future__ import annotations

import json
from hashlib import sha256
import re
import time
from uuid import uuid4
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import mqtt, panel_custom, websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

DOMAIN = "ha_gecko_kiosk"
TOPIC_PREFIX = "ha_kiosk"
DATA_KIOSKS = "kiosks"
DATA_UNSUBS = "unsubs"
STATIC_URL = "/ha_gecko_kiosk_static"
PANEL_URL = "ha-gecko-kiosk"

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

SERVICE_CAMERA = "camera"
SERVICE_DEVICE = "device"
SERVICE_POPUP = "popup"
SERVICE_NOTIFICATION = "notification"
SERVICE_SET_SCREENSAVER = "set_screensaver"
SERVICE_SET_CAMERA_POPUP = "set_camera_popup"
SERVICE_GET_SETTINGS = "get_settings"
SERVICE_RESET_SETTINGS = "reset_settings"
POPUP_RESPONSE_EVENT = "ha_gecko_kiosk_popup_response"
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
RESOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
CAPABILITY_MANIFEST_MAX_BYTES = 4096
CAPABILITY_MANIFEST_MAX_ITEMS = 64

CAMERA_SCHEMA = vol.Schema(
    {
        vol.Required("kiosk"): cv.string,
        vol.Required("action"): vol.In(["prewarm", "show", "hide", "stop"]),
        vol.Optional("camera", default="doorbell"): cv.string,
    }
)


DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("kiosk"): cv.string,
        vol.Required("command"): vol.In(["screen", "screensaver", "brightness", "volume", "mute", "reload_dashboard"]),
        vol.Required("value"): cv.string,
    }
)


_HEX_COLOR = vol.Match(r"^#[0-9a-fA-F]{6}$")
_KIOSK_FIELD = {vol.Required("kiosk"): cv.string}
SCREENSAVER_FIELDS = {
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("inactivity_timeout_seconds"): vol.All(vol.Coerce(int), vol.Range(min=5, max=86400)),
    vol.Optional("show_clock"): cv.boolean,
    vol.Optional("show_date"): cv.boolean,
    vol.Optional("consume_wake_touch"): cv.boolean,
    vol.Optional("clock_text_size_sp"): vol.All(vol.Coerce(int), vol.Range(min=12, max=200)),
    vol.Optional("date_text_size_sp"): vol.All(vol.Coerce(int), vol.Range(min=10, max=100)),
    vol.Optional("clock_update_interval_seconds"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
    vol.Optional("background_color"): _HEX_COLOR,
    vol.Optional("text_color"): _HEX_COLOR,
}
CAMERA_POPUP_FIELDS = {
    vol.Optional("width_percent"): vol.All(vol.Coerce(int), vol.Range(min=40, max=100)),
    vol.Optional("height_percent"): vol.All(vol.Coerce(int), vol.Range(min=40, max=100)),
    vol.Optional("dim_percent"): vol.All(vol.Coerce(int), vol.Range(min=0, max=95)),
}
SET_SCREENSAVER_SCHEMA = vol.Schema({**_KIOSK_FIELD, **SCREENSAVER_FIELDS})
SET_CAMERA_POPUP_SCHEMA = vol.Schema({**_KIOSK_FIELD, **CAMERA_POPUP_FIELDS})
GET_SETTINGS_SCHEMA = vol.Schema(_KIOSK_FIELD)
RESET_SETTINGS_SCHEMA = vol.Schema({
    **_KIOSK_FIELD,
    vol.Required("section"): vol.In(["screensaver", "camera_popup"]),
})


NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("kiosk"): cv.string,
        vol.Optional("action", default="show"): vol.In(["show", "clear"]),
        vol.Optional("notification_id", default=""): vol.All(cv.string, vol.Length(max=80)),
        vol.Optional("level", default="warning"): vol.In(["info", "warning", "critical"]),
        vol.Optional("title", default=""): vol.All(cv.string, vol.Length(max=80)),
        vol.Optional("message", default=""): vol.All(cv.string, vol.Length(max=300)),
        vol.Optional("duration_seconds", default=60): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=600)
        ),
        vol.Optional("show_screensaver", default=False): cv.boolean,
    }
)


POPUP_SCHEMA = vol.Schema(
    {
        vol.Required("kiosk"): cv.string,
        vol.Required("kind"): vol.In(["confirmation", "message", "camera"]),
        vol.Optional("popup_name", default="custom"): vol.All(cv.string, vol.Length(min=1, max=64)),
        vol.Optional("title", default=""): vol.All(cv.string, vol.Length(max=96)),
        vol.Optional("message", default=""): vol.All(cv.string, vol.Length(max=800)),
        vol.Optional("confirm_label", default="Bevestigen"): vol.All(cv.string, vol.Length(max=32)),
        vol.Optional("cancel_label", default="Annuleren"): vol.All(cv.string, vol.Length(max=32)),
        vol.Optional("camera", default="doorbell"): vol.All(cv.string, vol.Length(min=1, max=64)),
    }
)


def _valid_segment(value: str) -> bool:
    return bool(value) and not any(c in value for c in "/+#")


def _state(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_KIOSKS, {})


def _ensure_kiosk(hass: HomeAssistant, kiosk_id: str) -> dict[str, Any]:
    kiosks = _state(hass)
    return kiosks.setdefault(
        kiosk_id,
        {
            "id": kiosk_id,
            "availability": "unknown",
            "status": {},
            "battery": {},
            "display": {},
            "audio": {},
            "diagnostics": {},
        },
    )


def _topic_parts(message: mqtt.ReceiveMessage) -> list[str]:
    return message.topic.split("/")


@callback
def _handle_availability(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    parts = _topic_parts(message)
    if len(parts) != 3 or parts[0] != TOPIC_PREFIX or parts[2] != "availability":
        return
    kiosk = _ensure_kiosk(hass, parts[1])
    kiosk["availability"] = str(message.payload)


@callback
def _handle_status(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX or parts[2] != "status":
        return
    kiosk = _ensure_kiosk(hass, parts[1])
    if parts[3] == "capabilities":
        kiosk["capabilities"] = _parse_capability_manifest(message.payload)
        return
    kiosk["status"][parts[3]] = str(message.payload)


@callback
def _handle_device_state(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    """Keep the kiosk's public display/audio read model available to the panel."""
    parts = _topic_parts(message)
    if (len(parts) != 4 or parts[0] != TOPIC_PREFIX
            or parts[2] not in ("display", "audio")
            or parts[3] not in {"power", "power_state_detail", "power_control_ready",
                                "brightness_percent", "volume_percent", "muted"}):
        return
    value = str(message.payload).strip()
    if len(value) > 128:
        return
    _ensure_kiosk(hass, parts[1])[parts[2]][parts[3]] = value


@callback
def _handle_device_response(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    """Accept only a live response correlated to a command sent to this kiosk."""
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX or parts[2:] != ["device", "response"]:
        return
    if not isinstance(message.payload, str) or len(message.payload) > 4096:
        return
    try:
        payload = json.loads(message.payload)
    except (ValueError, TypeError):
        return
    if not isinstance(payload, dict) or type(payload.get("schema")) is not int or payload["schema"] != 1:
        return
    request_id = payload.get("request_id")
    status = payload.get("status")
    if (not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id)
            or not isinstance(status, str)
            or status not in {"applied", "rejected", "unsupported", "unavailable", "expired", "error"}):
        return
    pending = hass.data.get(DOMAIN, {}).get("pending_device_commands", {})
    request = pending.get(request_id)
    if request is None or request["kiosk"] != parts[1] or request["expires"] < time.monotonic():
        return
    pending.pop(request_id, None)
    state = _ensure_kiosk(hass, parts[1])
    state["last_device_response"] = {
        "request_id": request_id,
        "status": status,
        "detail": str(payload.get("detail", ""))[:200],
    }


@callback
def _handle_diagnostic_state(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    """Keep only low-sensitivity, generic diagnostic values for the admin panel."""
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX:
        return
    allowed = {
        ("app", "version"),
        ("mqtt", "reconnect_count"),
        ("watchdog", "status"),
        ("watchdog", "restart_count"),
    }
    if (parts[2], parts[3]) not in allowed:
        return
    value = str(message.payload).strip()
    if len(value) > 128:
        return
    _ensure_kiosk(hass, parts[1])["diagnostics"][f"{parts[2]}_{parts[3]}"] = value


def _parse_capability_manifest(payload: str) -> dict[str, Any]:
    """Validate the versioned manifest and fail closed for declared bad data."""
    invalid = {"compatible": False, "protocol_version": None, "capabilities": []}
    if not isinstance(payload, str):
        return invalid
    try:
        if len(payload.encode("utf-8")) > CAPABILITY_MANIFEST_MAX_BYTES:
            return invalid
    except UnicodeEncodeError:
        return invalid
    try:
        value = json.loads(payload)
    except (ValueError, TypeError):
        return invalid
    if not isinstance(value, dict):
        return invalid

    schema = value.get("schema")
    version = value.get("protocol_version")
    capabilities = value.get("capabilities")
    resources = value.get("resources", {})
    if (type(schema) is not int or type(version) is not int
            or not isinstance(capabilities, list)
            or len(capabilities) > CAPABILITY_MANIFEST_MAX_ITEMS
            or not isinstance(resources, dict)):
        return invalid
    if any(not isinstance(item, str) or not CAPABILITY_ID_PATTERN.fullmatch(item)
           for item in capabilities):
        return invalid
    camera_ids = resources.get("cameras", [])
    if (not isinstance(camera_ids, list)
            or len(camera_ids) > CAPABILITY_MANIFEST_MAX_ITEMS
            or any(not isinstance(item, str) or not RESOURCE_ID_PATTERN.fullmatch(item)
                   for item in camera_ids)):
        return invalid

    return {
        "compatible": schema == 1 and version == 1,
        "protocol_version": version,
        "capabilities": sorted(set(capabilities)),
        "resources": {"cameras": sorted(set(camera_ids))},
    }


def _require_capability(hass: HomeAssistant, kiosk_id: str, capability: str) -> None:
    """Keep legacy devices usable while enforcing an explicit manifest."""
    state = _state(hass).get(kiosk_id)
    if state is None or "capabilities" not in state:
        return
    manifest = state["capabilities"]
    if not manifest.get("compatible"):
        raise vol.Invalid("Kiosk capability manifest is invalid or uses an unsupported protocol version")
    if capability not in manifest["capabilities"]:
        raise vol.Invalid(f"Kiosk does not support {capability}")


def _require_any_capability(
    hass: HomeAssistant, kiosk_id: str, capabilities: tuple[str, ...]
) -> None:
    state = _state(hass).get(kiosk_id)
    if state is None or "capabilities" not in state:
        return
    manifest = state["capabilities"]
    if not manifest.get("compatible"):
        raise vol.Invalid("Kiosk capability manifest is invalid or uses an unsupported protocol version")
    if not set(capabilities).intersection(manifest["capabilities"]):
        raise vol.Invalid("Kiosk does not support any of the requested settings capabilities")


@callback
def _handle_battery(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX or parts[2] != "battery":
        return
    kiosk = _ensure_kiosk(hass, parts[1])
    kiosk["battery"][parts[3]] = str(message.payload)


@callback
def _handle_popup_response(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX or parts[2:] != ["popup", "response"]:
        return
    try:
        body = json.loads(message.payload)
        popup_id = body.get("popup_id")
        answer = body.get("response")
    except (ValueError, TypeError, AttributeError):
        return
    if not isinstance(popup_id, str) or answer not in ("confirm", "cancel", "dismiss", "error"):
        return
    pending = hass.data.get(DOMAIN, {}).get("pending_popups", {})
    request = pending.get(popup_id)
    if (request is None or request["kiosk"] != parts[1]
            or request["expires"] < time.monotonic()):
        return
    # Only consume a pending confirmation after validating its originating kiosk.
    pending.pop(popup_id, None)
    hass.bus.async_fire(POPUP_RESPONSE_EVENT, {
        "popup_id": popup_id,
        "popup_name": request["popup_name"],
        "kiosk": request["kiosk"],
        "response": answer,
    })


@callback
def _handle_settings_state(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX or parts[2:] != ["settings", "state"]:
        return
    if len(message.payload) > 4096:
        return
    try:
        payload = json.loads(message.payload)
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            return
        sections = payload.get("sections")
        if not isinstance(sections, dict):
            return
        if not isinstance(sections.get("screensaver"), dict) or not isinstance(
                sections.get("camera_popup"), dict):
            return
    except (ValueError, TypeError, AttributeError):
        return
    kiosk = _ensure_kiosk(hass, parts[1])
    kiosk["settings"] = sections


@callback
def _handle_settings_response(hass: HomeAssistant, message: mqtt.ReceiveMessage) -> None:
    parts = _topic_parts(message)
    if len(parts) != 4 or parts[0] != TOPIC_PREFIX or parts[2:] != ["settings", "response"]:
        return
    if len(message.payload) > 4096:
        return
    try:
        payload = json.loads(message.payload)
        if not isinstance(payload, dict) or payload.get("status") not in ("applied", "error"):
            return
    except (ValueError, TypeError, AttributeError):
        return
    request_id = payload.get("request_id")
    if not isinstance(request_id, str):
        return
    pending = hass.data.get(DOMAIN, {}).get("pending_settings", {})
    request = pending.get(request_id)
    if request is None or request["kiosk"] != parts[1] or request["expires"] < time.monotonic():
        return
    pending.pop(request_id, None)
    kiosk = _ensure_kiosk(hass, parts[1])
    kiosk["last_settings_response"] = {
        "request_id": request_id,
        "status": payload["status"],
        "detail": str(payload.get("detail", ""))[:200],
    }


def _kiosk_topic(kiosk_id: str, suffix: str) -> str:
    return f"{TOPIC_PREFIX}/{kiosk_id}/{suffix}"


async def _service_camera(hass: HomeAssistant, call: ServiceCall) -> None:
    kiosk = call.data["kiosk"].strip()
    action = call.data["action"]
    camera = call.data["camera"].strip()
    if not kiosk or any(char in kiosk for char in "/+#") or not camera or any(char in camera for char in "/+#"):
        raise vol.Invalid("Invalid kiosk or camera ID")
    _require_capability(hass, kiosk, "camera.external")
    payload = json.dumps({"action": action, "camera": camera})
    await mqtt.async_publish(
        hass,
        _kiosk_topic(kiosk, "command/camera"),
        payload,
        qos=1,
        retain=False,
    )


async def _service_device(hass: HomeAssistant, call: ServiceCall) -> None:
    """Send only explicit supported commands; never allow arbitrary MQTT topics."""
    kiosk = call.data["kiosk"].strip()
    command = call.data["command"]
    value = call.data["value"].strip()
    if not kiosk or "/" in kiosk or "+" in kiosk or "#" in kiosk:
        raise vol.Invalid("Invalid kiosk ID")
    if command in ("screen", "screensaver", "mute"):
        if value.upper() not in ("ON", "OFF"):
            raise vol.Invalid("Only ON or OFF allowed")
        payload = value.upper()
    elif command in ("brightness", "volume"):
        try:
            percent = int(value)
        except ValueError as error:
            minimum = 1 if command == "brightness" else 0
            raise vol.Invalid(f"Value must be an integer from {minimum} to 100") from error
        minimum = 1 if command == "brightness" else 0
        if not minimum <= percent <= 100:
            raise vol.Invalid("Percentage out of range")
        payload = str(percent)
    elif command == "reload_dashboard":
        if value.lower() not in ("reload", "on", "1"):
            raise vol.Invalid("Use reload as the value")
        command = "system"
        payload = "reload_dashboard"
    else:
        raise vol.Invalid("Unsupported device command")
    capability = {
        "screen": "display.power",
        "screensaver": "screensaver.activate",
        "brightness": "display.brightness",
        "volume": "audio.volume",
        "mute": "audio.mute",
        "system": "dashboard.reload",
    }[command]
    _require_capability(hass, kiosk, capability)
    if command == "screen" and payload == "OFF":
        readiness = _state(hass).get(kiosk, {}).get("display", {}).get("power_control_ready")
        if readiness is not None and readiness.lower() in ("false", "off", "0", "no"):
            raise vol.Invalid("Display power-off is unavailable until device-admin access is enabled")
    state = _state(hass).get(kiosk, {})
    manifest = state.get("capabilities")
    if manifest and manifest.get("compatible") and "command.acknowledged" in manifest["capabilities"]:
        request_id = uuid4().hex
        request_body = {
            "schema": 1,
            "request_id": request_id,
            "expires_at_ms": int(time.time() * 1000) + 60_000,
            "command": command,
            "value": payload,
        }
        pending = hass.data[DOMAIN].setdefault("pending_device_commands", {})
        now = time.monotonic()
        for old_id, request in list(pending.items()):
            if request["expires"] < now:
                pending.pop(old_id, None)
        pending[request_id] = {"kiosk": kiosk, "expires": now + 65}
        state = _ensure_kiosk(hass, kiosk)
        state["last_device_request"] = request_id
        state["last_device_request_at_ms"] = int(time.time() * 1000)
        try:
            await mqtt.async_publish(
                hass, _kiosk_topic(kiosk, "command/device/request"),
                json.dumps(request_body), qos=1, retain=False,
            )
        except Exception:
            pending.pop(request_id, None)
            raise
        return
    await mqtt.async_publish(
        hass, _kiosk_topic(kiosk, f"command/device/{command}") if command != "system"
        else _kiosk_topic(kiosk, "command/system"),
        payload, qos=1, retain=False,
    )


async def _send_settings_command(
        hass: HomeAssistant, kiosk: str, action: str, section: str = "",
        changes: dict[str, Any] | None = None) -> None:
    kiosk = kiosk.strip()
    if not _valid_segment(kiosk):
        raise vol.Invalid("Invalid kiosk ID")
    if action == "get":
        _require_any_capability(hass, kiosk, ("screensaver.settings", "camera.popup_settings"))
    else:
        capability = "screensaver.settings" if section == "screensaver" else "camera.popup_settings"
        _require_capability(hass, kiosk, capability)
    request_id = uuid4().hex
    payload: dict[str, Any] = {
        "schema": 1,
        "request_id": request_id,
        "expires_at_ms": int(time.time() * 1000) + 60_000,
        "action": action,
    }
    if action != "get":
        payload["section"] = section
    if action == "update":
        if not changes:
            raise vol.Invalid("At least one setting must be provided")
        payload["changes"] = changes

    pending = hass.data[DOMAIN].setdefault("pending_settings", {})
    now = time.monotonic()
    for old_id, request in list(pending.items()):
        if request["expires"] < now:
            pending.pop(old_id, None)
    pending[request_id] = {"kiosk": kiosk, "expires": now + 60}
    state = _ensure_kiosk(hass, kiosk)
    state["last_settings_request"] = request_id
    state["last_settings_request_at_ms"] = int(time.time() * 1000)
    try:
        await mqtt.async_publish(
            hass, _kiosk_topic(kiosk, "command/settings"),
            json.dumps(payload), qos=1, retain=False,
        )
    except Exception:
        pending.pop(request_id, None)
        raise


async def _service_notification(hass: HomeAssistant, call: ServiceCall) -> None:
    """Push an ephemeral, typed notification to one kiosk screensaver."""
    kiosk = call.data["kiosk"].strip()
    if not _valid_segment(kiosk):
        raise vol.Invalid("Invalid kiosk ID")
    _require_capability(hass, kiosk, "notification.display")

    action = call.data["action"]
    notice_id = call.data["notification_id"].strip()
    if notice_id and not _valid_segment(notice_id):
        raise vol.Invalid("Invalid notification ID")

    if action == "clear":
        payload = {"action": "clear", "id": notice_id}
    else:
        message = call.data["message"].strip()
        if not message:
            raise vol.Invalid("A notification must contain a message")
        duration = call.data["duration_seconds"]
        payload = {
            "action": "show",
            "id": notice_id or uuid4().hex,
            "level": call.data["level"],
            "title": call.data["title"],
            "message": message,
            "expires_at_ms": int(time.time() * 1000) + duration * 1000,
            "show_screensaver": call.data["show_screensaver"],
        }

    await mqtt.async_publish(
        hass,
        _kiosk_topic(kiosk, "command/notification"),
        json.dumps(payload, ensure_ascii=False),
        qos=1,
        retain=False,
    )


async def _service_popup(hass: HomeAssistant, call: ServiceCall) -> None:
    """Display constrained kiosk content; actions require an explicit HA automation."""
    kiosk = call.data["kiosk"].strip()
    kind = call.data["kind"]
    camera = call.data["camera"].strip()
    if not _valid_segment(kiosk) or not _valid_segment(camera):
        raise vol.Invalid("Invalid kiosk or camera ID")

    if kind == "camera":
        _require_capability(hass, kiosk, "camera.external")
        await mqtt.async_publish(
            hass, _kiosk_topic(kiosk, "command/camera"),
            json.dumps({"action": "show", "camera": camera}),
            qos=1, retain=False,
        )
        return

    _require_capability(
        hass, kiosk, "popup.confirmation" if kind == "confirmation" else "popup.message"
    )

    popup_id = uuid4().hex
    pending = hass.data[DOMAIN].setdefault("pending_popups", {})
    # Prune abandoned requests whenever a new popup is requested.
    now = time.monotonic()
    for old_id, request in list(pending.items()):
        if request["expires"] < now:
            del pending[old_id]
    pending[popup_id] = {
        "kiosk": kiosk,
        "popup_name": call.data["popup_name"],
        "expires": now + 120,
    }
    payload = {
        "popup_id": popup_id,
        "expires_at_ms": int(time.time() * 1000) + 120_000,
        "kind": kind,
        "title": call.data["title"],
        "message": call.data["message"],
        "confirm_label": call.data["confirm_label"],
        "cancel_label": call.data["cancel_label"],
    }
    try:
        await mqtt.async_publish(
            hass, _kiosk_topic(kiosk, "command/popup"),
            json.dumps(payload), qos=1, retain=False,
        )
    except Exception:
        pending.pop(popup_id, None)
        raise


@websocket_api.websocket_command({vol.Required("type"): "ha_gecko_kiosk/list"})
@websocket_api.require_admin
@callback
def websocket_list_kiosks(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all kiosks observed through MQTT."""
    connection.send_result(msg["id"], {"kiosks": list(_state(hass).values())})


async def _register_panel(hass: HomeAssistant) -> None:
    integration_dir = Path(__file__).parent
    frontend_dir = integration_dir / "frontend"
    panel_version = sha256((frontend_dir / "ha-gecko-kiosk-panel.js").read_bytes()).hexdigest()[:12]

    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(frontend_dir), cache_headers=False)]
    )

    await panel_custom.async_register_panel(
        hass=hass,
        frontend_url_path=PANEL_URL,
        sidebar_title="Gecko-kiosken",
        sidebar_icon="mdi:tablet",
        webcomponent_name="ha-gecko-kiosk-panel",
        module_url=f"{STATIC_URL}/ha-gecko-kiosk-panel.js?v={panel_version}",
        embed_iframe=False,
        require_admin=True,
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up HA Gecko Kiosk from YAML."""
    data = hass.data.setdefault(DOMAIN, {DATA_KIOSKS: {}, DATA_UNSUBS: []})
    if data.get("_initialized"):
        return True
    unsubs = data.setdefault(DATA_UNSUBS, [])

    unsubs.append(
        await mqtt.async_subscribe(
            hass,
            f"{TOPIC_PREFIX}/+/availability",
            lambda msg: _handle_availability(hass, msg),
            qos=1,
        )
    )
    unsubs.append(
        await mqtt.async_subscribe(
            hass,
            f"{TOPIC_PREFIX}/+/status/+",
            lambda msg: _handle_status(hass, msg),
            qos=1,
        )
    )
    unsubs.append(
        await mqtt.async_subscribe(
            hass,
            f"{TOPIC_PREFIX}/+/battery/+",
            lambda msg: _handle_battery(hass, msg),
            qos=1,
        )
    )
    for subsystem in ("display", "audio"):
        unsubs.append(
            await mqtt.async_subscribe(
                hass,
                f"{TOPIC_PREFIX}/+/{subsystem}/+",
                lambda msg: _handle_device_state(hass, msg),
                qos=1,
            )
        )
    unsubs.append(
        await mqtt.async_subscribe(
            hass,
            f"{TOPIC_PREFIX}/+/device/response",
            lambda msg: _handle_device_response(hass, msg),
            qos=1,
        )
    )
    for suffix in ("app/version", "mqtt/reconnect_count", "watchdog/status", "watchdog/restart_count"):
        unsubs.append(
            await mqtt.async_subscribe(
                hass,
                f"{TOPIC_PREFIX}/+/{suffix}",
                lambda msg: _handle_diagnostic_state(hass, msg),
                qos=1,
            )
        )

    unsubs.append(
        await mqtt.async_subscribe(
            hass,
            f"{TOPIC_PREFIX}/+/popup/response",
            lambda msg: _handle_popup_response(hass, msg),
            qos=1,
        )
    )

    unsubs.append(
        await mqtt.async_subscribe(
            hass, f"{TOPIC_PREFIX}/+/settings/state",
            lambda msg: _handle_settings_state(hass, msg), qos=1,
        )
    )
    unsubs.append(
        await mqtt.async_subscribe(
            hass, f"{TOPIC_PREFIX}/+/settings/response",
            lambda msg: _handle_settings_response(hass, msg), qos=1,
        )
    )

    async def handle_camera(call: ServiceCall) -> None:
        await _service_camera(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CAMERA,
        handle_camera,
        schema=CAMERA_SCHEMA,
    )

    async def handle_device(call: ServiceCall) -> None:
        await _service_device(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_DEVICE, handle_device, schema=DEVICE_SCHEMA
    )

    async def handle_popup(call: ServiceCall) -> None:
        await _service_popup(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_POPUP, handle_popup, schema=POPUP_SCHEMA
    )

    async def handle_notification(call: ServiceCall) -> None:
        await _service_notification(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_NOTIFICATION, handle_notification, schema=NOTIFICATION_SCHEMA
    )

    async def handle_set_screensaver(call: ServiceCall) -> None:
        await _send_settings_command(hass, call.data["kiosk"], "update", "screensaver",
                {k: v for k, v in call.data.items() if k != "kiosk"})

    async def handle_set_camera_popup(call: ServiceCall) -> None:
        await _send_settings_command(hass, call.data["kiosk"], "update", "camera_popup",
                {k: v for k, v in call.data.items() if k != "kiosk"})

    async def handle_get_settings(call: ServiceCall) -> None:
        await _send_settings_command(hass, call.data["kiosk"], "get")

    async def handle_reset_settings(call: ServiceCall) -> None:
        await _send_settings_command(hass, call.data["kiosk"], "reset", call.data["section"])

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCREENSAVER, handle_set_screensaver,
        schema=SET_SCREENSAVER_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_CAMERA_POPUP, handle_set_camera_popup,
        schema=SET_CAMERA_POPUP_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_SETTINGS, handle_get_settings,
        schema=GET_SETTINGS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_SETTINGS, handle_reset_settings,
        schema=RESET_SETTINGS_SCHEMA
    )

    @callback
    def cleanup(_event: Event) -> None:
        for unsub in list(unsubs):
            unsub()
        unsubs.clear()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, cleanup)

    websocket_api.async_register_command(hass, websocket_list_kiosks)
    await _register_panel(hass)
    data["_initialized"] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Support installation through Settings > Devices & services."""
    return await async_setup(hass, {})
