"""车来了集成配置流程.

分步:
1. user: 选城市(从 /wwd/ncitylist 拉取下拉)
2. line: 输入线路号 -> 搜索得到各方向
3. stop: 选定方向 -> 拉取该方向站点列表 -> 选目标站点
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
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
    STEP_LINE,
    STEP_STOP,
    STEP_USER,
)
from .exceptions import ChelaileAuthError, ChelaileError, ChelaileNotFoundError

_LOGGER = logging.getLogger(__name__)


async def _get_api(hass: HomeAssistant) -> ChelaileApiClient:
    """构造一个临时 API 客户端(共享 hass 的 aiohttp session)。"""
    session = aiohttp.ClientSession()
    # 用 hass.helpers 不可靠,直接用独立 session;config_flow 期间短生命周期可接受
    return ChelaileApiClient(session)


async def _validate_get_cities(hass: HomeAssistant) -> list[dict[str, Any]]:
    """获取城市列表,返回 [{cityId, cityName, ...}]。失败抛异常。"""
    api = await _get_api(hass)
    try:
        return await api.async_get_cities()
    finally:
        await api._session.close()


async def _validate_search_lines(
    hass: HomeAssistant, city_id: str, keyword: str
) -> list[dict[str, Any]]:
    api = await _get_api(hass)
    try:
        return await api.async_search_lines(city_id, keyword)
    finally:
        await api._session.close()


async def _validate_get_line_stations(
    hass: HomeAssistant, city_id: str, line_id: str
) -> list[dict[str, Any]]:
    api = await _get_api(hass)
    try:
        return await api.async_get_line_stations(city_id, line_id)
    finally:
        await api._session.close()


def _city_options(cities: list[dict[str, Any]]) -> dict[str, str]:
    """构造城市下拉选项 {cityId: "cityName (pinyin)"}。热门在前。"""
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第1步:选城市。"""
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

        if user_input is not None:
            city_id = user_input.get(CONF_CITY_ID)
            if not city_id:
                errors[CONF_CITY_ID] = "select_city"
            elif not errors:
                self._selected_city_id = city_id
                self._selected_city_name = next(
                    (str(c.get("cityName", "")) for c in self._cities if str(c.get("cityId")) == city_id),
                    "",
                )
                return await self.async_step_line()

        city_options = _city_options(self._cities) if self._cities else {}
        # 默认选中茂名
        default_city = DEFAULT_CITY_ID if DEFAULT_CITY_ID in city_options else (next(iter(city_options), ""))

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

    async def async_step_line(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第2步:输入线路号,搜索后选方向。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            line_no = (user_input.get(CONF_LINE_NO) or "").strip()
            if not line_no:
                errors[CONF_LINE_NO] = "line_no_required"
            elif not errors:
                try:
                    self._lines = await _validate_search_lines(
                        self.hass, self._selected_city_id, line_no
                    )
                    self._line_no = line_no
                    if len(self._lines) == 1:
                        # 只有一个方向,直接进下一步
                        return await self._select_line_and_go_to_stop(self._lines[0])
                    return await self.async_step_line()
                except ChelaileNotFoundError:
                    errors[CONF_LINE_NO] = "line_not_found"
                except ChelaileAuthError:
                    errors["base"] = "auth_failed"
                except ChelaileError as err:
                    _LOGGER.error("搜索线路失败: %s", err)
                    errors["base"] = "cannot_connect"
                except Exception as err:  # noqa: BLE001
                    _LOGGER.error("搜索线路异常: %s", err)
                    errors["base"] = "unknown"

        # 展示搜索结果作为方向选择(如果有多个方向)
        if self._lines and len(self._lines) > 1 and user_input and CONF_LINE_ID not in user_input:
            # 首次搜索成功多方向,展示方向选择
            pass

        # 若已有搜索结果且用户选了方向
        if user_input and user_input.get(CONF_LINE_ID) and self._lines:
            line_id = user_input[CONF_LINE_ID]
            selected = next((l for l in self._lines if l.get("lineId") == line_id), None)
            if selected:
                return await self._select_line_and_go_to_stop(selected)

        # 同时输入线路号 + (可选)已搜索方向
        line_options = {l["lineId"]: l.get("caption", l.get("name", "")) for l in self._lines}

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_LINE_NO, default=self._line_no): str,
        }
        if line_options:
            schema_dict[vol.Required(CONF_LINE_ID)] = vol.In(line_options)

        return self.async_show_form(
            step_id=STEP_LINE,
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"city_name": self._selected_city_name},
        )

    async def _select_line_and_go_to_stop(self, line: dict[str, Any]) -> FlowResult:
        """记录选中线路,拉取站点,进入站点选择步。"""
        self._selected_line = line
        errors: dict[str, str] = {}
        try:
            self._stations = await _validate_get_line_stations(
                self.hass, self._selected_city_id, line["lineId"]
            )
        except ChelaileNotFoundError:
            errors["base"] = "no_stations"
            return self.async_show_form(step_id=STEP_LINE, errors=errors)
        except ChelaileError as err:
            _LOGGER.error("获取站点失败: %s", err)
            errors["base"] = "cannot_connect"
            return self.async_show_form(step_id=STEP_LINE, errors=errors)

        return await self.async_step_stop()

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """第3步:选目标站点,然后创建 entry。"""
        errors: dict[str, str] = {}

        if not self._stations:
            return await self.async_step_line()

        if user_input is not None:
            station_key = user_input.get(CONF_STATION_ID)
            # station_key 形如 "order:stationId" 或纯 station_id,我们用 order 定位
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

        # 站点下拉: order:stationId -> "order. 站名"
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
        return ChelaileOptionsFlow(config_entry)


class ChelaileOptionsFlow(config_entries.OptionsFlow):
    """选项流:可调轮询间隔。"""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
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
