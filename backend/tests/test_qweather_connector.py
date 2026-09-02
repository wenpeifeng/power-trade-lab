"""和风天气连接器的离线契约测试。

测试不访问公网、不读取真实凭据，也不会输出密钥。
"""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base
from app.db.models import PublicData
from crawlers.adapters.qweather import (
    QWeatherClient,
    QWeatherCrawler,
    QWeatherError,
    _forecast_quality,
    _normalize_api_host,
    _observation_quality,
    connector_status,
)


@contextmanager
def patched_settings(**values):
    original = {key: getattr(settings, key) for key in values}
    try:
        for key, value in values.items():
            setattr(settings, key, value)
        yield
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def decode_segment(value: str) -> dict:
    value += "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value.encode("ascii")))


class QWeatherClientTest(unittest.TestCase):
    def test_connector_is_disabled_by_default(self):
        with patched_settings(
            QWEATHER_ENABLED=False,
            QWEATHER_API_HOST="example.re.qweatherapi.com",
            QWEATHER_AUTH_TYPE="api_key",
            QWEATHER_API_KEY="local-test-secret",
        ):
            status = connector_status()
        self.assertFalse(status["configured"])
        self.assertFalse(status["enabled"])
        self.assertNotIn("api_host", status)

    def test_normalize_api_host_rejects_legacy_public_domain(self):
        with self.assertRaises(QWeatherError):
            _normalize_api_host("https://api.qweather.com")
        self.assertEqual(
            _normalize_api_host("https://example.re.qweatherapi.com/"),
            "example.re.qweatherapi.com",
        )

    def test_api_key_is_sent_only_in_header(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["X-QW-Api-Key"], "local-test-secret")
            self.assertNotIn("local-test-secret", str(request.url))
            return httpx.Response(
                200,
                json={
                    "code": "200",
                    "updateTime": "2026-07-23T10:00+08:00",
                    "now": {
                        "obsTime": "2026-07-23T09:50+08:00",
                        "temp": "31",
                        "humidity": "68",
                        "windSpeed": "11",
                    },
                },
            )

        with patched_settings(
            QWEATHER_API_HOST="example.re.qweatherapi.com",
            QWEATHER_AUTH_TYPE="api_key",
            QWEATHER_API_KEY="local-test-secret",
        ):
            payload = QWeatherClient(
                transport=httpx.MockTransport(handler)
            ).weather_now("101100101")
        self.assertEqual(payload["code"], "200")

    def test_jwt_contains_only_public_identifiers_and_valid_signature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_key = Ed25519PrivateKey.generate()
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            private_path = Path(temp_dir) / "private.pem"
            private_path.write_bytes(pem)

            with patched_settings(
                QWEATHER_ENABLED=True,
                QWEATHER_API_HOST="example.re.qweatherapi.com",
                QWEATHER_AUTH_TYPE="jwt",
                QWEATHER_PROJECT_ID="project-id",
                QWEATHER_CREDENTIAL_ID="credential-id",
                QWEATHER_PRIVATE_KEY_PATH=private_path,
            ):
                token = QWeatherClient()._jwt()
                status = connector_status()

            header_part, payload_part, signature_part = token.split(".")
            self.assertEqual(decode_segment(header_part)["kid"], "credential-id")
            self.assertEqual(decode_segment(payload_part)["sub"], "project-id")
            signature_part += "=" * (-len(signature_part) % 4)
            private_key.public_key().verify(
                base64.urlsafe_b64decode(signature_part),
                f"{header_part}.{payload_part}".encode("ascii"),
            )
            self.assertNotIn("PRIVATE KEY", token)
            self.assertFalse(status["secret_exposed"])

    def test_quality_rules_reject_missing_and_flag_outliers(self):
        self.assertEqual(
            _observation_quality({
                "obsTime": "2026-07-23T10:00+08:00",
                "temp": "31",
                "humidity": "55",
                "windSpeed": "9",
            }),
            "valid",
        )
        self.assertEqual(
            _observation_quality({
                "obsTime": "2026-07-23T10:00+08:00",
                "temp": "99",
                "humidity": "55",
                "windSpeed": "9",
            }),
            "suspect",
        )
        self.assertEqual(_forecast_quality({"fxTime": "x"}), "invalid")


class FakeQWeatherClient:
    def weather_now(self, location_id: str) -> dict:
        return {
            "code": "200",
            "updateTime": "2026-07-23T10:00+08:00",
            "now": {
                "obsTime": "2026-07-23T09:50+08:00",
                "temp": "31",
                "feelsLike": "34",
                "text": "多云",
                "humidity": "68",
                "precip": "0.0",
                "pressure": "998",
                "vis": "18",
                "cloud": "72",
                "dew": "23",
                "windDir": "东南风",
                "wind360": "135",
                "windScale": "2",
                "windSpeed": "9",
            },
            "refer": {"sources": ["QWeather"]},
        }

    def weather_hourly(self, location_id: str, hours: str = "24h") -> dict:
        return {
            "code": "200",
            "updateTime": "2026-07-23T10:00+08:00",
            "hourly": [{
                "fxTime": "2026-07-23T11:00+08:00",
                "temp": "32",
                "text": "多云",
                "humidity": "64",
                "pop": "20",
                "precip": "0.0",
                "pressure": "998",
                "cloud": "70",
                "dew": "23",
                "windDir": "东南风",
                "wind360": "135",
                "windScale": "2",
                "windSpeed": "10",
            }],
            "refer": {"sources": ["QWeather"]},
        }


class QWeatherCrawlerTest(unittest.TestCase):
    def test_crawler_persists_normalized_and_raw_lineage(self):
        engine = create_engine("sqlite:///:memory:")
        PublicData.__table__.create(engine)
        session = sessionmaker(bind=engine)()

        with tempfile.TemporaryDirectory() as temp_dir, patched_settings(
            QWEATHER_ENABLED=True,
            QWEATHER_API_HOST="example.re.qweatherapi.com",
            QWEATHER_AUTH_TYPE="api_key",
            QWEATHER_API_KEY="local-test-secret",
            QWEATHER_FORECAST_HOURS="24h",
            QWEATHER_LOCATIONS_JSON=json.dumps({
                "山西": {"city": "太原", "location_id": "101100101"},
            }, ensure_ascii=False),
            RAW_PUBLIC_DIR=Path(temp_dir),
        ), patch(
            "crawlers.adapters.qweather.QWeatherClient",
            return_value=FakeQWeatherClient(),
        ):
            stats = QWeatherCrawler(db=session).run()
            rows = session.query(PublicData).order_by(PublicData.data_type).all()

        self.assertEqual(stats["new"], 2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.provenance_level == "observed_authorized" for row in rows))
        self.assertTrue(all(row.quality_status == "valid" for row in rows))
        self.assertTrue(all(row.raw_sha256 and len(row.raw_sha256) == 64 for row in rows))
        self.assertTrue(all("local-test-secret" not in row.metrics for row in rows))


if __name__ == "__main__":
    unittest.main()
