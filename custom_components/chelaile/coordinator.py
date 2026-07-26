"""车来了数据更新协调器."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ChelaileApiClient
from .const import (
    CONF_CITY_ID,
    CONF_LINE_ID,
    CONF_STATION_ID,
    CONF_TARGET_ORDER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .exceptions import ChelaileAuthError, ChelaileError

_LOGGER = logging.getLogger(__name__)


class ChelaileDataUpdateCoordinator(DataUpdateCoordinator):
    """轮询车来了实时到站信息。"""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ChelaileApiClient,
        entry: ConfigEntry,
    ) -> None:
        self.api = api
        self.entry = entry
        self.line_id = entry.data[CONF_LINE_ID]
        self.city_id = entry.data[CONF_CITY_ID]
        self.station_id = entry.data[CONF_STATION_ID]
        self.target_order = entry.data[CONF_TARGET_ORDER]
        self.lat = str(entry.data.get("lat") or "")
        self.lng = str(entry.data.get("lng") or "")

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL)
        if scan_interval:
            update_interval = timedelta(seconds=int(scan_interval))
        else:
            update_interval = DEFAULT_SCAN_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """从上游拉取实时到站数据并归一化。"""
        try:
            buses = await self.api.async_get_realtime(
                city_id=self.city_id,
                line_id=self.line_id,
                target_order=self.target_order,
                station_id=self.station_id,
                lat=self.lat,
                lng=self.lng,
            )
        except ChelaileAuthError as err:
            # 签名/版本失效，需用户重新配置或集成升级
            raise UpdateFailed(str(err)) from err
        except ChelaileError as err:
            raise UpdateFailed(str(err)) from err

        now = datetime.now(timezone.utc)
        result: dict[str, Any] = {
            "buses": buses,
            "next_bus": buses[0] if buses else None,
            "following_buses": buses[1:] if len(buses) > 1 else [],
            "last_updated": now.isoformat(),
        }
        return result
