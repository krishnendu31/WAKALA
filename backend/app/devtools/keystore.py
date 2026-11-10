"""DEVELOPMENT-ONLY private key storage.

Generates Ed25519 private keys on first use and stores them as unencrypted
PKCS#8 PEM files in a git-ignored directory (default ``backend/.dev_keys``).
These keys protect only synthetic data and exist so the demo can run offline.

The gateway never imports this module: it verifies with *public* keys from the
database registry. Production replaces this with workload identity or
managed signing keys (HSM / cloud KMS) where private keys never leave the
signing boundary — see docs/SECURITY_MODEL.md.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, load_pem_private_key

_KEY_ID = re.compile(r"^KEY-[A-Z0-9-]{4,40}$")
_README = (
    "DEVELOPMENT KEYS ONLY - WAKALA prototype.\n"
    "Generated locally for synthetic demo identities. Never commit, share or reuse these files.\n"
    "Delete this directory to rotate all development keys (mandates are re-issued on next start).\n"
)


class PrivateKeyProvider(Protocol):
    def private_key(self, key_id: str) -> Ed25519PrivateKey: ...


class DevKeystore:
    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        readme = self._dir / "README.txt"
        if not readme.exists():
            readme.write_text(_README, encoding="utf-8")
        gitignore = self._dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")

    def officer_password(self, officer_id: str) -> str:
        """DEVELOPMENT-ONLY officer password (generated once, stored beside the dev keys)."""
        from app.services.officers import DevOfficerCredentials
        return DevOfficerCredentials(self._dir).password(officer_id)

    def _path(self, key_id: str) -> Path:
        if not _KEY_ID.fullmatch(key_id):  # prevents path traversal via key ids
            raise ValueError(f"invalid key id {key_id!r}")
        return self._dir / f"{key_id}.pem"

    def private_key(self, key_id: str) -> Ed25519PrivateKey:
        path = self._path(key_id)
        if path.exists():
            key = load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError(f"{path.name} is not an Ed25519 key")
            return key
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(pem)
        return key
