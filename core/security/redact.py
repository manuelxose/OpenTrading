"""Log redaction — secrets must never reach logs (architecture §29, ADR-0025).

Applies ordered regex masks to log records: API keys, bearer tokens,
`key=value` secrets (including env-style names such as
``OT_LIVE_APPROVAL_SIGNING_KEY=…``), DSN passwords and age secret keys.

- :class:`RedactingFilter` mutates the record before *any* handler renders it
  (attach to the root logger and per-framework loggers).
- :class:`RedactingFormatter` is the belt-and-braces layer for std handlers.
- :func:`install_redacting_logging` wires both at process startup.
"""

from __future__ import annotations

import logging
import re
from typing import Final

__all__ = ["RedactingFilter", "RedactingFormatter", "install_redacting_logging", "redact"]

#: (pattern, replacement) pairs, applied in order. More specific patterns first.
_RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # SOPS age secret keys: AGE-SECRET-KEY-<58 base62 chars>
    (re.compile(r"AGE-SECRET-KEY-[0-9A-Za-z]{40,}", re.IGNORECASE), "AGE-SECRET-KEY-***"),
    # Langfuse / generic `sk-`-style API keys
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}", re.IGNORECASE), "sk-***"),
    # `Authorization: Bearer <token>` headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
    # key=value / key: value secrets — the name is kept, the value is masked.
    # Covers `password=…`, `api_key: …` and env-style names such as
    # `OT_LIVE_APPROVAL_SIGNING_KEY=…` or `MINIO_SECRET_KEY=…` (longer
    # alternatives first so `signing_key` beats bare `key`/`secret`).
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_]*("
            r"signing[_-]?key|secret[_-]?key|access[_-]?key|private[_-]?key|"
            r"encryption[_-]?key|api[_-]?key|password|passwd|pwd|token|secret|key"
            r")[A-Za-z0-9_]*)\s*[:=]\s*\S+"
        ),
        r"\1=***",
    ),
    # PostgreSQL / Redis DSNs: mask the userinfo component
    (
        re.compile(r"(?i)\b((?:postgres|postgresql|redis)://)[^@\s]*@"),
        r"\1***@",
    ),
    # AWS-style access keys / MinIO credentials
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "AKIA***"),
)


def redact(text: str | None) -> str:
    """Return ``text`` with every known secret pattern masked (``None`` → ``""``)."""
    if text is None:
        return ""
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    """Masks secret patterns on the record itself, before any handler renders.

    Attached to a logger (or the root logger) this covers handlers whose
    formatter is not redacting — e.g. uvicorn's own handlers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        record.msg = redact(message)
        record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """Formatter that masks secret patterns (including exception text)."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


_installed = False


def _attach_filter(logger: logging.Logger) -> None:
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())


def install_redacting_logging(
    *,
    level: int = logging.INFO,
    log_format: str = "%(asctime)s %(levelname)s %(name)s: %(message)s",
    force: bool = False,
) -> None:
    """Install redaction process-wide: filter + redacting std handler.

    Idempotent across calls (e.g. worker CLI + API import paths). Attaches the
    filter to the root logger and to uvicorn's loggers so every handler — even
    non-redacting ones — emits masked records.
    """
    global _installed
    if _installed and not force:
        return
    _installed = True

    root = logging.getLogger()
    _attach_filter(root)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _attach_filter(logging.getLogger(name))

    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(log_format))
    root.handlers[:] = [h for h in root.handlers if not isinstance(h.formatter, RedactingFormatter)]
    root.addHandler(handler)
    root.setLevel(level)
