from __future__ import annotations

import base64
import hashlib
import hmac
import os

TOKEN_PREFIX = "v1"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _keystream(secret: str, nonce: bytes, length: int) -> bytes:
    key = (secret or "").encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(
            key, nonce + counter.to_bytes(8, "big"), hashlib.sha256
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(left ^ right for left, right in zip(data, stream))


def _tag(secret: str, nonce: bytes, cipher: bytes) -> str:
    key = (secret or "").encode("utf-8")
    return _b64encode(hmac.new(key, nonce + cipher, hashlib.sha256).digest())


def encrypt_text(plain: str, secret: str) -> str:
    if not plain:
        return ""
    nonce = os.urandom(16)
    data = plain.encode("utf-8")
    cipher = _xor(data, _keystream(secret, nonce, len(data)))
    return f"{TOKEN_PREFIX}:{_b64encode(nonce)}:{_b64encode(cipher)}:{_tag(secret, nonce, cipher)}"


def decrypt_text(token: str, secret: str) -> str:
    if not token:
        return ""
    parts = (token or "").split(":")
    if len(parts) not in (3, 4) or parts[0] != TOKEN_PREFIX:
        return ""
    try:
        nonce = _b64decode(parts[1])
        cipher = _b64decode(parts[2])
    except (ValueError, TypeError):
        return ""
    if len(parts) == 4 and not hmac.compare_digest(parts[3], _tag(secret, nonce, cipher)):
        return ""
    plain = _xor(cipher, _keystream(secret, nonce, len(cipher)))
    text = plain.decode("utf-8", errors="replace")
    if "\ufffd" in text:
        return ""
    return text


def mask_secret(secret: str) -> str:
    text = secret or ""
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"
