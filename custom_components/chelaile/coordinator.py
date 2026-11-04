"""指定线路和站点的共享轮询。"""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Bus, ChelaileApiClient, ChelaileError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ChelaileCoordinator(DataUpdateCoordinator[list[Bus]]):
    """为所有实体统一获取最近的公交车信息。"""

    config_entry: ChelaileConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ChelaileConfigEntry, api: ChelaileApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            always_update=False,
        )
        self.api = api

    async def _async_update_data(self) -> list[Bus]:
        """获取到站信息，由 Home Assistant 处理失败后的重试。"""
        data = self.config_entry.data
        try:
            return await self.api.async_get_realtime(
                city_id=data["city_id"],
                line_id=data["line_id"],
                station_id=data["station_id"],
                target_order=data["target_order"],
                lat=data["lat"],
                lng=data["lng"],
            )
        except ChelaileError as err:
            raise UpdateFailed(str(err)) from err


type ChelaileConfigEntry = ConfigEntry[ChelaileCoordinator]
