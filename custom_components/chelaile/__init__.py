"""车来了实时公交到站信息集成。"""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChelaileApiClient
from .coordinator import ChelaileConfigEntry, ChelaileCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ChelaileConfigEntry) -> bool:
    """初始化指定线路和站点。"""
    coordinator = ChelaileCoordinator(
        hass, entry, ChelaileApiClient(async_get_clientsession(hass))
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChelaileConfigEntry) -> bool:
    """卸载实体及其协调器监听。"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
