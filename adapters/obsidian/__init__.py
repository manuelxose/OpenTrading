"""Obsidian adapter: a non-authoritative human knowledge mirror (§25)."""

from adapters.obsidian.export import (
    MirroringEventBus,
    ObsidianExporter,
    SecretDetectedError,
    ensure_secret_free,
    initialize_vault,
)
from adapters.obsidian.vault import FileVaultWriter, MemoryVaultWriter, NullVaultWriter, VaultWriter

__all__ = [
    "FileVaultWriter",
    "MemoryVaultWriter",
    "MirroringEventBus",
    "NullVaultWriter",
    "ObsidianExporter",
    "SecretDetectedError",
    "VaultWriter",
    "ensure_secret_free",
    "initialize_vault",
]
