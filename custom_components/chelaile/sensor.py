"""车来了到站时间 sensor 平台."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CAPACITY_MAP,
    CONF_CITY_NAME,
    CONF_DIRECTION,
    CONF_LINE_ID,
    CONF_LINE_NAME,
    CONF_STATION_NAME,
    DOMAIN,
)
from .coordinator import ChelaileDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为每个 config entry 创建到站时间 sensor。"""
    coordinator: ChelaileDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ChelaileArrivalSensor(coordinator, entry)])


def _arrival_iso(ms_ts: int | None) -> str | None:
    """毫秒时间戳 -> ISO 字符串(本地时区展示)。"""
    if not ms_ts:
        return None
    try:
        return datetime.fromtimestamp(int(ms_ts) / 1000, tz=timezone.utc).astimezone().isoformat()
    except (ValueError, OSError):
        return None


def _capacity_label(cap: int | None) -> str:
    if cap is None:
        return "未知"
    return CAPACITY_MAP.get(cap, "未知")


class ChelaileArrivalSensor(CoordinatorEntity, SensorEntity):
    """显示最近一辆公交车到站分钟数。"""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:bus"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChelaileDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry

        line_name = entry.data.get(CONF_LINE_NAME, "")
        station_name = entry.data.get(CONF_STATION_NAME, "")
        self._attr_unique_id = f"{entry.entry_id}_{entry.data[CONF_LINE_ID]}_{entry.data.get('station_id', '')}"
        self._attr_name = f"{line_name} {station_name} 到站"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data[CONF_LINE_ID]}_{entry.entry_id}")},
            name=f"{line_name} {station_name}",
            manufacturer="车来了",
            model="公交线路",
        )

    @property
    def native_value(self) -> int | None:
        """最近一辆车到站分钟数(向上取整)。无车返回 None。"""
        data = self.coordinator.data or {}
        next_bus = data.get("next_bus")
        if not next_bus:
            return None
        travel_time = next_bus.get("travel_time")
        if travel_time is None:
            return None
        try:
            return max(0, math.ceil(int(travel_time) / 60))
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """详细到站信息。"""
        data = self.coordinator.data or {}
        entry_data = self._entry.data
        next_bus = data.get("next_bus")
        following = data.get("following_buses") or []

        attrs: dict[str, Any] = {
            "line_name": entry_data.get(CONF_LINE_NAME),
            "direction": entry_data.get(CONF_DIRECTION),
            "station_name": entry_data.get(CONF_STATION_NAME),
            "city_name": entry_data.get(CONF_CITY_NAME),
            "last_updated": data.get("last_updated"),
        }

        if next_bus:
            attrs.update(
                {
                    "next_bus_eta_min": self.native_value,
                    "next_bus_arrival_time": _arrival_iso(next_bus.get("arrival_time")),
                    "next_bus_stops_away": next_bus.get("stops_away"),
                    "next_bus_distance_m": next_bus.get("distance_to_wait"),
                    "next_bus_capacity": _capacity_label(next_bus.get("capacity")),
                    "next_bus_licence": next_bus.get("licence"),
                }
            )
        else:
            attrs["next_bus_eta_min"] = None

        attrs["following_buses"] = [
            {
                "eta_min": max(0, math.ceil(int(b.get("travel_time") or 0) / 60)) if b.get("travel_time") is not None else None,
                "arrival_time": _arrival_iso(b.get("arrival_time")),
                "stops_away": b.get("stops_away"),
                "distance_m": b.get("distance_to_wait"),
                "capacity": _capacity_label(b.get("capacity")),
                "licence": b.get("licence"),
            }
            for b in following
        ]
        return attrs

    @property
    def available(self) -> bool:
        """数据更新成功且有数据时可用。"""
        return bool(self.coordinator.last_update_success and self.coordinator.data)
