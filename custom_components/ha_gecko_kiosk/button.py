"""Explicit dashboard reload, without reboot/restart controls."""
from homeassistant.components.button import ButtonEntity
from .entity import KioskEntity, setup_platform

async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(hass, entry, async_add_entities, "button", KioskButton)

class KioskButton(KioskEntity, ButtonEntity):
    _attr_icon = "mdi:refresh"
    async def async_press(self): await self.async_command("reload")
