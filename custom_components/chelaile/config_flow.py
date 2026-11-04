"""车来了集成的配置流程与选项流程。"""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ChelaileApiClient, ChelaileError, ChelaileNotFoundError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL


class ChelaileConfigFlow(ConfigFlow, domain=DOMAIN):
    """选择城市、线路、方向和站点。"""

    VERSION = 2

    def __init__(self) -> None:
        self._cities: dict[str, str] = {}
        self._lines: dict[str, dict[str, Any]] = {}
        self._line: dict[str, Any] = {}
        self._stations: list[dict[str, Any]] = []
        self._data: dict[str, Any] = {}

    @property
    def _api(self) -> ChelaileApiClient:
        return ChelaileApiClient(async_get_clientsession(self.hass))

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选择城市，或重试加载城市列表。"""
        errors: dict[str, str] = {}
        if not self._cities:
            try:
                cities = await self._api.async_get_cities()
                self._cities = {
                    str(city["cityId"]): city["cityName"]
                    for city in sorted(
                        cities,
                        key=lambda city: city.get("pinyin") or city["cityName"],
                    )
                }
            except ChelaileNotFoundError:
                errors["base"] = "no_cities"
            except ChelaileError:
                errors["base"] = "cannot_connect"

        if user_input and self._cities:
            city_id = user_input["city_id"]
            self._data = {"city_id": city_id, "city_name": self._cities[city_id]}
            return await self.async_step_line()

        schema = {}
        if self._cities:
            schema[probatio.Required("city_id")] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": city_id, "label": name}
                        for city_id, name in self._cities.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        return self.async_show_form(
            step_id="user", data_schema=probatio.Schema(schema), errors=errors
        )

    async def async_step_line(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """搜索公交线路。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            keyword = user_input["line_no"].strip()
            if not keyword:
                errors["line_no"] = "line_no_required"
            else:
                try:
                    lines = await self._api.async_search_lines(
                        self._data["city_id"], keyword
                    )
                except ChelaileNotFoundError:
                    errors["line_no"] = "line_not_found"
                except ChelaileError:
                    errors["base"] = "cannot_connect"
                else:
                    self._lines = {str(line["lineId"]): line for line in lines}
                    if len(self._lines) == 1:
                        self._line = next(iter(self._lines.values()))
                        return await self.async_step_stop()
                    return await self.async_step_direction()

        return self.async_show_form(
            step_id="line",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema({probatio.Required("line_no"): str}), user_input
            ),
            errors=errors,
            description_placeholders={"city_name": self._data["city_name"]},
        )

    async def async_step_direction(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选择线路方向。"""
        if user_input is not None:
            self._line = self._lines[user_input["line_id"]]
            self._stations = []
            return await self.async_step_stop()

        return self.async_show_form(
            step_id="direction",
            data_schema=probatio.Schema(
                {
                    probatio.Required("line_id"): probatio.In(
                        {
                            line_id: line["caption"]
                            for line_id, line in self._lines.items()
                        }
                    )
                }
            ),
        )

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选择站点，或重试加载已选线路的站点。"""
        errors: dict[str, str] = {}
        if not self._stations:
            try:
                self._stations = await self._api.async_get_line_stations(
                    self._data["city_id"], str(self._line["lineId"])
                )
            except ChelaileNotFoundError:
                errors["base"] = "no_stations"
            except ChelaileError:
                errors["base"] = "cannot_connect"

        stations = {
            f"{station['order']}:{station['station_id']}": station
            for station in self._stations
        }
        if user_input and stations:
            station = stations[user_input["station_id"]]
            data = {
                **self._data,
                "line_id": str(self._line["lineId"]),
                "line_name": self._line["name"],
                "direction": (
                    f"{self._line.get('startSn', '')} → {self._line.get('endSn', '')}"
                ),
                "station_id": str(station["station_id"]),
                "station_name": station["name"],
                "target_order": station["order"],
                "lat": "" if station["lat"] is None else str(station["lat"]),
                "lng": "" if station["lng"] is None else str(station["lng"]),
            }
            await self.async_set_unique_id(
                ":".join(
                    str(data[key])
                    for key in ("city_id", "line_id", "station_id", "target_order")
                )
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{data['line_name']} · {data['station_name']}", data=data
            )

        schema = {}
        if stations:
            schema[probatio.Required("station_id")] = probatio.In(
                {
                    key: f"{station['order']}. {station['name']}"
                    for key, station in stations.items()
                }
            )
        return self.async_show_form(
            step_id="stop",
            data_schema=probatio.Schema(schema),
            errors=errors,
            description_placeholders={"line_name": self._line["name"]},
            last_step=bool(stations),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ChelaileOptionsFlow:
        """创建选项流程。"""
        return ChelaileOptionsFlow()


class ChelaileOptionsFlow(OptionsFlowWithReload):
    """配置轮询间隔。"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): probatio.All(
                        probatio.Coerce(int),
                        probatio.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
