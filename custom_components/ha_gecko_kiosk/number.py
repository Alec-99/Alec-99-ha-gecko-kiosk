"""Validated brightness and audio numbers."""
import math
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError
from .entity import KioskEntity, numeric_value, setup_platform

async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(hass, entry, async_add_entities, "number", KioskNumber)

class KioskNumber(KioskEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, *args):
        super().__init__(*args)
        self._attr_native_min_value = self.spec.minimum
        self._attr_native_max_value = self.spec.maximum
        self._attr_native_unit_of_measurement = self.spec.unit

    @property
    def native_value(self): return numeric_value(self.kiosk, self.spec)

    async def async_set_native_value(self, value):
        if (not math.isfinite(value) or value != int(value)
                or not self.spec.minimum <= value <= self.spec.maximum):
            raise HomeAssistantError("Value must be a whole percentage in the supported range")
        await self.async_command(str(int(value)))
