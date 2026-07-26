"""车来了(chelaile) API 客户端.

移植自 chelaile-API/bus_service.py,改为 async + aiohttp 风格,
用于 Home Assistant 集成。

技术要点:
- 签名: md5('"k"="v"&"k"="v"...' + "qwihrnbtmj"),参数顺序敏感
- 解密: AES-256-ECB,PKCS7,key=FF32AE65FBFD19414EAAFF6291A54B42
- 必需 headers: 微信小程序 UA + Referer
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

import aiohttp
from Crypto.Cipher import AES

from .const import (
    AES_KEY,
    API_BASE,
    CITY_LIST_URL,
    DEFAULT_HEADERS,
    DEFAULT_PARAMS,
    EP_BUS_DETAIL,
    EP_LINE_DETAIL,
    EP_SEARCH_LINES,
    EP_STOP_DETAIL,
    SIGN_SALT,
    STATUS_DEPRECATED,
    STATUS_OK,
)
from .exceptions import (
    ChelaileApiError,
    ChelaileAuthError,
    ChelaileError,
    ChelaileNotFoundError,
)

_LOGGER = logging.getLogger(__name__)


def crypto_sign(params: dict[str, str]) -> str:
    """计算 cryptoSign: '"k"="v"&...' 拼接后追加 salt,再 md5。

    参数顺序敏感,必须保留 dict 插入顺序。
    """
    sign_str = "&".join(f'"{k}"="{v}"' for k, v in params.items()) + SIGN_SALT
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def extract_json(raw: str) -> dict[str, Any]:
    """从可能带前导垃圾的响应中提取首个完整 JSON 对象(大括号配平)。"""
    start = raw.find("{")
    if start < 0:
        raise ChelaileError(f"upstream response is not JSON: {raw[:100]!r}")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])
    raise ChelaileError("upstream response JSON is truncated")


def decrypt_result(ciphertext: str) -> str:
    """AES-256-ECB 解密 base64 密文,去除 PKCS7 填充,返回 UTF-8 字符串。"""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    plain = cipher.decrypt(base64.b64decode(ciphertext))
    pad = plain[-1]
    # PKCS7 填充值即末尾字节数,1~16
    if pad < 1 or pad > 16:
        # 兜底:可能不是标准填充,直接尝试解码
        return plain.rstrip(b"\x00").decode("utf-8", errors="ignore")
    return plain[:-pad].decode("utf-8")


class ChelaileApiClient:
    """车来了 API 异步客户端。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        city_id: str = "",
    ) -> None:
        self._session = session
        self.city_id = city_id

    # ---------- 底层请求 ----------

    async def _request(
        self,
        endpoint: str,
        extra: dict[str, str] | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """发起签名+加密 GET 请求,返回解密后的 data dict。

        Args:
            endpoint: 相对 API_BASE 的端点(如 "query!nSearch.action")
            extra: 业务参数(会合并到 DEFAULT_PARAMS 之后再签名)
            url: 完整 URL(用于城市列表等非 /api/bus/ 端点)
        """
        # 合并:DEFAULT_PARAMS 先,业务参数后(顺序敏感)
        params: dict[str, str] = dict(DEFAULT_PARAMS)
        if self.city_id:
            params["cityId"] = self.city_id
            params["localCityId"] = self.city_id
        if extra:
            params.update(extra)

        params["cryptoSign"] = crypto_sign(params)

        target = url or (API_BASE + endpoint)
        _LOGGER.debug("GET %s params=%s", target, {k: v for k, v in params.items() if k != "cryptoSign"})

        try:
            async with self._session.get(
                target,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise ChelaileError(f"request failed: {err}") from err

        envelope = extract_json(text)
        jsonr = envelope.get("jsonr", {})
        status = jsonr.get("status")

        if status == STATUS_DEPRECATED:
            raise ChelaileAuthError(
                status,
                jsonr.get("errmsg", "该版本已不提供服务,需升级客户端指纹"),
            )
        if status not in STATUS_OK and status is not None:
            raise ChelaileApiError(status, jsonr.get("errmsg", ""))

        data = jsonr.get("data") or {}
        if isinstance(data, dict) and data.get("encryptResult"):
            decrypted = decrypt_result(data["encryptResult"])
            _LOGGER.debug("decrypted: %s", decrypted[:300])
            return json.loads(decrypted)
        return data

    # ---------- 高层方法 ----------

    async def async_get_cities(self) -> list[dict[str, Any]]:
        """获取城市列表(明文端点,响应结构为 {"data":{"cityList":[...]}})。

        该端点不走标准 jsonr 信封,也不加密,需单独处理。
        返回 [{cityId, cityName, pinyin, isHot, ...}]。
        """
        # 城市列表无需签名,但仍带默认参数与指纹 headers
        params: dict[str, str] = dict(DEFAULT_PARAMS)
        params["cryptoSign"] = crypto_sign(params)
        try:
            async with self._session.get(
                CITY_LIST_URL,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise ChelaileError(f"request failed: {err}") from err

        envelope = extract_json(text)
        # 兼容两种结构: {"data":{"cityList":[...]}} 或直接 {"cityList":[...]}
        data = envelope.get("data") or envelope
        city_list = data.get("cityList") or []
        return city_list

    async def async_search_lines(
        self, city_id: str, keyword: str
    ) -> list[dict[str, Any]]:
        """按线路号搜索线路,返回各方向。

        过滤掉地铁线路(subwayV2==1)。每条增加 caption 字段方便展示。
        """
        # 搜索时临时覆盖 cityId
        result = await self._request(
            EP_SEARCH_LINES,
            {
                "cityId": city_id,
                "localCityId": city_id,
                "key": keyword,
                "supportPhyStn": "true",
            },
        )
        lines = (result or {}).get("result", {}).get("lines", []) or []
        out = []
        for line in lines:
            if line.get("subwayV2") == 1:
                continue
            name = line.get("name") or ""
            # 只保留名字里包含关键词的(避免"7"匹配到"71")
            if keyword not in name:
                continue
            line = dict(line)
            line["caption"] = "{}({} -> {})".format(
                name, line.get("startSn", ""), line.get("endSn", "")
            )
            out.append(line)
        if not out:
            raise ChelaileNotFoundError(f"未找到线路号 {keyword} 的公交线路")
        return out

    async def async_get_line_detail(
        self, city_id: str, line_id: str
    ) -> dict[str, Any]:
        """获取线路详情:首末班/票价/站点列表/当前车辆。

        返回 {line: {...}, stations: [...], buses: [...], otherlines: [...]}
        """
        return await self._request(
            EP_LINE_DETAIL,
            {
                "cityId": city_id,
                "localCityId": city_id,
                "lineId": line_id,
                "lat": "",
                "lng": "",
                "geo_lat": "",
                "geo_lng": "",
            },
        )

    async def async_get_line_stations(
        self, city_id: str, line_id: str
    ) -> list[dict[str, Any]]:
        """获取线路所有站点,归一化为 [{station_id, order, name, lat, lng}]。"""
        data = await self.async_get_line_detail(city_id, line_id)
        stations = []
        for s in data.get("stations", []) or []:
            stations.append(
                {
                    "station_id": s.get("sId"),
                    "order": s.get("order"),
                    "name": s.get("sn"),
                    "lat": s.get("wgsLat"),
                    "lng": s.get("wgsLng"),
                    "physical_st_id": s.get("physicalStId"),
                    "namesake_st_id": s.get("namesakeStId"),
                }
            )
        if not stations:
            raise ChelaileNotFoundError(f"线路 {line_id} 未返回站点列表")
        return stations

    async def async_get_stop_detail(
        self,
        city_id: str,
        physical_station_id: str,
        namesake_station_id: str = "",
        first_line_id: str = "",
        lat: str = "",
        lng: str = "",
    ) -> dict[str, Any]:
        """获取站点详情(经过该站的所有线路)。"""
        return await self._request(
            EP_STOP_DETAIL,
            {
                "cityId": city_id,
                "localCityId": city_id,
                "physicalStId": physical_station_id,
                "namesakeStId": namesake_station_id,
                "firstLineId": first_line_id,
                "stationId": "",
                "lat": lat,
                "lng": lng,
                "geo_lat": lat,
                "geo_lng": lng,
                "actionState": "1",
                "permission": "0",
            },
        )

    async def async_get_realtime(
        self,
        city_id: str,
        line_id: str,
        target_order: int | str,
        station_id: str,
        lat: str = "",
        lng: str = "",
    ) -> list[dict[str, Any]]:
        """获取指定(线路,站点)的实时到站信息。

        返回最近若干辆车(按离站距离倒序,最近在前),每辆含:
            bus_id, order(当前站序), distance_to_wait(米),
            stops_away(还有几站), travel_time(秒), arrival_time(ms ts),
            capacity(0/1/2), licence, speed
        """
        target_order = str(target_order)
        data = await self._request(
            EP_BUS_DETAIL,
            {
                "cshow": "busDetail",
                "specail": "0",
                "specialType": "undefined",
                "cityId": city_id,
                "localCityId": city_id,
                "lineId": line_id,
                "targetOrder": target_order,
                "specialTargetOrder": target_order,
                "stationId": station_id,
                "lat": lat,
                "lng": lng,
                "geo_lat": lat,
                "geo_lng": lng,
                "userId": "",
                "h5Id": "",
                "unionId": "",
                "accountId": "",
                "secret": "",
            },
        )
        buses = data.get("buses", []) or []
        # 仅保留朝向目标站的车(distanceToWaitStn >= 0)
        approaching = [b for b in buses if b.get("distanceToWaitStn", -1) >= 0]
        # order 越大越接近目标站(因为 order 是车辆当前站序,目标站序固定)
        approaching.sort(key=lambda b: b.get("order", 0), reverse=True)

        out = []
        try:
            target_order_int = int(target_order)
        except (TypeError, ValueError):
            target_order_int = 0

        for bus in approaching[:3]:
            travels = bus.get("travels") or [{}]
            travel = travels[0] if travels else {}
            order = bus.get("order", 0)
            out.append(
                {
                    "bus_id": bus.get("busId"),
                    "order": order,
                    "stops_away": target_order_int - order if order else None,
                    "distance_to_wait": bus.get("distanceToWaitStn"),
                    "travel_time": travel.get("travelTime"),
                    "arrival_time": travel.get("arrivalTime"),
                    "capacity": bus.get("capacity", 0),
                    "licence": bus.get("licence"),
                    "speed": bus.get("speed"),
                }
            )
        return out
