"""车来了到站时间 sensor 平台 - 重构版.

采用主从式设计，提供清晰直观的公交实时信息:

主要传感器:
- ETA Sensor: 显示最近一辆公交车的预计到达时间 (ISO 时间字符串)
- Capacity Sensor: 显示拥挤度
- Bus Count Sensor: 监控可见车辆数量

实体命名规范:
- bus_chelaile_{line}_{station}_eta
- bus_chelaile_{line}_{station}_capacity  
- bus_chelaile_{line}_{station}_bus_count
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CAPACITY_MAP, CONF_CITY_NAME, CONF_DIRECTION, CONF_LINE_ID, CONF_LINE_NAME, CONF_STATION_NAME, DOMAIN
from .coordinator import ChelaileDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为每个配置创建主线传感器。"""
    coordinator: ChelaileDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    sensors = [
        ChelaileETASensor(coordinator, entry),
        ChelaileCapacitySensor(coordinator, entry),
        ChelaileBusCountSensor(coordinator, entry),
    ]
    
    async_add_entities(sensors)


# ========== 工具函数 ==========

def _arrival_iso(ms_ts: int | None) -> str | None:
    """毫秒时间戳 -> ISO 字符串."""
    if not ms_ts:
        return None
    try:
        return datetime.fromtimestamp(int(ms_ts) / 1000, tz=timezone.utc).astimezone().isoformat()
    except (ValueError, OSError):
        return None


def _get_eta_minutes(travel_time: Any) -> int:
    """计算到站分钟数 (向上取整)。"""
    try:
        return max(1, math.ceil(int(travel_time) / 60))
    except (TypeError, ValueError):
        return 0


def _get_full_display_info(bus_data: dict | None) -> str | None:
    """获取完整显示信息字符串."""
    if not bus_data:
        return None
    
    parts = []
    travel_time = bus_data.get("travel_time")
    
    if travel_time is not None:
        eta = _get_eta_minutes(travel_time)
        parts.append(f"ETA {eta} min")
    
    stops_away = bus_data.get("stops_away")
    if stops_away is not None:
        parts.append(f"{stops_away} stops")
    
    distance = bus_data.get("distance_to_wait")
    if distance is not None:
        parts.append(f"~{int(distance)}m" if distance >= 100 else "<100m")
    
    capacity = bus_data.get("capacity")
    if capacity is not None:
        parts.append(CAPACITY_MAP.get(capacity, "?"))
    
    return " • ".join(parts)


def _get_distance_description(distance_m: float | None) -> str:
    """根据距离返回友好的描述."""
    if distance_m is None:
        return "Unknown"
    if distance_m < 50:
        return "Arriving shortly"
    elif distance_m < 200:
        return "Very close"
    elif distance_m < 500:
        return "Close"
    return f"{int(distance_m)}m"


# ========== 主传感器 ==========

class ChelaileETASensor(CoordinatorEntity, SensorEntity):
    """公交 ETA 主要传感器 - 显示预计到达时间。"""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bus-alert"

    def __init__(self, coordinator: ChelaileDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        
        line_name = entry.data.get(CONF_LINE_NAME, "")
        station_name = entry.data.get(CONF_STATION_NAME, "")
        
        self._attr_unique_id = f"{entry.entry_id}_eta"
        self._attr_name = f"{line_name} @ {station_name} ETA"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data[CONF_LINE_ID]}_{entry.entry_id}")},
            name=f"{line_name} @ {station_name}",
            manufacturer="车来了",
            model=line_name,
            configuration_url="https://web.chelaile.net.cn",
        )

    @property
    def native_value(self) -> datetime | None:
        """返回预计到达时间 (ISO 格式)。"""
        data = self.coordinator.data or {}
        bus = data.get("next_bus")
        return _arrival_iso(bus.get("arrival_time")) if bus else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """详细属性。"""
        data = self.coordinator.data or {}
        bus = data.get("next_bus")
        entry_data = self._entry.data
        
        attrs = {
            "line_name": entry_data.get(CONF_LINE_NAME),
            "direction": entry_data.get(CONF_DIRECTION),
            "station_name": entry_data.get(CONF_STATION_NAME),
            "city_name": entry_data.get(CONF_CITY_NAME),
            "last_updated": data.get("last_updated"),
        }
        
        if bus:
            travel_time = bus.get("travel_time")
            distance = bus.get("distance_to_wait")
            
            attrs.update({
                "eta_display": _get_full_display_info(bus),
                "eta_minutes_raw": _get_eta_minutes(travel_time),
                "arrival_time_iso": _arrival_iso(bus.get("arrival_time")),
                "stops_away": bus.get("stops_away"),
                "distance_meters": distance,
                "distance_description": _get_distance_description(distance),
                "capacity": CAPACITY_MAP.get(bus.get("capacity"), "Unknown"),
                "license_plate": bus.get("licence"),
                "speed_kmh": bus.get("speed"),
                "order": bus.get("order"),
                "is_arriving": int(travel_time or 999) <= 60 if travel_time is not None else None,
            })
        
        return attrs

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success and self.coordinator.data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))


# ========== 拥挤度传感器 ==========

class ChelaileCapacitySensor(CoordinatorEntity, SensorEntity):
    """公交拥挤度传感器。"""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:female"

    def __init__(self, coordinator: ChelaileDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        
        line_name = entry.data.get(CONF_LINE_NAME, "")
        station_name = entry.data.get(CONF_STATION_NAME, "")
        
        self._attr_unique_id = f"{entry.entry_id}_capacity"
        self._attr_name = f"{line_name} @ {station_name} Capacity"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data[CONF_LINE_ID]}_{entry.entry_id}")},
            name=f"{line_name} @ {station_name}",
            manufacturer="车来了",
            model=line_name,
            configuration_url="https://web.chelaile.net.cn",
        )

    @property
    def native_value(self) -> str | None:
        """返回拥挤度状态。"""
        data = self.coordinator.data or {}
        bus = data.get("next_bus")
        return CAPACITY_MAP.get(bus.get("capacity"), "Unknown") if bus else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        bus = data.get("next_bus")
        
        attrs = {"last_updated": data.get("last_updated")}
        if bus:
            attrs.update({
                "capacity_numeric": bus.get("capacity"),
                "license_plate": bus.get("licence"),
            })
        return attrs

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success and self.coordinator.data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))


# ========== 公交车计数传感器 ==========

class ChelaileBusCountSensor(CoordinatorEntity, SensorEntity):
    """监控范围内的公交车数量。"""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.POWER
    _attr_icon = "mdi:bus-side"

    def __init__(self, coordinator: ChelaileDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        
        line_name = entry.data.get(CONF_LINE_NAME, "")
        station_name = entry.data.get(CONF_STATION_NAME, "")
        
        self._attr_unique_id = f"{entry.entry_id}_bus_count"
        self._attr_name = f"{line_name} @ {station_name} Buses"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data[CONF_LINE_ID]}_{entry.entry_id}")},
            name=f"{line_name} @ {station_name}",
            manufacturer="车来了",
            model=line_name,
            configuration_url="https://web.chelaile.net.cn",
        )

    @property
    def native_value(self) -> int | None:
        """返回可见公交车数量。"""
        data = self.coordinator.data or {}
        buses = data.get("buses", [])
        return len(buses) if buses else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        buses = data.get("buses", [])
        
        attrs = {
            "last_updated": data.get("last_updated"),
            "max_buses_displayed": 3,
        }
        
        if buses:
            attrs["all_buses"] = [
                {
                    "eta_min": _get_eta_minutes(b.get("travel_time")),
                    "stops_away": b.get("stops_away"),
                    "distance_m": b.get("distance_to_wait"),
                }
                for b in buses[:3]
            ]
        
        return attrs

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success and self.coordinator.data)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
