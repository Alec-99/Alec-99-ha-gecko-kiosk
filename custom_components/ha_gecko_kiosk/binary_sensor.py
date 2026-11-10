"""Kiosk connectivity and binary state."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from .entity import KioskEntity, raw_value, setup_platform

async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(hass, entry, async_add_entities, "binary_sensor", KioskBinarySensor)

class KioskBinarySensor(KioskEntity, BinarySensorEntity):
    @property
    def is_on(self):
        value = raw_value(self.kiosk, self.spec)
        if value is None: return None
        value = value.lower()
        if value in ("online", "on", "true", "1"): return True
        if value in ("offline", "off", "false", "0"): return False
        return None
