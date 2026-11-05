"""最近三辆公交车的剩余到站时间及文本汇总。"""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import Bus
from .coordinator import ChelaileConfigEntry
from .entity import ChelaileEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChelaileConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """添加最近三辆车的到站时间传感器及文本汇总。"""
    async_add_entities(
        [
            *(ChelaileETASensor(entry, index) for index in range(3)),
            ChelaileETASummarySensor(entry),
        ]
    )


class ChelaileETASensor(ChelaileEntity, SensorEntity):
    """指定顺位的公交车距离到站的分钟数。"""

    _attr_translation_key = "eta"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:bus-clock"

    def __init__(self, entry: ChelaileConfigEntry, vehicle_index: int) -> None:
        """使用固定顺位标识实体，车辆离开后由后车补位。"""
        super().__init__(entry)
        self._vehicle_index = vehicle_index
        self._attr_unique_id = f"{entry.unique_id}_eta_{vehicle_index + 1}"
        self._attr_translation_placeholders = {"position": str(vehicle_index + 1)}

    @property
    def bus(self) -> Bus | None:
        """返回对应顺位的车辆，车辆数量不足时返回 None。"""
        buses = self.coordinator.data or []
        return buses[self._vehicle_index] if self._vehicle_index < len(buses) else None

    # 按 HA 实体接口实时读取数据，不缓存状态。
    @property
    def native_value(self) -> int | None:  # ty: ignore[invalid-property-type-override]
        """返回剩余分钟数，无法预计到站时间时返回未知。"""
        bus = self.bus
        return bus["eta_minutes"] if bus else None

    # 车辆属性同样需要实时读取，不能沿用基类的缓存属性。
    @property
    def extra_state_attributes(  # ty: ignore[invalid-property-type-override]
        self,
    ) -> dict[str, Any]:
        """提供当前车辆的详细信息及本次查询的车辆数量。"""
        buses = self.coordinator.data or []
        return {"bus_count": len(buses), **(self.bus or {})}


class ChelaileETASummarySensor(ChelaileEntity, SensorEntity):
    """按固定顺位拼接最近三辆车的剩余分钟数。"""

    _attr_translation_key = "eta_summary"
    _attr_icon = "mdi:bus-clock"

    def __init__(self, entry: ChelaileConfigEntry) -> None:
        super().__init__(entry)
        self._attr_unique_id = f"{entry.unique_id}_eta_summary"

    @property
    def native_value(self) -> str | None:  # ty: ignore[invalid-property-type-override]
        """以间隔点拼接时间，保留未知位置；全部未知时返回 None。"""
        buses = self.coordinator.data or []
        values = [
            buses[index]["eta_minutes"] if index < len(buses) else None
            for index in range(3)
        ]
        if all(value is None for value in values):
            return None
        return " · ".join("—" if value is None else f"{value}m" for value in values)
