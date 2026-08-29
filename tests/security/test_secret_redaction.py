"""Secret hygiene: masking in logs and settings (architecture §29, ADR-0025).

Secrets must never appear in logs; pydantic ``SecretStr`` must mask settings
reprs; DSNs and age keys must be redacted.
"""

from __future__ import annotations

import logging

from core.config.settings import Settings
from core.security import RedactingFilter, RedactingFormatter, redact


class TestSettingsMasking:
    def test_live_secrets_are_masked_in_repr_and_str(self) -> None:
        settings = Settings(
            live_approval_signing_key="a" * 64,
            live_operator_token="opentrading-super-secret-operator-token",
        )
        rendered = f"{settings!r} {settings}"
        assert "super-secret-operator-token" not in rendered
        assert settings.live_operator_token.get_secret_value() == (
            "opentrading-super-secret-operator-token"
        )


class TestRedact:
    def test_langfuse_style_keys(self) -> None:
        assert redact("key=sk-lf-1234567890abcdef") == "key=***"
        # even dev placeholders are masked: they are `sk-`-shaped tokens
        assert "sk-lf-opentrading-dev" not in redact("dev placeholder: sk-lf-opentrading-dev")

    def test_bearer_tokens(self) -> None:
        text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
        assert "abcdefghijklmnopqrstuvwxyz" not in redact(text)

    def test_key_value_secrets(self) -> None:
        text = "connect failed password=hunter2, token: abc123"
        redacted = redact(text)
        assert "hunter2" not in redacted
        assert "abc123" not in redacted

    def test_env_style_secret_names(self) -> None:
        # The repo's canonical secret env names must be masked (review F1).
        cases = [
            "OT_LIVE_APPROVAL_SIGNING_KEY=supersecret123",
            "OT_LIVE_OPERATOR_TOKEN=operator-token-456",
            "OT_MINIO_SECRET_KEY=minio-secret-456",
            "OT_POSTGRES_PASSWORD=hunter2",
            "REDIS_PASSWORD=redissecret789",
            "LANGFUSE_ENCRYPTION_KEY=001122aabbccddeeff",
        ]
        for case in cases:
            masked = redact(case)
            assert masked.split("=", 1)[1] == "***", f"{case!r} leaked: {masked!r}"
            assert case.split("=", 1)[1] not in masked

    def test_redact_none_and_empty(self) -> None:
        assert redact(None) == ""
        assert redact("") == ""

    def test_filter_masks_record_before_plain_handlers(self) -> None:
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="loaded OT_LIVE_APPROVAL_SIGNING_KEY=deadbeefsecret",
            args=(),
            exc_info=None,
        )
        assert RedactingFilter().filter(record) is True
        assert "deadbeefsecret" not in record.getMessage()
        assert "OT_LIVE_APPROVAL_SIGNING_KEY=***" in record.getMessage()

    def test_postgres_and_redis_dsns(self) -> None:
        assert "s3cret" not in redact("postgresql://user:s3cret@db:5432/x")
        assert "s3cret" not in redact("redis://opentrading:s3cret@redis:6379/0")

    def test_age_secret_keys(self) -> None:
        masked = redact(
            "AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ"
        )
        assert masked == "AGE-SECRET-KEY-***"
        assert "QQQQ" not in masked


class TestRedactingFormatter:
    def test_formatter_masks_record_message(self) -> None:
        formatter = RedactingFormatter("%(levelname)s %(message)s")
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="starting with api_key=sk-lf-abcdef12345678",
            args=(),
            exc_info=None,
        )
        rendered = formatter.format(record)
        assert "sk-lf-" not in rendered
        assert "abcdef12345678" not in rendered
