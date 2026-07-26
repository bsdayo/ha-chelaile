"""车来了到站时间 sensor 平台.

支持创建多个传感器，每个显示一辆车的到站信息：
- 主传感器：最近一辆车到站分钟数（适合卡片展示）
- 附加传感器：第 2、3 辆车的详细信息（适合列表对比）
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime, Platform
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

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为每个 config entry 创建多个传感器（每辆车一个）。"""
    coordinator: ChelaileDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # 创建所有车辆的传感器（最多 3 辆）
    sensors = []
    line_name = entry.data.get(CONF_LINE_NAME, "")
    station_name = entry.data.get(CONF_STATION_NAME, "")
    
    # 主传感器：显示最近一辆车
    sensors.append(ChelaileBusSensor(coordinator, entry, vehicle_index=0))
    
    # 附加传感器：第 2、3 辆车
    for i in range(1, 3):
        sensors.append(ChelaileBusSensor(coordinator, entry, vehicle_index=i))
    
    async_add_entities(sensors)


def _arrival_iso(ms_ts: int | None) -> str | None:
    """毫秒时间戳 -> ISO 字符串 (本地时区展示)。"""
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


def _calculate_eta_minutes(travel_time: Any) -> int | None:
    """计算到站分钟数（向上取整）。"""
    if travel_time is None:
        return None
    try:
        return max(0, math.ceil(int(travel_time) / 60))
    except (TypeError, ValueError):
        return None


def _get_bus_data(coordinator_data: dict | None, vehicle_index: int) -> dict | None:
    """根据车辆索引获取对应的公交车数据。"""
    if not coordinator_data:
        return None
    
    if vehicle_index == 0:
        # 第一辆车：next_bus
        return coordinator_data.get("next_bus")
    else:
        # 第 2、3 辆车：following_buses
        following = coordinator_data.get("following_buses") or []
        actual_index = vehicle_index - 1
        if actual_index < len(following):
            return following[actual_index]
        return None


class ChelaileBusSensor(CoordinatorEntity, SensorEntity):
    """公交车到站信息传感器 - 每辆车一个实例。"""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ChelaileDataUpdateCoordinator,
        entry: ConfigEntry,
        vehicle_index: int = 0,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._vehicle_index = vehicle_index

        line_name = entry.data.get(CONF_LINE_NAME, "")
        station_name = entry.data.get(CONF_STATION_NAME, "")
        
        # 唯一 ID 包含车辆索引以区分不同车辆
        unique_id_suffix = f"bus_{vehicle_index}"
        self._attr_unique_id = f"{entry.entry_id}_{entry.data[CONF_LINE_ID]}_{unique_id_suffix}"
        
        # 名称根据车辆索引显示不同文本
        if vehicle_index == 0:
            self._attr_name = f"{line_name} {station_name} 第 1 辆车"
        else:
            self._attr_name = f"{line_name} {station_name} 第{vehicle_index + 1}辆车"
        
        # 设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data[CONF_LINE_ID]}_{entry.entry_id}")},
            name=f"{line_name} {station_name}",
            manufacturer="车来了",
            model="公交线路",
            configuration_url=f"https://web.chelaile.net.cn",
        )
        
        # 图标：根据状态动态设置
        self._attr_icon = "mdi:bus"

    @property
    def native_value(self) -> int | str | None:
        """获取当前车辆的到站时间。
        
        对于第 1 辆车：返回分钟数（整数）
        对于第 2、3 辆车：返回详细字符串
        """
        data = self.coordinator.data or {}
        bus = _get_bus_data(data, self._vehicle_index)
        
        if not bus:
            return None
        
        travel_time = bus.get("travel_time")
        if travel_time is None:
            return None
        
        eta_minutes = _calculate_eta_minutes(travel_time)
        
        # 第 1 辆车：简单显示分钟数
        if self._vehicle_index == 0:
            return eta_minutes
        
        # 第 2、3 辆车：显示详细字符串
        stops_away = bus.get("stops_away")
        distance = bus.get("distance_to_wait")
        
        parts = []
        if eta_minutes is not None and eta_minutes > 0:
            parts.append(f"约{eta_minutes}分钟")
        if stops_away is not None:
            parts.append(f"还有{stops_away}站")
        if distance is not None:
            parts.append(f"约{int(distance)}米")
        
        return ", ".join(parts) if parts else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """详细到站信息。"""
        data = self.coordinator.data or {}
        entry_data = self._entry.data
        bus = _get_bus_data(data, self._vehicle_index)
        
        attrs: dict[str, Any] = {
            "vehicle_index": self._vehicle_index,
            "is_first_bus": self._vehicle_index == 0,
            "line_name": entry_data.get(CONF_LINE_NAME),
            "direction": entry_data.get(CONF_DIRECTION),
            "station_name": entry_data.get(CONF_STATION_NAME),
            "city_name": entry_data.get(CONF_CITY_NAME),
            "last_updated": data.get("last_updated"),
        }
        
        if bus:
            travel_time = bus.get("travel_time")
            attrs.update(
                {
                    "eta_minutes": _calculate_eta_minutes(travel_time),
                    "arrival_time": _arrival_iso(bus.get("arrival_time")),
                    "stops_away": bus.get("stops_away"),
                    "distance_m": bus.get("distance_to_wait"),
                    "capacity": _capacity_label(bus.get("capacity")),
                    "licence": bus.get("licence"),
                    "speed_kmh": bus.get("speed"),
                    "order": bus.get("order"),
                }
            )
        
        return attrs

    @property
    def available(self) -> bool:
        """数据更新成功且有数据时可用。"""
        return bool(self.coordinator.last_update_success and self.coordinator.data)
    
    async def async_added_to_hass(self) -> None:
        """实体已添加到 hass。"""
        await super().async_added_to_hass()
        # 监听协调器数据变化
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )
