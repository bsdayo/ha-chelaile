"""车来了 (chelaile) 实时公交 Home Assistant 集成.

数据源：https://web.chelaile.net.cn 微信小程序 API

支持功能：
- 显示多辆公交车的到站时间
- 检测公交车是否已到达（binary_sensor）
- 提供手动刷新服务
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_component import EntityComponent

from .api import ChelaileApiClient
from .const import CONF_CITY_ID, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import ChelaileDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# 服务常量
SERVICE_REFRESH = "refresh"

# 服务 schema
REFRESH_SCHEMA = {}  # 不需要参数


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置 config entry:创建 API 客户端 + 协调器，转发到平台。"""
    from homeassistant.config_entries import ConfigEntry
    
    hass.data.setdefault(DOMAIN, {})
    session = async_get_clientsession(hass)
    api = ChelaileApiClient(
        session=session,
        city_id=entry.data[CONF_CITY_ID],
    )

    coordinator = ChelaileDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    # 注册刷新服务
    component = hass.data.get("component")  # EntityComponent
    if not isinstance(component, EntityComponent):
        from homeassistant.core import HomeAssistant
        component = hass.components.entity  # 尝试其他路径
    
    # 注册服务
    async def refresh_handler(service_call):
        """处理刷新请求。"""
        entry_id = service_call.data.get("entry_id")
        if entry_id:
            coordinators = [
                coord
                for data in hass.data.get(DOMAIN, {}).values()
                if (coord := data.get("coordinator"))
            ]
        else:
            coordinators = []
            for data in hass.data.get(DOMAIN, {}).values():
                if (coord := data.get("coordinator")):
                    coordinators.append(coord)
        
        if coordinators:
            _LOGGER.info("收到 %d 个协调器的刷新请求", len(coordinators))
            for coord in coordinators:
                await coord.async_request_refresh()
    
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, refresh_handler, schema=REFRESH_SCHEMA
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # options 更新时重新加载
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载 config entry。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """options 变更后重载 entry。"""
    await hass.config_entries.async_reload(entry.entry_id)
