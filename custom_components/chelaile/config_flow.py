"""车来了集成配置流程.

分步(每步职责单一,避免单步承担多职责导致前端卡顿):
1. user:      选城市(从 /wwd/ncitylist 拉取下拉)
2. line:      输入线路号 -> 搜索得到各方向
3. direction: 选方向(若该线路号仅一个方向则自动跳过)
4. stop:      选目标站点 -> 创建 entry
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .api import ChelaileApiClient
from .const import (
    CONF_CITY_ID,
    CONF_CITY_NAME,
    CONF_DIRECTION,
    CONF_END_SN,
    CONF_LAT,
    CONF_LINE_ID,
    CONF_LINE_NAME,
    CONF_LINE_NO,
    CONF_LNG,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_START_SN,
    CONF_TARGET_ORDER,
    DEFAULT_CITY_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STEP_DIRECTION,
    STEP_LINE,
    STEP_STOP,
    STEP_USER,
)
from .exceptions import ChelaileAuthError, ChelaileError, ChelaileNotFoundError

_LOGGER = logging.getLogger(__name__)


async def _get_api(hass: HomeAssistant) -> ChelaileApiClient:
    """构造一个临时 API 客户端(config_flow 期间短生命周期,独立 session)。"""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    
    session = async_get_clientsession(hass)
    return ChelaileApiClient(session)


async def _validate_get_cities(hass: HomeAssistant) -> list[dict[str, Any]]:
    """获取城市列表，返回 [{cityId, cityName, ...}]。失败抛异常。"""
    api = await _get_api(hass)
    try:
        return await api.async_get_cities()
    finally:
        pass  # HA 自动管理 session


async def _validate_search_lines(
    hass: HomeAssistant, city_id: str, keyword: str
) -> list[dict[str, Any]]:
    api = await _get_api(hass)
    try:
        return await api.async_search_lines(city_id, keyword)
    finally:
        pass  # HA 自动管理 session


async def _validate_get_line_stations(
    hass: HomeAssistant, city_id: str, line_id: str
) -> list[dict[str, Any]]:
    api = await _get_api(hass)
    try:
        return await api.async_get_line_stations(city_id, line_id)
    finally:
        pass  # HA 自动管理 session


def _city_options(cities: list[dict[str, Any]]) -> dict[str, str]:
    """构造城市下拉选项 {cityId: "cityName"}。热门在前。"""
    sorted_cities = sorted(
        cities,
        key=lambda c: (not c.get("isHot"), c.get("pinyin") or c.get("cityName") or ""),
    )
    return {str(c.get("cityId", "")): str(c.get("cityName", "")) for c in sorted_cities}


class ChelaileConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """车来了集成配置流程。"""

    VERSION = 1

    def __init__(self) -> None:
        """初始化流程状态。"""
        self._cities: list[dict[str, Any]] = []
        self._lines: list[dict[str, Any]] = []
        self._stations: list[dict[str, Any]] = []
        self._selected_city_id: str = ""
        self._selected_city_name: str = ""
        self._line_no: str = ""
        self._selected_line: dict[str, Any] = {}
        self._entry_data: dict[str, Any] = {}

    # ---------- 第 1 步：选城市 ----------
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选城市。"""
        errors: dict[str, str] = {}

        if not self._cities:
            try:
                self._cities = await _validate_get_cities(self.hass)
            except ChelaileError as err:
                _LOGGER.error("获取城市列表失败: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("获取城市列表异常: %s", err)
                errors["base"] = "unknown"

        if user_input is not None and not errors:
            city_id = user_input.get(CONF_CITY_ID)
            if not city_id:
                errors[CONF_CITY_ID] = "select_city"
            else:
                self._selected_city_id = city_id
                self._selected_city_name = next(
                    (
                        str(c.get("cityName", ""))
                        for c in self._cities
                        if str(c.get("cityId")) == city_id
                    ),
                    "",
                )
                return await self.async_step_line()

        city_options = _city_options(self._cities) if self._cities else {}
        default_city = DEFAULT_CITY_ID if DEFAULT_CITY_ID in city_options else next(
            iter(city_options), ""
        )

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CITY_ID, default=default_city): vol.In(city_options),
                }
            ),
            errors=errors,
            description_placeholders={"city_count": str(len(city_options))},
        )

    # ---------- 第2步:输入线路号 ----------

    async def async_step_line(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """输入线路号,搜索后跳到方向选择。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            line_no = (user_input.get(CONF_LINE_NO) or "").strip()
            if not line_no:
                errors[CONF_LINE_NO] = "line_no_required"
            else:
                try:
                    self._lines = await _validate_search_lines(
                        self.hass, self._selected_city_id, line_no
                    )
                    self._line_no = line_no
                    # 单方向直接选中并进入站点步;多方向进入方向选择步
                    if len(self._lines) == 1:
                        return await self._go_to_stop(self._lines[0])
                    return await self.async_step_direction()
                except ChelaileNotFoundError:
                    errors[CONF_LINE_NO] = "line_not_found"
                except ChelaileAuthError:
                    errors["base"] = "auth_failed"
                    # 需要用户重新配置
                except ChelaileError as err:
                    _LOGGER.error("搜索线路失败: %s", err)
                    errors["base"] = "cannot_connect"
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("搜索线路异常: %s", err)
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id=STEP_LINE,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LINE_NO, default=self._line_no): str,
                }
            ),
            errors=errors,
            description_placeholders={"city_name": self._selected_city_name},
        )

    # ---------- 第3步:选方向 ----------

    async def async_step_direction(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选择线路方向(上/下行)。"""
        errors: dict[str, str] = {}

        if not self._lines:
            # 没有搜索结果,回到上一步
            return await self.async_step_line()

        if user_input is not None:
            line_id = user_input.get(CONF_LINE_ID)
            selected = next(
                (l for l in self._lines if l.get("lineId") == line_id), None
            )
            if selected:
                return await self._go_to_stop(selected)
            errors[CONF_LINE_ID] = "select_direction"

        direction_options = {
            l["lineId"]: l.get("caption", l.get("name", ""))
            for l in self._lines
        }

        return self.async_show_form(
            step_id=STEP_DIRECTION,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LINE_ID): vol.In(direction_options),
                }
            ),
            errors=errors,
            description_placeholders={"line_no": self._line_no},
        )

    # ---------- 第4步:选站点 ----------

    async def _go_to_stop(self, line: dict[str, Any]) -> ConfigFlowResult:
        """记录选中线路,拉取站点,进入站点选择步。"""
        self._selected_line = line
        try:
            self._stations = await _validate_get_line_stations(
                self.hass, self._selected_city_id, line["lineId"]
            )
        except ChelaileNotFoundError:
            return self.async_show_form(
                step_id=STEP_DIRECTION,
                errors={"base": "no_stations"},
            )
        except ChelaileError as err:
            _LOGGER.error("获取站点失败: %s", err)
            return self.async_show_form(
                step_id=STEP_DIRECTION,
                errors={"base": "cannot_connect"},
            )
        return await self.async_step_stop()

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """选目标站点,然后创建 entry。"""
        errors: dict[str, str] = {}

        if not self._stations:
            return await self.async_step_direction()

        if user_input is not None:
            station_key = user_input.get(CONF_STATION_ID)
            selected = None
            for s in self._stations:
                key = f"{s['order']}:{s['station_id']}"
                if key == station_key:
                    selected = s
                    break
            if selected:
                line = self._selected_line
                return self.async_create_entry(
                    title=f"{line.get('name', '')} {selected['name']}",
                    data={
                        CONF_CITY_ID: self._selected_city_id,
                        CONF_CITY_NAME: self._selected_city_name,
                        CONF_LINE_NO: self._line_no,
                        CONF_LINE_ID: line.get("lineId"),
                        CONF_LINE_NAME: line.get("name"),
                        CONF_DIRECTION: line.get("direction"),
                        CONF_START_SN: line.get("startSn"),
                        CONF_END_SN: line.get("endSn"),
                        CONF_TARGET_ORDER: selected["order"],
                        CONF_STATION_ID: selected["station_id"],
                        CONF_STATION_NAME: selected["name"],
                        CONF_LAT: selected.get("lat"),
                        CONF_LNG: selected.get("lng"),
                    },
                )
            errors[CONF_STATION_ID] = "select_station"

        station_options = {
            f"{s['order']}:{s['station_id']}": f"{s['order']}. {s['name']}"
            for s in self._stations
        }

        return self.async_show_form(
            step_id=STEP_STOP,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): vol.In(station_options),
                }
            ),
            errors=errors,
            description_placeholders={
                "line_name": self._selected_line.get("name", ""),
                "direction": str(self._selected_line.get("direction", "")),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "ChelaileOptionsFlow":
        """返回 options flow。"""
        return ChelaileOptionsFlow()

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """重配流程：遇到版本无效时让用户重新选择城市/线路。"""
        if user_input is not None:
            pass
        # 直接跳到城市选择步
        return await self.async_step_user(user_input)


class ChelaileOptionsFlow(config_entries.OptionsFlow):
    """选项流：可调轮询间隔。"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """管理选项。"""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=int(current)): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=600)
                    ),
                }
            ),
        )
