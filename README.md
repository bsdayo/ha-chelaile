# 车来了实时公交 - Home Assistant 集成

<p align="center">
  <img src="icon.png" width="128" alt="车来了实时公交集成图标" />
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

基于[车来了](https://web.chelaile.net.cn)微信小程序接口的 Home Assistant 自定义集成,实时监控指定公交线路在指定站点的到站时间。

## 功能

- 🚌 实时到站时间(分钟数)作为 sensor 状态
- 📍 显示最近一辆车的:到站分钟、到达时间、距离(米)、还有几站、拥挤度、车牌
- 🚏 同时展示后续 2 辆车的到站信息
- ⏱️ 可配置轮询间隔(默认 30 秒)
- 🗺️ 配置流程:选城市 → 输线路号 → 选方向 → 选站点(全程下拉,无需手动抓 ID)

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

如需调整轮询间隔,在集成卡片上点「配置」即可(10–600 秒)。

## 实体说明

每个 (线路, 站点) 配置生成一个 sensor:

| 属性 | 说明 |
|------|------|
| 状态 | 最近一辆车到站分钟数(向上取整,无车时为 `unknown`) |
| `line_name` | 线路名 |
| `direction` | 方向 |
| `station_name` | 站点名 |
| `city_name` | 城市 |
| `next_bus_eta_min` | 最近车到站分钟 |
| `next_bus_arrival_time` | 最近车预计到达时间(ISO) |
| `next_bus_stops_away` | 最近车还有几站 |
| `next_bus_distance_m` | 最近车距站点距离(米) |
| `next_bus_capacity` | 最近车拥挤度(空/中/挤) |
| `next_bus_licence` | 最近车牌号 |
| `following_buses` | 后续车辆列表(ETA/距离/站数/拥挤度/车牌) |
| `last_updated` | 最后更新时间 |

## 自动化示例

```yaml
# 公交快到站时通知(还有 3 分钟)
automation:
  - alias: 公交快到站提醒
    trigger:
      - platform: numeric_state
        entity_id: sensor.bus_7_市一中_到站
        below: 3
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "7路公交还有 {{ trigger.to_state.state }} 分钟到达市一中!"
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
