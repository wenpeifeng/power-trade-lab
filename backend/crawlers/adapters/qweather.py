"""和风天气国内气象连接器。

能力：
- 兼容 API KEY 和官方推荐的 Ed25519 JWT
- 同步五个首批省份省会的近实时观测与逐小时预报
- 保存原始 JSON、哈希、抓取时间、解析器版本和质量状态
- 不记录、不返回 API KEY、JWT 或私钥

气象是电力交易的辅助特征，不冒充交易中心数据。
"""
from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app.config import settings
from crawlers.market_data_base import CrawledSeries, MarketDataCrawler

logger = logging.getLogger("crawler.qweather")

PARSER_VERSION = "qweather-v1"
SOURCE_NAME = "和风天气开发者服务"
NOW_DOC_URL = "https://dev.qweather.com/docs/api/weather/weather-now/"
HOURLY_DOC_URL = "https://dev.qweather.com/docs/api/weather/weather-hourly-forecast/"
CITY_DOC_URL = "https://dev.qweather.com/docs/api/geoapi/city-lookup/"

# LocationID 来自和风城市数据。配置项 QWEATHER_LOCATIONS_JSON 可完全覆盖。
DEFAULT_LOCATIONS = {
    "山西": {"city": "太原", "location_id": "101100101"},
    "山东": {"city": "济南", "location_id": "101120101"},
    "广东": {"city": "广州", "location_id": "101280101"},
    "浙江": {"city": "杭州", "location_id": "101210101"},
    "蒙西": {"city": "呼和浩特", "location_id": "101080101"},
}


class QWeatherError(RuntimeError):
    """可安全展示的和风连接错误，不包含请求凭证。"""


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _normalize_api_host(raw_host: str) -> str:
    host = raw_host.strip().replace("https://", "").replace("http://", "").strip("/")
    if not host or "/" in host or "." not in host:
        raise QWeatherError("QWEATHER_API_HOST 应填写控制台分配的专属域名，不含路径")
    if host in {"api.qweather.com", "devapi.qweather.com", "geoapi.qweather.com"}:
        raise QWeatherError("请使用和风控制台分配的专属 API Host，不要使用即将停用的公共域名")
    return host


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _local_timestamp(value: str) -> str:
    """把带时区 ISO 时间规范成 PublicData 的 YYYY-MM-DD HH:MM。"""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)[:16].replace("T", " ")


def configured_locations() -> dict[str, dict[str, str]]:
    if not settings.QWEATHER_LOCATIONS_JSON.strip():
        return DEFAULT_LOCATIONS
    try:
        parsed = json.loads(settings.QWEATHER_LOCATIONS_JSON)
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError
        result = {}
        for province, item in parsed.items():
            if not isinstance(item, dict) or not item.get("location_id"):
                raise ValueError
            result[str(province)] = {
                "city": str(item.get("city") or province),
                "location_id": str(item["location_id"]),
            }
        return result
    except (json.JSONDecodeError, ValueError) as exc:
        raise QWeatherError("QWEATHER_LOCATIONS_JSON 格式无效") from exc


class QWeatherClient:
    def __init__(self, transport: Optional[httpx.BaseTransport] = None):
        self.host = _normalize_api_host(settings.QWEATHER_API_HOST)
        self.auth_type = settings.QWEATHER_AUTH_TYPE.strip().lower()
        self.transport = transport
        self._last_request_at = 0.0
        if self.auth_type not in {"api_key", "jwt"}:
            raise QWeatherError("QWEATHER_AUTH_TYPE 只能是 api_key 或 jwt")
        self._validate_credentials()

    def _validate_credentials(self) -> None:
        if self.auth_type == "api_key":
            if not settings.QWEATHER_API_KEY.strip():
                raise QWeatherError("尚未配置 QWEATHER_API_KEY")
            return
        if not settings.QWEATHER_PROJECT_ID.strip():
            raise QWeatherError("尚未配置 QWEATHER_PROJECT_ID")
        if not settings.QWEATHER_CREDENTIAL_ID.strip():
            raise QWeatherError("尚未配置 QWEATHER_CREDENTIAL_ID")
        if not settings.QWEATHER_PRIVATE_KEY_PATH.is_file():
            raise QWeatherError("和风 JWT 私钥文件不存在")

    def _jwt(self) -> str:
        now = int(time.time())
        header = {"alg": "EdDSA", "kid": settings.QWEATHER_CREDENTIAL_ID.strip()}
        payload = {
            "sub": settings.QWEATHER_PROJECT_ID.strip(),
            "iat": now - 30,
            "exp": now + 870,
        }
        encoded_header = _base64url(
            json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        encoded_payload = _base64url(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        try:
            private_key = load_pem_private_key(
                settings.QWEATHER_PRIVATE_KEY_PATH.read_bytes(), password=None
            )
            signature = private_key.sign(signing_input)
        except Exception as exc:
            raise QWeatherError("无法读取或使用和风 Ed25519 私钥") from exc
        return f"{encoded_header}.{encoded_payload}.{_base64url(signature)}"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "PowerTradeLab/0.1 qweather-connector",
        }
        if self.auth_type == "api_key":
            headers["X-QW-Api-Key"] = settings.QWEATHER_API_KEY.strip()
        else:
            headers["Authorization"] = f"Bearer {self._jwt()}"
        return headers

    def get(self, path: str, params: dict[str, Any]) -> dict:
        url = f"https://{self.host}/{path.lstrip('/')}"
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)
        try:
            with httpx.Client(
                timeout=20,
                follow_redirects=True,
                transport=self.transport,
                headers=self._headers(),
            ) as client:
                response = client.get(url, params=params)
                self._last_request_at = time.monotonic()
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise QWeatherError(f"和风接口 HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise QWeatherError("无法连接或解析和风天气接口") from exc

        code = str(payload.get("code", ""))
        if code != "200":
            safe_messages = {
                "204": "请求成功但没有匹配数据",
                "400": "请求参数错误",
                "401": "认证失败，请检查 API Host 和凭据",
                "402": "订阅或额度不可用",
                "403": "无权访问该接口",
                "404": "接口或数据不存在",
                "429": "超过请求频率或额度",
                "500": "和风服务内部错误",
            }
            raise QWeatherError(f"和风返回 {code or '未知代码'}：{safe_messages.get(code, '请求失败')}")
        return payload

    def city_lookup(self, location: str, adm: Optional[str] = None) -> dict:
        params = {"location": location, "range": "cn", "number": 5, "lang": "zh"}
        if adm:
            params["adm"] = adm
        payload = self.get("/geo/v2/city/lookup", params)
        items = payload.get("location") or []
        if not items:
            raise QWeatherError(f"未找到国内城市：{location}")
        return items[0]

    def weather_now(self, location_id: str) -> dict:
        return self.get("/v7/weather/now", {"location": location_id, "lang": "zh", "unit": "m"})

    def weather_hourly(self, location_id: str, hours: str = "24h") -> dict:
        if hours not in {"24h", "72h", "168h"}:
            raise QWeatherError("逐小时预报范围只能是 24h、72h 或 168h")
        return self.get(
            f"/v7/weather/{hours}",
            {"location": location_id, "lang": "zh", "unit": "m"},
        )


def connector_status() -> dict[str, Any]:
    """返回不含凭证值和账号标识的配置状态。"""
    host = settings.QWEATHER_API_HOST.strip()
    config_errors = []
    if not settings.QWEATHER_ENABLED:
        config_errors.append("和风天气连接器默认关闭")
    elif host:
        try:
            _normalize_api_host(host)
        except QWeatherError as exc:
            config_errors.append(str(exc))
    else:
        config_errors.append("尚未配置 API Host")
    try:
        locations = configured_locations()
    except QWeatherError as exc:
        locations = {}
        config_errors.append(str(exc))
    return {
        "connector": "qweather",
        "enabled": settings.QWEATHER_ENABLED,
        "configured": settings.qweather_configured,
        "auth_type": settings.QWEATHER_AUTH_TYPE.strip().lower(),
        "api_host_configured": bool(host),
        "locations": locations,
        "forecast_hours": settings.QWEATHER_FORECAST_HOURS,
        "secret_exposed": False,
        "configuration_errors": config_errors,
    }


def test_connection() -> dict[str, Any]:
    client = QWeatherClient()
    first_province, location = next(iter(configured_locations().items()))
    payload = client.weather_now(location["location_id"])
    current = payload["now"]
    return {
        "ok": True,
        "provider": SOURCE_NAME,
        "province": first_province,
        "city": location["city"],
        "location_id": location["location_id"],
        "obs_time": current.get("obsTime"),
        "weather": current.get("text"),
        "temp_c": _safe_float(current.get("temp")),
        "update_time": payload.get("updateTime"),
    }


def _observation_quality(current: dict) -> str:
    required = ("obsTime", "temp", "humidity", "windSpeed")
    if any(current.get(key) in (None, "") for key in required):
        return "invalid"
    temp = _safe_float(current.get("temp"))
    humidity = _safe_float(current.get("humidity"))
    wind_speed = _safe_float(current.get("windSpeed"))
    if temp is None or humidity is None or wind_speed is None:
        return "invalid"
    if not (-90 <= temp <= 70 and 0 <= humidity <= 100 and 0 <= wind_speed <= 250):
        return "suspect"
    return "valid"


def _forecast_quality(hour: dict) -> str:
    required = ("fxTime", "temp", "humidity", "windSpeed")
    if any(hour.get(key) in (None, "") for key in required):
        return "invalid"
    temp = _safe_float(hour.get("temp"))
    humidity = _safe_float(hour.get("humidity"))
    if temp is None or humidity is None or not (-90 <= temp <= 70 and 0 <= humidity <= 100):
        return "suspect"
    return "valid"


class QWeatherCrawler(MarketDataCrawler):
    name = "qweather"
    rate_limit = 0.2

    def run(self) -> dict:
        if not settings.qweather_configured:
            return {
                "source": self.name,
                "new": 0,
                "updated": 0,
                "dup": 0,
                "errors": 0,
                "skipped": True,
                "reason": "和风天气尚未配置",
            }
        return super().run()

    def fetch_series(self) -> list[CrawledSeries]:
        client = QWeatherClient()
        fetched_at = datetime.now().astimezone().isoformat()
        series: list[CrawledSeries] = []

        for province, location in configured_locations().items():
            location_id = location["location_id"]
            city = location["city"]
            now_payload = client.weather_now(location_id)
            current = now_payload.get("now") or {}
            now_quality = _observation_quality(current)
            if now_quality == "invalid":
                raise QWeatherError(f"{province}{city}实况数据缺少必要字段")
            now_metrics = {
                "provider": "qweather",
                "city": city,
                "location_id": location_id,
                "obs_time": current.get("obsTime"),
                "weather": current.get("text"),
                "temp_c": _safe_float(current.get("temp")),
                "feels_like_c": _safe_float(current.get("feelsLike")),
                "humidity_pct": _safe_float(current.get("humidity")),
                "precip_mm": _safe_float(current.get("precip")),
                "pressure_hpa": _safe_float(current.get("pressure")),
                "visibility_km": _safe_float(current.get("vis")),
                "cloud_pct": _safe_float(current.get("cloud")),
                "dew_c": _safe_float(current.get("dew")),
                "wind_direction": current.get("windDir"),
                "wind_degree": _safe_float(current.get("wind360")),
                "wind_scale": current.get("windScale"),
                "wind_speed_kmh": _safe_float(current.get("windSpeed")),
                "data_freshness": "near_real_time",
                "provenance_level": "observed_authorized",
                "disclosure_scope": "authorized_api",
                "refer": now_payload.get("refer"),
            }
            series.append(CrawledSeries(
                data_type="weather_observation",
                province=province,
                data_date=_local_timestamp(str(current.get("obsTime", ""))),
                metrics=now_metrics,
                source=SOURCE_NAME,
                source_url=NOW_DOC_URL,
                provenance_level="observed_authorized",
                disclosure_scope="authorized_api",
                fetched_at=fetched_at,
                parser_version=PARSER_VERSION,
                quality_status=now_quality,
                update_existing=True,
                raw={
                    "provider": "qweather",
                    "endpoint": "/v7/weather/now",
                    "province": province,
                    "city": city,
                    "location_id": location_id,
                    "response": now_payload,
                },
            ))

            hourly_payload = client.weather_hourly(location_id, settings.QWEATHER_FORECAST_HOURS)
            issued_at = hourly_payload.get("updateTime")
            hourly_items = hourly_payload.get("hourly") or []
            if not hourly_items:
                raise QWeatherError(f"{province}{city}逐小时预报为空")
            for hour in hourly_items:
                quality = _forecast_quality(hour)
                if quality == "invalid":
                    continue
                metrics = {
                    "provider": "qweather",
                    "city": city,
                    "location_id": location_id,
                    "issued_at": issued_at,
                    "forecast_for": hour.get("fxTime"),
                    "weather": hour.get("text"),
                    "temp_c": _safe_float(hour.get("temp")),
                    "dew_c": _safe_float(hour.get("dew")),
                    "humidity_pct": _safe_float(hour.get("humidity")),
                    "precip_probability_pct": _safe_float(hour.get("pop")),
                    "precip_mm": _safe_float(hour.get("precip")),
                    "pressure_hpa": _safe_float(hour.get("pressure")),
                    "cloud_pct": _safe_float(hour.get("cloud")),
                    "wind_direction": hour.get("windDir"),
                    "wind_degree": _safe_float(hour.get("wind360")),
                    "wind_scale": hour.get("windScale"),
                    "wind_speed_kmh": _safe_float(hour.get("windSpeed")),
                    "data_freshness": "forecast",
                    "provenance_level": "observed_authorized",
                    "disclosure_scope": "authorized_api",
                    "refer": hourly_payload.get("refer"),
                }
                series.append(CrawledSeries(
                    data_type="weather_forecast_hourly",
                    province=province,
                    data_date=_local_timestamp(str(hour.get("fxTime", ""))),
                    metrics=metrics,
                    source=SOURCE_NAME,
                    source_url=HOURLY_DOC_URL,
                    provenance_level="observed_authorized",
                    disclosure_scope="authorized_api",
                    fetched_at=fetched_at,
                    parser_version=PARSER_VERSION,
                    quality_status=quality,
                    update_existing=True,
                    raw={
                        "provider": "qweather",
                        "endpoint": f"/v7/weather/{settings.QWEATHER_FORECAST_HOURS}",
                        "province": province,
                        "city": city,
                        "location_id": location_id,
                        "response": hourly_payload,
                    },
                ))
        return series
