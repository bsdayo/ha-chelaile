"""车来了小程序接口的异步客户端。"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any, TypedDict

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    AES_KEY,
    API_BASE,
    CITY_LIST_URL,
    DEFAULT_HEADERS,
    DEFAULT_PARAMS,
    EP_BUS_DETAIL,
    EP_LINE_DETAIL,
    EP_SEARCH_LINES,
    SIGN_SALT,
    STATUS_OK,
)


class ChelaileError(Exception):
    """上游请求失败或响应异常。"""


class ChelaileNotFoundError(ChelaileError):
    """未找到匹配的城市、线路或站点。"""


class Bus(TypedDict):
    """一辆驶向目标站点的公交车的标准化到站信息。"""

    bus_id: str | None
    license_plate: str | None
    speed_kmh: float | None
    order: int | None
    travel_time_seconds: int | None
    eta_minutes: int | None
    arrival_time: str | None
    distance_m: float
    stops_away: int | None
    capacity: str | None


def crypto_sign(params: dict[str, str]) -> str:
    """按接口要求，以参数插入顺序计算签名。"""
    value = "&".join(f'"{key}"="{value}"' for key, value in params.items())
    return hashlib.md5((value + SIGN_SALT).encode(), usedforsecurity=False).hexdigest()


def decrypt_result(ciphertext: str) -> str:
    """解密上游 AES-256-ECB 响应，并校验 PKCS7 填充。"""
    decryptor = Cipher(algorithms.AES(AES_KEY), modes.ECB()).decryptor()
    plaintext = decryptor.update(base64.b64decode(ciphertext, validate=True))
    plaintext += decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    return (unpadder.update(plaintext) + unpadder.finalize()).decode()


def _number(value: Any) -> float | None:
    """转换上游可选数值，缺失或无效时返回 None。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class ChelaileApiClient:
    """使用 Home Assistant 共享的 HTTP 会话查询车来了。"""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get_json(
        self, url: str, extra: dict[str, str] | None = None
    ) -> dict[str, Any]:
        params = {**DEFAULT_PARAMS, **(extra or {})}
        params["cryptoSign"] = crypto_sign(params)
        try:
            async with self._session.get(
                url,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                response.raise_for_status()
                text = await response.text()
            # 响应的 JSON 对象前后可能包含其他文本。
            data, _ = json.JSONDecoder().raw_decode(text, text.index("{"))
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ChelaileError(f"Request failed: {err}") from err
        return data

    async def _request(self, endpoint: str, extra: dict[str, str]) -> dict[str, Any]:
        envelope = await self._get_json(API_BASE + endpoint, extra)
        try:
            response = envelope["jsonr"]
            status = str(response["status"])
            if status not in STATUS_OK:
                raise ChelaileError(
                    f"Upstream status {status}: {response.get('errmsg', '')}"
                )
            data = response["data"]
            if "encryptResult" in data:
                data = json.loads(decrypt_result(data["encryptResult"]))
            if not isinstance(data, dict):
                raise ValueError("Expected a response object")
        except (KeyError, TypeError, ValueError) as err:
            raise ChelaileError(f"Invalid response: {err}") from err
        return data

    async def async_get_cities(self) -> list[dict[str, Any]]:
        """获取上游服务支持的城市列表。"""
        envelope = await self._get_json(CITY_LIST_URL)
        data = envelope.get("data") or envelope
        if not isinstance(data, dict) or not isinstance(data.get("cityList"), list):
            raise ChelaileError("Invalid city list")
        cities = data["cityList"]
        if not cities:
            raise ChelaileNotFoundError("No cities found")
        return cities

    async def async_search_lines(
        self, city_id: str, keyword: str
    ) -> list[dict[str, Any]]:
        """搜索公交线路，并为各方向生成说明文字。"""
        data = await self._request(
            EP_SEARCH_LINES,
            {
                "cityId": city_id,
                "localCityId": city_id,
                "key": keyword,
                "supportPhyStn": "true",
            },
        )
        result = data.get("result") or {}
        lines = []
        for line in result.get("lines") or []:
            name = line.get("name") or ""
            if str(line.get("subwayV2")) == "1" or keyword not in name:
                continue
            lines.append(
                {
                    **line,
                    "caption": (
                        f"{name} ({line.get('startSn', '')} → {line.get('endSn', '')})"
                    ),
                }
            )
        if not lines:
            raise ChelaileNotFoundError(f"No bus lines found for {keyword}")
        return lines

    async def async_get_line_stations(
        self, city_id: str, line_id: str
    ) -> list[dict[str, Any]]:
        """按行驶顺序返回线路站点。"""
        data = await self._request(
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
        stations = [
            {
                "station_id": station["sId"],
                "order": station["order"],
                "name": station["sn"],
                "lat": station.get("wgsLat"),
                "lng": station.get("wgsLng"),
            }
            for station in data.get("stations") or []
        ]
        if not stations:
            raise ChelaileNotFoundError(f"No stations found for line {line_id}")
        return stations

    async def async_get_realtime(
        self,
        city_id: str,
        line_id: str,
        target_order: int | str,
        station_id: str,
        lat: str = "",
        lng: str = "",
    ) -> list[Bus]:
        """按距离由近到远返回最多三辆驶向目标站点的公交车。"""
        data = await self._request(
            EP_BUS_DETAIL,
            {
                "cityId": city_id,
                "localCityId": city_id,
                "cshow": "busDetail",
                "specail": "0",
                "specialType": "undefined",
                "lineId": line_id,
                "targetOrder": str(target_order),
                "specialTargetOrder": str(target_order),
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
        if not isinstance(data.get("buses"), list):
            raise ChelaileError("Invalid bus list")
        buses: list[Bus] = []
        for bus in data["buses"]:
            distance = _number(bus.get("distanceToWaitStn"))
            if distance is None:
                raise ChelaileError("Invalid bus distance")
            if distance < 0:
                continue
            travel = (bus.get("travels") or [{}])[0]
            seconds = _number(travel.get("travelTime"))
            travel_time = (
                math.ceil(seconds) if seconds is not None and seconds >= 0 else None
            )
            order = _number(bus.get("order"))
            speed = _number(bus.get("speed"))
            timestamp = _number(travel.get("arrivalTime"))
            arrival_time = None
            if timestamp is not None and timestamp > 0:
                try:
                    arrival_time = datetime.fromtimestamp(
                        timestamp / 1000, UTC
                    ).isoformat()
                except (OverflowError, OSError, ValueError):
                    pass
            buses.append(
                {
                    "bus_id": (
                        str(bus["busId"]) if bus.get("busId") is not None else None
                    ),
                    "license_plate": bus.get("licence") or None,
                    "speed_kmh": speed if speed is not None and speed >= 0 else None,
                    "order": (int(order) if order is not None and order >= 0 else None),
                    "travel_time_seconds": travel_time,
                    "eta_minutes": (
                        math.ceil(travel_time / 60) if travel_time is not None else None
                    ),
                    "arrival_time": arrival_time,
                    "distance_m": distance,
                    "stops_away": (
                        max(0, int(target_order) - int(order))
                        if order is not None and order >= 0
                        else None
                    ),
                    "capacity": {0: "empty", 1: "moderate", 2: "crowded"}.get(
                        _number(bus.get("capacity"))
                    ),
                }
            )
        buses.sort(key=lambda bus: bus["distance_m"])
        return buses[:3]
