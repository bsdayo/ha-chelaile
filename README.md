# 车来了实时公交 - Home Assistant 集成

<p align="center">
  <img src="icon.png" width="128" alt="车来了实时公交集成图标" />
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

基于[车来了](https://web.chelaile.net.cn)微信小程序接口的 Home Assistant 自定义集成,实时监控指定公交线路在指定站点的到站时间。

## 功能

✨ **核心功能**
- 🚌 **多车实时显示**: 同时监控最近 3 辆公交车的到站信息
- ⏱️ **智能到站时间**: 第 1 辆车显示分钟数，第 2-3 辆车显示详细字符串
- 🎯 **已到达检测**: binary_sensor 实时检测公交是否已到达 (≤1 分钟)
- ⚙️ **可配置轮询**: 支持 10-900 秒间隔，推荐 30-300 秒
- 🔄 **手动刷新服务**: 支持调用服务立即刷新数据
- 🗺️ **友好配置**: 选城市 → 输线路号 → 选方向 → 选站点 (全程下拉选择)

📊 **数据展示**
| 实体类型 | 说明 |
|----------|------|
| `sensor.*_第 1 辆车` | 最近一辆车到站分钟数 (适合 Lovelace 卡片) |
| `sensor.*_第 2/3 辆车` | 后续车辆的详细字符串 (如 "约 5 分钟，还有 3 站，约 450 米") |
| `binary_sensor.*_已到达` | 当车辆 ≤1 分钟时触发 True |

💡 **使用提示**
- 主面板建议只显示「第 1 辆车」传感器状态
- 可以创建自动化：当 `binary_sensor` 为 ON 时发送通知
- 支持在设置中调整轮询频率

## 安装

### 通过 HACS

1. HACS → 集成 → 右上角 ⋮ → 自定义仓库
2. 添加本仓库地址,类别选 `集成`
3. 搜索「车来了实时公交」并下载
4. 重启 Home Assistant

### 手动安装

将 `custom_components/chelaile/` 整个目录复制到你的 HA 配置目录的 `custom_components/` 下,然后重启 HA。

## 配置

1. 设置 → 设备与服务 → 添加集成 → 搜索「车来了」
2. 选择城市(支持约 480 个城市,默认定位茂名)
3. 输入线路号(如 `7`、`368`)
4. 选择方向(上行/下行,显示为首末站)
5. 选择要监控的站点
6. 完成

如需调整轮询间隔，在集成卡片上点「配置」即可 (10–900 秒)。

### 刷新服务

通过以下服务手动刷新数据:
```yaml
# 刷新所有集成
service: chelaile.refresh

# 或按 entry_id 刷新特定线路 (需要知道 entry_id)
# service: chelaile.refresh
# data:
#   entry_id: xxxxxx
```

## 实体说明

每个 (线路，站点) 配置生成 **6 个实体**:

### Sensors (传感器)

| 实体名称 | 状态类型 | 说明 |
|----------|----------|------|
| `sensor.线路 站点 第 1 辆车` | number | 最近一辆车到站分钟数 |
| `sensor.线路 站点 第 2 辆车` | string | "约 5 分钟，还有 3 站" |
| `sensor.线路 站点 第 3 辆车` | string | "约 8 分钟，还有 5 站" |

### Binary Sensors (二元传感器)

| 实体名称 | 状态 | 说明 |
|----------|------|------|
| `binary_sensor.线路 站点 第 1 辆车到站` | on/off | travel_time ≤ 60 秒时为 on |
| `binary_sensor.线路 站点 第 2 辆车到站` | on/off | 同上 |
| `binary_sensor.线路 站点 第 3 辆车到站` | on/off | 同上 |

### Attributes (属性)

**Sensor 通用属性**:
```yaml
vehicle_index: 0              # 车辆索引 (0,1,2)
is_first_bus: true            # 是否第一辆车
line_name: "7 路"
direction: "上行"
station_name: "市一中"
city_name: "茂名"
last_updated: "2026-07-26T..."
et a_minutes: 5               # 到站分钟数
arrival_time: "2026-07-26T..."
stops_away: 3                 # 还有几站
distance_m: 450               # 距离 (米)
capacity: "空"                # 拥挤度
licence: "粤 X·12345"         # 车牌
speed_kmh: 25                 # 速度 (km/h)
order: 15                     # 当前站序
```

**Binary Sensor 属性**:
```yaml
travel_time_seconds: 45       # 剩余行驶时间 (秒)
stops_away: 0                 # 还有几站
distance_m: 50                # 距离 (米)
arrival_time: "..."           # 预计到达时间
```

## 自动化示例

### 1. 公交快到站通知

```yaml
automation:
  - alias: 公交快到了提醒
    trigger:
      - platform: numeric_state
        entity_id: sensor.bus_7_市一中_第 1 辆车
        below: 3
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "7 路公交还有 {{ trigger.to_state.state }} 分钟到达市一中!"
```

### 2. 已到达推送 (更及时)

```yaml
automation:
  - alias: 公交已到达
    trigger:
      - platform: state
        entity_id: binary_sensor.bus_7_市一中_第 1 辆车到站
        to: 'on'
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "🚌 7 路公交已到达市一中站！"
```

### 3. 综合信息卡片 (Lovelace)

```yaml
type: custom:glance-card
title: 7 路公交
entities:
  - entity: sensor.bus_7_市一中_第 1 辆车
    name: 第 1 辆车
  - entity: sensor.bus_7_市一中_第 2 辆车
    name: 第 2 辆车
  - entity: binary_sensor.bus_7_市一中_第 1 辆车到站
    icon: 'mdi:bus'
    state_color: true
    states:
      - 'on':
          icon: 'mdi:bus-alert'
          color: green
```

### 4. 定时自动刷新

```yaml
automation:
  - alias: 每分钟自动刷新公交数据
    trigger:
      platform: timepattern
      minutes: '/1'
    action:
      - service: chelaile.refresh
```

## 技术实现

- **API**: `https://web.chelaile.net.cn` 微信小程序变体
- **签名**: MD5(`"k"="v"&...` + `qwihrnbtmj`)
- **解密**: AES-256-ECB(PKCS7)
- **轮询**: aiohttp 异步,默认 30s

## 致谢

本集成的接口逆向基于以下开源项目:

- [chelaile-api-collect](https://github.com/afterglowsdev/chelaile-api-collect) - H5 API 文档与 CLI
- [chelaile-API](https://github.com/SuperL-2233/chelaile-API) - Python 实现(本集成主要参考)
- [chelaile-mcp](https://github.com/PeanutSplash/chelaile-mcp) - 微信小程序 TypeScript 实现

## 免责声明

- 本集成仅供个人学习使用,数据来自车来了公开接口。
- 「车来了」是武汉元光科技有限公司的商标,本集成与其无任何关联。
- 接口签名/加密机制可能随官方更新失效,届时需同步更新本集成。
- 请勿高频轮询,默认 30 秒间隔已足够。
