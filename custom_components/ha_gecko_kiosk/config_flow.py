"""UI installation for the standalone Gecko kiosk management integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
import re
from homeassistant.core import callback
from homeassistant.helpers import selector

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OtaOptionsFlow()

    async def async_step_import(
        self, user_input: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Give YAML installations the same device/entity config-entry owner."""
        return await self.async_step_user({})


class OtaOptionsFlow(config_entries.OptionsFlow):
    """Credentials stay in HA config-entry storage, outside kiosk read models."""

    async def async_step_init(self, user_input=None):
        errors = {}
        options = self.config_entry.options
        if user_input is not None:
            values = {key: str(value).strip() for key, value in user_input.items()}
            if not values.get("ota_token"):
                values["ota_token"] = options.get("ota_token", "")
            repository = values.get("ota_repository", "")
            if repository and (
                not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                or not values.get("ota_branch")
                or not values.get("ota_token")
            ):
                errors["base"] = "invalid_ota_source"
            elif not re.fullmatch(
                r"[A-Za-z0-9_.-]+\.ya?ml", values.get("ota_workflow", "")
            ):
                errors["base"] = "invalid_ota_source"
            elif (
                len(values.get("ota_branch", "")) > 256
                or len(values.get("ota_token", "")) > 512
            ):
                errors["base"] = "invalid_ota_source"
            else:
                return self.async_create_entry(title="", data=values)
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "ota_repository", default=options.get("ota_repository", "")
                    ): str,
                    vol.Optional(
                        "ota_branch", default=options.get("ota_branch", "")
                    ): str,
                    vol.Optional(
                        "ota_workflow",
                        default=options.get("ota_workflow", "build-ha-gecko-kiosk.yml"),
                    ): str,
                    vol.Optional("ota_token", default=""): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
        )
