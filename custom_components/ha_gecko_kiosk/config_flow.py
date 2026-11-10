"""UI installation for the standalone Gecko kiosk management integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

DOMAIN = "ha_gecko_kiosk"


class HaGeckoKioskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Install a single controller for all locally discovered MQTT kiosks."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm installation; the existing HA MQTT integration supplies connectivity."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="HA Gecko Kiosk", data={})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> config_entries.ConfigFlowResult:
        """Give YAML installations the same device/entity config-entry owner."""
        return await self.async_step_user({})
