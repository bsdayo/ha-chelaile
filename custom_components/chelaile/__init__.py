"""车来了(chelaile)实时公交 Home Assistant 集成.

数据源: https://web.chelaile.net.cn 微信小程序 API
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant

from .api import ChelaileApiClient
from .const import CONF_CITY_ID, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import ChelaileDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置 config entry:创建 API 客户端 + 协调器,转发到平台。"""
    hass.data.setdefault(DOMAIN, {})

    # 用 HA 管理的 aiohttp session
    session = aiohttp.ClientSession()
    api = ChelaileApiClient(
        session=session,
        city_id=entry.data[CONF_CITY_ID],
    )

    coordinator = ChelaileDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # options 更新时重新加载
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载 config entry。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        session: aiohttp.ClientSession | None = data.get("session")
        if session and not session.closed:
            await session.close()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """options 变更后重载 entry。"""
    await hass.config_entries.async_reload(entry.entry_id)
