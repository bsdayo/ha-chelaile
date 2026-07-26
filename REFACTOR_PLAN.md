# Home Assistant Chelaile 集成架构重构方案

## 🎯 设计目标

1. **提高用户体验**: 清晰直观的实体命名和状态显示
2. **优化资源利用**: 减少不必要的 API 调用和数据冗余
3. **增强可视化**: 支持可视化的距离进度条
4. **简化配置**: 提供更便捷的新增和管理方式
5. **兼容性保障**: 保持 HA Core 2026.7.1+ 兼容

---

## 🏗️ 架构改进

### 1. 实体系统设计

**当前问题**: 为每辆车创建独立 sensor，导致实体过多且信息分散

**改进方案**: 采用"主从式"设计
```
✅ 主线 sensor (主要实体)
   - state: "ETA 5 min • 3 stops • ~450m"
   - attributes: {所有详细信息}

✅ 二元传感器 (到达检测)
   - state: on/off (≤1min)
   
✅ 辅助 sensor (可选启用)
   - bus_count: 监控到几辆车
   - capacity: 拥挤度变化
```

### 2. 设备组织

**当前**: 按配置 entry 分组设备
**改进**: 按公交线路 + 站点分组
```yaml
Device: 7 路公交 -> 市一中站
  ├─ Sensor: ETA (主)
  ├─ Binary Sensor: 已到达
  ├─ Sensor: 拥挤度
  └─ Sensor: 车辆数量
```

### 3. 数据更新策略

**当前**: 固定间隔轮询（60 秒）
**改进**: 混合策略
```python
- 默认: 90 秒轮询
- 手动: 即时刷新服务
- 条件: 距离 ≤ 200 米时自动缩短至 30 秒
```

---

## 📋 具体实现清单

### Phase 1: 核心重构 ✅
- [x] 简化实体系统（主线 sensor + binary sensor）
- [x] 统一时间显示格式（可读性字符串）
- [x] 优化设备注册信息
- [x] 添加 configuration_url

### Phase 2: 增强功能
- [ ] 添加距离进度条属性（percentage_complete）
- [ ] 智能刷新触发（距离越近越频繁）
- [ ] 缓存策略（失败时使用最后成功数据）

### Phase 3: 用户体验
- [ ] 优化配置流程（简化为 3 步）
- [ ] 提供快速添加服务（无需完整配置流）
- [ ] 批量导入 JSON 格式线路

### Phase 4: Lovelace 集成
- [ ] 提供专用卡片配置示例
- [ ] 添加自定义 UI 组件支持
- [ ] 地图集成接口（GeoLocation）

---

## 🔧 代码结构优化

### 文件重组建议

```
custom_components/chelaile/
├── __init__.py              # 主入口（精简）
├── config_flow.py           # 配置流程（保持不变）
├── const.py                 # 常量定义（完善）
├── coordinator.py           # 数据协调器（优化刷新策略）
├── sensor.py                # 主线传感器（重构）
├── binary_sensor.py         # 到达检测（保留）
├── services.yaml            # 服务定义（新增）
└── translations/
    ├── zh-Hans.json
    └── en.json
```

### 关键改动点

#### 1. Sensor Naming Convention
```python
# Before: sensor.chelaile_7_market_第 1 辆车
# After:  sensor.bus_chelaile_7_market_eta
```

#### 2. State Representation
```python
# Before: 5 (number) or "约 5 分钟，还有 3 站" (string)
# After:  "ETA 5 min (3 stops)"  # Always string for readability
```

#### 3. Device Info Structure
```python
DeviceInfo(
    identifiers={(DOMAIN, f"{line_id}_{station_id}")},
    name=f"{line_name} @ {station_name}",
    manufacturer="车来了",
    model=line_name,
    configuration_url="https://web.chelaile.net.cn/bus/...",
)
```

---

## 📊 对比表

| 特性 | 之前 | 之后 |
|------|------|------|
| 实体数量 | 6 个/配置 | 4 个/配置 (更精简) |
| 时间显示 | 数字 / 字符串混用 | 统一易读字符串 |
| 可视化 | ❌ 无 | ✅ 支持距离百分比 |
| 刷新频率 | 60 秒固定 | 90 秒 + 智能调整 |
| 错误处理 | ❌ 简单抛出 | ✅ 缓存失效数据 |
| 自动化支持 | ⚠️ 基础 | ✅ 丰富的自动化示例 |
| Lovelace 友好 | ⚠️ 一般 | ✅ 优化的卡片配置 |

---

## 🚀 预期效果

1. **更易理解的实体名称** - 一眼看出是什么
2. **更直观的显示** - 时间和距离一目了然
3. **更好的性能** - 减少 30% API 调用
4. **更强的可扩展性** - 易于添加新功能
5. **完整的文档** - 新手也能快速上手

