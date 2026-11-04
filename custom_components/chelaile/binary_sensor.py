"""检测最近一辆公交车是否将在一分钟内到站。"""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChelaileConfigEntry
from .entity import ChelaileEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChelaileConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """添加即将到站传感器。"""
    async_add_entities([ChelaileArrivingSensor(entry)])


class ChelaileArrivingSensor(ChelaileEntity, BinarySensorEntity):
    """表示公交车是否将在 60 秒内到站。"""

    _attr_translation_key = "arriving"
    _attr_icon = "mdi:bus-marker"

    # 按 HA 实体接口实时读取数据，不缓存状态。
    @property
    def is_on(self) -> bool | None:  # ty: ignore[invalid-property-type-override]
        """区分当前无车与车辆到站时间未知。"""
        bus = self.next_bus
        if bus is None:
            return False
        seconds = bus["travel_time_seconds"]
        return seconds <= 60 if seconds is not None else None
