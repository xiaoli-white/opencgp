from __future__ import annotations

import datetime
import hashlib
import hmac
from typing import Any, Optional
from urllib.parse import quote, urlparse

import httpx

from app.ports.storage import StorageBackend

EMPTY_PAYLOAD_HASH = hashlib.sha256(b"").hexdigest()
UNRESERVED = "-_.~"


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        prefix: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region or "us-east-1"
        self.prefix = prefix.strip("/")
        self.timeout = timeout
        parsed = urlparse(self.endpoint)
        self.host = parsed.netloc or parsed.path
        self._bucket_ready = False
        self.last_error = ""

    def _encode_path(self, path: str) -> str:
        return "/".join(quote(part, safe=UNRESERVED) for part in path.split("/"))

    def _encode_query(self, params: dict[str, Any] | None) -> str:
        if not params:
            return ""
        items = sorted((str(k), str(v)) for k, v in params.items())
        return "&".join(
            f"{quote(k, safe=UNRESERVED)}={quote(v, safe=UNRESERVED)}" for k, v in items
        )

    def _sign(
        self, method: str, path: str, query: str, body: bytes, headers: dict[str, str] | None = None
    ) -> dict[str, str]:
        now = datetime.datetime.now(datetime.timezone.utc)
        amzdate = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        extra = dict(headers or {})
        base = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amzdate,
        }
        for key, value in extra.items():
            base[key.lower()] = value
        signed_headers = ";".join(sorted(base))
        canonical_headers = "".join(f"{k}:{base[k].strip()}\n" for k in sorted(base))
        creq = "\n".join([method, path, query, canonical_headers, signed_headers, payload_hash])
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        sts = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amzdate,
                scope,
                hashlib.sha256(creq.encode()).hexdigest(),
            ]
        )
        key = ("AWS4" + self.secret_key).encode()
        for part in (datestamp, self.region, "s3", "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        signature = hmac.new(key, sts.encode(), hashlib.sha256).hexdigest()
        out = dict(base)
        out["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return out

    def _request(
        self,
        method: str,
        key: str = "",
        query: dict[str, Any] | None = None,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        bucket_level: bool = False,
    ) -> httpx.Response:
        path = f"/{self.bucket}" if bucket_level else f"/{self.bucket}/{key.lstrip('/')}"
        if bucket_level and key:
            path = f"/{self.bucket}/{key.lstrip('/')}"
        encoded_path = self._encode_path(path)
        encoded_query = self._encode_query(query)
        signed = self._sign(method, encoded_path, encoded_query, body, headers)
        signed.pop("host", None)
        url = f"{self.endpoint}{encoded_path}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        with httpx.Client(timeout=self.timeout) as client:
            return client.request(
                method, url, content=body if body else None, headers=signed
            )

    def ensure_bucket(self) -> bool:
        if self._bucket_ready:
            return True
        try:
            resp = self._request("PUT", bucket_level=True)
            if resp.status_code in (200, 201, 403, 409):
                self._bucket_ready = True
                return True
            self.last_error = f"建桶失败 {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            self.last_error = f"建桶异常: {exc!r}"
        return False

    def object_key(self, tenant_id: str, source_id: str, filename: str) -> str:
        tenant = (tenant_id or "tenant_default").strip() or "tenant_default"
        name = (filename or "upload.bin").strip().replace("/", "_") or "upload.bin"
        parts = [part for part in (self.prefix, tenant, source_id, name) if part]
        return "/".join(parts)

    def put(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        self.ensure_bucket()
        headers = {"content-type": content_type or "application/octet-stream"}
        resp = self._request("PUT", key=key, body=data, headers=headers)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"S3 put 失败 {resp.status_code}: {resp.text[:200]}")
        return key

    def get(self, key: str) -> bytes:
        resp = self._request("GET", key=key)
        if resp.status_code == 404:
            raise FileNotFoundError(key)
        if resp.status_code != 200:
            raise RuntimeError(f"S3 get 失败 {resp.status_code}: {resp.text[:200]}")
        return resp.content

    def delete(self, key: str) -> None:
        resp = self._request("DELETE", key=key)
        if resp.status_code not in (200, 204, 404):
            raise RuntimeError(f"S3 delete 失败 {resp.status_code}: {resp.text[:200]}")

    def exists(self, key: str) -> bool:
        resp = self._request("HEAD", key=key)
        return resp.status_code == 200

    def list_objects(self, prefix: str = "", limit: int = 1000) -> list[str]:
        self.ensure_bucket()
        query: dict[str, Any] = {"list-type": "2", "max-keys": str(limit)}
        if prefix:
            query["prefix"] = prefix
        resp = self._request("GET", bucket_level=True, query=query)
        if resp.status_code != 200:
            raise RuntimeError(f"S3 list 失败 {resp.status_code}: {resp.text[:200]}")
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(resp.text)
        except Exception:
            return []
        keys: list[str] = []
        for element in root.iter():
            tag = element.tag.split("}")[-1]
            if tag == "Key" and element.text:
                keys.append(element.text)
        return keys

    def count_objects(self, prefix: str = "") -> int:
        return len(self.list_objects(prefix))

    def healthcheck(self) -> bool:
        try:
            resp = self._request("HEAD", bucket_level=True)
            if resp.status_code == 200:
                self._bucket_ready = True
                return True
            if resp.status_code == 404:
                if self.ensure_bucket():
                    ok = self._request("HEAD", bucket_level=True).status_code == 200
                    if not ok:
                        self.last_error = "桶创建后 HEAD 仍失败"
                    return ok
            self.last_error = f"HEAD bucket {resp.status_code}: {resp.text[:200]}"
            return False
        except Exception as exc:
            self.last_error = f"探活异常: {exc!r}"
            return False
