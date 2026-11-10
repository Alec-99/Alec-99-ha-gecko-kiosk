"""Capability-gated kiosk switches using the existing device service."""
from homeassistant.components.switch import SwitchEntity
from .entity import KioskEntity, raw_value, setup_platform

async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(hass, entry, async_add_entities, "switch", KioskSwitch)

class KioskSwitch(KioskEntity, SwitchEntity):
    @property
    def is_on(self):
        value = raw_value(self.kiosk, self.spec)
        if value is None: return None
        if value.lower() in ("on", "true", "1"): return True
        if value.lower() in ("off", "false", "0"): return False
        return None

    async def async_turn_on(self, **kwargs): await self.async_command("ON")
    async def async_turn_off(self, **kwargs): await self.async_command("OFF")
