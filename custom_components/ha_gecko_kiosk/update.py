"""APK updates brokered by HA from a configured private CI artifact source."""

from datetime import timedelta

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.exceptions import HomeAssistantError

from . import DOMAIN
from .entity import KioskEntity, setup_platform
from .ota import ACTIVE

SCAN_INTERVAL = timedelta(hours=6)


async def async_setup_entry(hass, entry, async_add_entities):
    await setup_platform(hass, entry, async_add_entities, "update", KioskUpdate)


class KioskUpdate(KioskEntity, UpdateEntity):
    _attr_should_poll = True
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    _attr_title = "HA Gecko Kiosk"

    @property
    def ota(self):
        return self.hass.data[DOMAIN]["ota_manager"]

    @property
    def installed_version(self):
        return self.kiosk.get("ota", {}).get("version_name") or self.kiosk.get(
            "diagnostics", {}
        ).get("app_version")

    @property
    def latest_version(self):
        if self.ota.uploaded:
            return self.ota.uploaded[0]["version_name"]
        return self.ota.candidate.version_name if self.ota.candidate else None

    def version_is_newer(self, latest_version, installed_version):
        if self.ota.uploaded:
            current = self.kiosk.get("ota", {}).get("version_code")
            if type(current) is int:
                return self.ota.uploaded[0]["version_code"] > current
        return super().version_is_newer(latest_version, installed_version)

    @property
    def in_progress(self):
        return self.kiosk.get("ota", {}).get("status") in ACTIVE

    @property
    def update_percentage(self):
        return self.kiosk.get("ota", {}).get("progress") if self.in_progress else None

    @property
    def release_summary(self):
        status = self.kiosk.get("ota", {}).get("status", "idle")
        if not self.ota.uploaded and not self.ota.configured:
            return "Upload een APK via Gecko-kiosken → App-updates."
        if not self.ota.uploaded and self.ota.error:
            return "APK-bron niet bereikbaar; controleer de integratieopties."
        return {
            "permission_required": "Sta op de tablet installatie door HA Gecko Kiosk toe en keer terug naar de app.",
            "awaiting_confirmation": "Bevestig de installatie op de tablet.",
            "error": "Update mislukt: "
            + self.kiosk.get("ota", {}).get("detail", "unknown"),
            "requested": "Update aangevraagd.",
            "downloading": "APK downloaden.",
            "verifying": "APK controleren.",
            "installing": "Android installeert de APK.",
            "installed": "Installatie voltooid.",
            "cancelled": "Installatie geannuleerd.",
        }.get(
            status,
            "Geüploade APK; Android controleert pakket, versie en ondertekening."
            if self.ota.uploaded
            else "Privé CI-build; Android controleert pakket, versie en ondertekening.",
        )

    @property
    def extra_state_attributes(self):
        return {"ota_status": self.kiosk.get("ota", {}).get("status", "idle"),
                "ota_detail": self.kiosk.get("ota", {}).get("detail", "")}

    async def async_update(self):
        await self.ota.check()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        task = self.hass.async_create_background_task(
            self._initial_check(), "Check private kiosk OTA source"
        )
        self.async_on_remove(task.cancel)

    async def _initial_check(self):
        try:
            await self.ota.check()
        except HomeAssistantError:
            pass
        self.async_write_ha_state()

    async def async_install(self, version, backup, **kwargs):
        if not self.available:
            raise HomeAssistantError("Kiosk is offline or OTA is unavailable")
        if version is not None or backup:
            raise HomeAssistantError("Specific versions and backups are not supported")
        await self.ota.install(self.kiosk_id)
