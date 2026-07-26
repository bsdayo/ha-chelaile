"""车来了 binary sensor 平台 - 检测公交车是否已到达。"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DIRECTION, CONF_LINE_ID, CONF_LINE_NAME, CONF_STATION_NAME, DOMAIN
from .coordinator import ChelaileDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为每个 config entry 创建已到达传感器。"""
    coordinator: ChelaileDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    line_name = entry.data.get(CONF_LINE_NAME, "")
    station_name = entry.data.get(CONF_STATION_NAME, "")
    
    # 为每辆车创建一个已到达传感器
    sensors = []
    for i in range(3):  # 最多检测 3 辆车
        sensors.append(ChelaileArrivedSensor(coordinator, entry, i))
    
    async_add_entities(sensors)


class ChelaileArrivedSensor(BinarySensorEntity):
    """检测某辆公交车是否已到达。"""

    _attr_device_class = BinarySensorDeviceClass.MOVING
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:bus-marker"

    def __init__(
        self,
        coordinator: ChelaileDataUpdateCoordinator,
        entry: ConfigEntry,
        vehicle_index: int,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._entry = entry
        self._vehicle_index = vehicle_index

        line_name = entry.data.get(CONF_LINE_NAME, "")
        station_name = entry.data.get(CONF_STATION_NAME, "")
        
        # 唯一 ID
        self._attr_unique_id = f"{entry.entry_id}_{entry.data[CONF_LINE_ID]}_arrived_{vehicle_index}"
        
        # 名称
        if vehicle_index == 0:
            self._attr_name = f"{line_name} {station_name} 第 1 辆车到站"
        else:
            self._attr_name = f"{line_name} {station_name} 第{vehicle_index + 1}辆车到站"
        
        # 设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.data[CONF_LINE_ID]}_{entry.entry_id}")},
            name=f"{line_name} {station_name}",
            manufacturer="车来了",
            model="公交线路",
            configuration_url="https://web.chelaile.net.cn",
        )

    @property
    def is_on(self) -> bool | None:
        """如果车辆已到达（travel_time <= 60 秒），返回 True。"""
        data = self._coordinator.data or {}
        
        if self._vehicle_index == 0:
            bus = data.get("next_bus")
        else:
            following = data.get("following_buses") or []
            actual_index = self._vehicle_index - 1
            if actual_index < len(following):
                bus = following[actual_index]
            else:
                return None
        
        if not bus:
            return None
        
        travel_time = bus.get("travel_time")
        if travel_time is None:
            return None
        
        try:
            # 如果行驶时间小于等于 60 秒（还有 1 分钟以内），认为已到达
            return int(travel_time) <= 60
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict:
        """详细状态属性。"""
        data = self._coordinator.data or {}
        
        if self._vehicle_index == 0:
            bus = data.get("next_bus")
        else:
            following = data.get("following_buses") or []
            actual_index = self._vehicle_index - 1
            if actual_index < len(following):
                bus = following[actual_index]
            else:
                bus = None
        
        attrs = {"vehicle_index": self._vehicle_index, "is_first_bus": self._vehicle_index == 0}
        
        if bus:
            attrs.update({
                "travel_time_seconds": bus.get("travel_time"),
                "stops_away": bus.get("stops_away"),
                "distance_m": bus.get("distance_to_wait"),
                "arrival_time": bus.get("arrival_time"),
            })
        
        return attrs

    @property
    def available(self) -> bool:
        """数据更新成功且有数据时可用。"""
        return bool(self._coordinator.last_update_success and self._coordinator.data)

    async def async_added_to_hass(self) -> None:
        """实体已添加到 hass。"""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )
