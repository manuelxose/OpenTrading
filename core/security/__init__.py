"""Security primitives for trust-zone enforcement (architecture §29, ADR-0025).

- :mod:`core.security.zones` — process-level zone guards (INV-1, INV-9).
- :mod:`core.security.redact` — log redaction so secrets never reach logs (§29).
"""

from core.security.redact import (
    RedactingFilter,
    RedactingFormatter,
    install_redacting_logging,
    redact,
)
from core.security.zones import (
    EXECUTION_ZONE_MODES,
    LLM_PROCESS_ALLOWED_MODES,
    ExecutionBoundaryViolation,
    assert_llm_process_cannot_execute,
)

__all__ = [
    "EXECUTION_ZONE_MODES",
    "LLM_PROCESS_ALLOWED_MODES",
    "ExecutionBoundaryViolation",
    "RedactingFilter",
    "RedactingFormatter",
    "assert_llm_process_cannot_execute",
    "install_redacting_logging",
    "redact",
]
