"""Small, auditable cryptographic primitives (Ed25519 via `cryptography`).

Signing rules used everywhere in WAKALA:

* payload = canonical JSON: keys sorted, no insignificant whitespace, UTF-8,
  produced from the *validated* Pydantic model (``model_dump(mode="json")``)
* message = domain-separation tag + payload. Distinct tags for action
  requests and mandates mean a signature over one can never be replayed as
  the other.
* signature = raw 64-byte Ed25519 signature, base64url without padding
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ACTION_REQUEST_TAG = b"WAKALA-ACTION-REQUEST-v1\n"
MANDATE_TAG = b"WAKALA-MANDATE-v1\n"


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def public_key_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def public_key_fingerprint(key: Ed25519PublicKey) -> str:
    return "sha256:" + sha256_hex(public_key_bytes(key))


def load_public_key(encoded: str) -> Ed25519PublicKey:
    raw = b64url_decode(encoded)
    if len(raw) != 32:
        raise ValueError("Ed25519 public keys are 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def sign(private_key: Ed25519PrivateKey, tag: bytes, payload: bytes) -> str:
    return b64url_encode(private_key.sign(tag + payload))


def verify(public_key: Ed25519PublicKey, tag: bytes, payload: bytes, signature_b64: str) -> bool:
    """True only for a valid signature. Never raises on bad input."""
    try:
        raw = b64url_decode(signature_b64)
    except (binascii.Error, ValueError):
        return False
    if len(raw) != 64:
        return False
    try:
        public_key.verify(raw, tag + payload)
    except InvalidSignature:
        return False
    return True
