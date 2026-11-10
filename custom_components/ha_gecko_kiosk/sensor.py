"""Allowlisted kiosk sensors; no network addresses or stream URLs."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from .entity import KioskEntity, raw_value, numeric_value, setup_platform

async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(hass, entry, async_add_entities, "sensor", KioskSensor)

class KioskSensor(KioskEntity, SensorEntity):
    def __init__(self, *args):
        super().__init__(*args)
        self._attr_native_unit_of_measurement = self.spec.unit
        if self.spec.minimum is not None: self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        if self.spec.minimum is not None: return numeric_value(self.kiosk, self.spec)
        value = raw_value(self.kiosk, self.spec)
        return value if value is not None and len(value) <= 128 else None
