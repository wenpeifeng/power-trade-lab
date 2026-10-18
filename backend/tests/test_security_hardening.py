"""开源发布前的关键安全边界回归测试。"""
import logging
import stat
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.credentials import (
    _resolve_master_key,
    config_status,
    decrypt_api_key,
    get_user_runtime_config,
    normalize_llm_config,
    save_user_llm_config,
)
from app.common.auth import _resolve_jwt_secret
from app.common.auth import get_current_user, require_admin
from app.common.input_security import (
    UnsafeInputError,
    safe_filename,
    sanitize_outbound_headers,
    validate_file_signature,
    validate_outbound_url,
)


class JwtSecretSecurityTests(unittest.TestCase):
    def test_explicit_secret_must_be_long_enough(self):
        with self.assertRaises(RuntimeError):
            _resolve_jwt_secret(
                configured="too-short",
                environment="production",
                secret_file=Path("unused"),
            )

    def test_production_cannot_fall_back_to_generated_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                _resolve_jwt_secret(
                    configured="",
                    environment="production",
                    secret_file=Path(temp_dir) / "jwt-secret.key",
                )

    def test_development_secret_is_private_and_stable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / "credentials" / "jwt-secret.key"
            first = _resolve_jwt_secret(
                configured="",
                environment="development",
                secret_file=secret_file,
            )
            second = _resolve_jwt_secret(
                configured="",
                environment="development",
                secret_file=secret_file,
            )

            self.assertGreaterEqual(len(first), 32)
            self.assertEqual(first, second)
            self.assertEqual(stat.S_IMODE(secret_file.stat().st_mode), 0o600)


class AdminRouteSecurityTests(unittest.TestCase):
    def test_sensitive_routers_require_admin(self):
        from app.admin.router import router as admin_router
        from app.knowledge.admin_router import router as asset_router

        # admin 路由：全部端点必须保留 admin 守卫
        for route in admin_router.routes:
            dependency_calls = {
                dependency.call for dependency in route.dependant.dependencies
            }
            self.assertIn(
                require_admin,
                dependency_calls,
                msg=f"{route.path} 缺少管理员权限依赖",
            )

        # asset 路由：读端点已放开给任意登录用户，但每个端点必须至少要求登录
        # （require_admin 内部已依赖 get_current_user，属顶级依赖则二者其一即可）
        for route in asset_router.routes:
            dependency_calls = {
                dependency.call for dependency in route.dependant.dependencies
            }
            self.assertTrue(
                get_current_user in dependency_calls
                or require_admin in dependency_calls,
                msg=f"{route.path} 缺少登录鉴权依赖",
            )

    def test_asset_write_routes_keep_require_admin_guard(self):
        """资产路由的所有写/审核端点必须保留 require_admin 守卫。

        Task1 把读端点放开给任意登录用户，但写/审核端点（含 ingest 通道、
        crawler/run、qweather/test、track-ref、review*、doc/update、以及 GET
        但属审核敏感操作的 /review/pending）必须保留 require_admin，防止
        误把 require_admin 降级为 get_current_user 导致越权写入。
        通过结构化内省 route.dependant.dependencies 的 callable 集合判定。
        """
        from app.knowledge.admin_router import router as asset_router

        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        for route in asset_router.routes:
            methods = getattr(route, "methods", None) or set()
            if not (methods & write_methods):
                continue
            dependency_calls = {
                dependency.call for dependency in route.dependant.dependencies
            }
            self.assertIn(
                require_admin,
                dependency_calls,
                msg=f"写端点 {route.path} 缺少 require_admin 守卫（不应降级为 get_current_user）",
            )

        # /review/pending 是 GET 但属审核敏感操作，必须保留 require_admin
        pending_route = next(
            (r for r in asset_router.routes if r.path.endswith("/review/pending")),
            None,
        )
        self.assertIsNotNone(pending_route, msg="/asset/review/pending 路由缺失")
        self.assertIn(
            require_admin,
            {d.call for d in pending_route.dependant.dependencies},
            msg="/asset/review/pending 必须保留 require_admin 守卫",
        )


class AuthProtectionTests(unittest.TestCase):
    def test_auth_rate_limiter_uses_sliding_window(self):
        from app.common.rate_limit import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(max_attempts=2, window_seconds=10)
        self.assertTrue(limiter.check("client", now=100).allowed)
        self.assertTrue(limiter.record("client", now=100).allowed)
        self.assertFalse(limiter.record("client", now=101).allowed)
        self.assertFalse(limiter.check("client", now=105).allowed)
        self.assertTrue(limiter.check("client", now=111).allowed)

    def test_new_password_policy_blocks_common_passwords(self):
        from app.auth.router import _validate_new_password

        with self.assertRaises(ValueError):
            _validate_new_password("12345678", "learner")
        with self.assertRaises(ValueError):
            _validate_new_password("learner", "learner")
        self.assertEqual(
            _validate_new_password("safe-pass-2026", "learner"),
            "safe-pass-2026",
        )


class LogRedactionTests(unittest.TestCase):
    def test_tokens_and_passwords_are_redacted(self):
        from app.common.logging_security import redact_sensitive_text

        raw = (
            "Authorization: Bearer abc.def.ghi "
            "api_key=secret-value password=hunter2 "
            "https://example.com/data?token=query-secret&safe=1"
        )
        cleaned = redact_sensitive_text(raw)
        for secret in ("abc.def.ghi", "secret-value", "hunter2", "query-secret"):
            self.assertNotIn(secret, cleaned)
        self.assertIn("safe=1", cleaned)

    def test_uvicorn_access_arguments_keep_formatter_shape(self):
        from app.common.logging_security import SensitiveDataFilter

        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("127.0.0.1", "GET", "/api?token=secret-value", "1.1", 200),
            exc_info=None,
        )
        self.assertTrue(SensitiveDataFilter().filter(record))
        self.assertEqual(len(record.args), 5)
        self.assertNotIn("secret-value", str(record.args))


class ExternalInputSecurityTests(unittest.TestCase):
    def test_private_and_non_http_targets_are_rejected(self):
        for url in (
            "http://127.0.0.1:8000/private",
            "http://169.254.169.254/latest/meta-data",
            "http://localhost/admin",
            "file:///etc/passwd",
            "http://user:password@example.com/data",
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeInputError):
                validate_outbound_url(url)

    def test_public_ip_is_allowed(self):
        self.assertEqual(validate_outbound_url("https://1.1.1.1/data"), "https://1.1.1.1/data")

    def test_dangerous_proxy_headers_are_removed(self):
        cleaned = sanitize_outbound_headers({
            "Host": "127.0.0.1",
            "X-Forwarded-For": "127.0.0.1",
            "Authorization": "Bearer example",
            "Accept": "application/json",
        })
        self.assertNotIn("Host", cleaned)
        self.assertNotIn("X-Forwarded-For", cleaned)
        self.assertEqual(cleaned["Accept"], "application/json")
        self.assertEqual(cleaned["Authorization"], "Bearer example")

    def test_uploaded_filename_cannot_escape_storage_directory(self):
        self.assertEqual(safe_filename("../../etc/passwd.pdf"), "passwd.pdf")
        self.assertEqual(safe_filename("..\\..\\secret.xlsx"), "secret.xlsx")

    def test_spoofed_document_extensions_are_rejected(self):
        for filename, content in (
            ("payload.pdf", b"MZ executable"),
            ("payload.xlsx", b"not a zip"),
            ("payload.csv", b"\x00" * 200),
        ):
            with self.subTest(filename=filename), self.assertRaises(UnsafeInputError):
                validate_file_signature(filename, content)

    def test_valid_pdf_signature_is_allowed(self):
        validate_file_signature("document.pdf", b"%PDF-1.7\nexample")


class PerUserLLMCredentialTests(unittest.TestCase):
    def test_master_key_is_private_and_production_requires_explicit_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "llm-master.key"
            generated = _resolve_master_key("", "development", key_file)
            Fernet(generated)
            self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)
            self.assertEqual(generated, _resolve_master_key("", "development", key_file))
        with self.assertRaises(RuntimeError):
            _resolve_master_key("", "production", Path("unused"))

    def test_cloud_model_cannot_point_to_local_network(self):
        for url in ("http://example.com/v1", "https://127.0.0.1/v1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_llm_config("openai", url, "example-model")

    def test_user_key_is_encrypted_and_status_never_returns_secret(self):
        from app.db.database import Base
        from app.db.models import User, UserLLMConfig

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[User.__table__, UserLLMConfig.__table__])
        session = sessionmaker(bind=engine)()
        try:
            user = User(username="security-test", hashed_password="unused", role="user")
            session.add(user)
            session.commit()
            session.refresh(user)
            secret = "test-user-key-that-must-never-be-returned"
            row = save_user_llm_config(
                session,
                user.id,
                provider="zhipu",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                model="glm-4-flash",
                api_key=secret,
            )
            self.assertNotIn(secret, row.encrypted_api_key)
            self.assertEqual(decrypt_api_key(row.encrypted_api_key), secret)
            runtime = get_user_runtime_config(session, user.id)
            self.assertEqual(runtime.api_key, secret)
            public_status = config_status(row)
            self.assertNotIn("encrypted_api_key", public_status)
            self.assertNotIn(secret, str(public_status))
            self.assertEqual(public_status["api_key_masked"], "***rned")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
