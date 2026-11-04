"""公交实体共用的标识和设备信息。"""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Bus
from .const import BASE_URL, DOMAIN
from .coordinator import ChelaileConfigEntry, ChelaileCoordinator


class ChelaileEntity(CoordinatorEntity[ChelaileCoordinator]):
    """属于指定线路和站点的实体。"""

    _attr_has_entity_name = True

    def __init__(self, entry: ChelaileConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        # 配置流程创建条目前必定设置唯一标识。
        assert entry.unique_id is not None
        self._attr_unique_id = f"{entry.unique_id}_{self._attr_translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="车来了",
            model=entry.data["direction"],
            configuration_url=BASE_URL,
        )

    @property
    def next_bus(self) -> Bus | None:
        """返回距离目标站点最近的驶来车辆。"""
        return self.coordinator.data[0] if self.coordinator.data else None
