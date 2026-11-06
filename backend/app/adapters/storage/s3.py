from __future__ import annotations

import datetime
import hashlib
import hmac
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import quote, urlparse

import httpx

from app.ports.storage import StorageBackend

EMPTY_PAYLOAD_HASH = hashlib.sha256(b"").hexdigest()
UNRESERVED = "-_.~"
RETRY_DELAYS = (0.2, 0.5, 1.2)
RETRYABLE_STATUS = 500
MULTIPART_THRESHOLD = 8 * 1024 * 1024
PART_SIZE = 8 * 1024 * 1024


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
        self.retries = 0
        self.multipart_threshold = MULTIPART_THRESHOLD
        self.part_size = PART_SIZE

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
        attempt = 0
        while True:
            try:
                resp = self._send(method, key, query, body, headers, bucket_level)
            except httpx.HTTPError as exc:
                self.last_error = f"{method} network error: {exc!r}"
                if attempt >= len(RETRY_DELAYS):
                    raise
                delay = RETRY_DELAYS[attempt]
                attempt += 1
                self.retries += 1
                print(
                    f"[s3] {method} {key or self.bucket} network error, retry {attempt} ({delay}s): {exc!r}"
                )
                time.sleep(delay)
                continue
            if resp.status_code < RETRYABLE_STATUS:
                return resp
            self.last_error = f"{method} {resp.status_code}: {resp.text[:200]}"
            if attempt >= len(RETRY_DELAYS):
                return resp
            delay = RETRY_DELAYS[attempt]
            attempt += 1
            self.retries += 1
            print(
                f"[s3] {method} {key or self.bucket} returned {resp.status_code}, "
                f"retry {attempt} ({delay}s)"
            )
            time.sleep(delay)

    def _send(
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
            self.last_error = f"bucket creation failed {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            self.last_error = f"bucket creation error: {exc!r}"
        return False

    def object_key(self, tenant_id: str, source_id: str, filename: str) -> str:
        tenant = (tenant_id or "tenant_default").strip() or "tenant_default"
        name = (filename or "upload.bin").strip().replace("/", "_") or "upload.bin"
        parts = [part for part in (self.prefix, tenant, source_id, name) if part]
        return "/".join(parts)

    def put(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        self.ensure_bucket()
        if len(data) > self.multipart_threshold:
            return self._put_multipart(key, data, content_type)
        headers = {"content-type": content_type or "application/octet-stream"}
        resp = self._request("PUT", key=key, body=data, headers=headers)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"S3 put failed {resp.status_code}: {resp.text[:200]}")
        return key

    def _put_multipart(
        self, key: str, data: bytes, content_type: Optional[str] = None
    ) -> str:
        upload_id = self.create_multipart_upload(key, content_type)
        parts: list[tuple[int, str]] = []
        try:
            number = 1
            for offset in range(0, len(data), self.part_size):
                chunk = data[offset : offset + self.part_size]
                parts.append((number, self.upload_part(key, upload_id, number, chunk)))
                number += 1
            self.complete_multipart_upload(key, upload_id, parts)
        except Exception:
            self.abort_multipart_upload(key, upload_id)
            raise
        return key

    def create_multipart_upload(
        self, key: str, content_type: Optional[str] = None
    ) -> str:
        headers = {"content-type": content_type or "application/octet-stream"}
        resp = self._request(
            "POST", key=key, query={"uploads": ""}, headers=headers
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"S3 multipart init failed {resp.status_code}: {resp.text[:200]}"
            )
        try:
            root = ET.fromstring(resp.text)
        except Exception as exc:
            raise RuntimeError(f"cannot parse S3 multipart response: {exc!r}") from exc
        for element in root.iter():
            if element.tag.split("}")[-1] == "UploadId" and element.text:
                return element.text
        raise RuntimeError("S3 multipart did not return an UploadId")

    def upload_part(
        self, key: str, upload_id: str, part_number: int, body: bytes
    ) -> str:
        resp = self._request(
            "PUT",
            key=key,
            query={"partNumber": int(part_number), "uploadId": upload_id},
            body=body,
            headers={"content-type": "application/octet-stream"},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"S3 upload_part failed {resp.status_code}: {resp.text[:200]}"
            )
        return (resp.headers.get("etag") or "").strip('"')

    def complete_multipart_upload(
        self, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> None:
        body = ["<CompleteMultipartUpload>"]
        for number, etag in parts:
            body.append(
                f"<Part><PartNumber>{number}</PartNumber><ETag>\"{etag}\"</ETag></Part>"
            )
        body.append("</CompleteMultipartUpload>")
        payload = "".join(body).encode()
        resp = self._request(
            "POST",
            key=key,
            query={"uploadId": upload_id},
            body=payload,
            headers={"content-type": "application/xml"},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"S3 multipart completion failed {resp.status_code}: {resp.text[:200]}"
            )

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        try:
            self._request(
                "DELETE", key=key, query={"uploadId": upload_id}
            )
        except Exception as exc:
            print(f"[s3] multipart abort failed {key}: {exc!r}")

    def get(self, key: str) -> bytes:
        resp = self._request("GET", key=key)
        if resp.status_code == 404:
            raise FileNotFoundError(key)
        if resp.status_code != 200:
            raise RuntimeError(f"S3 get failed {resp.status_code}: {resp.text[:200]}")
        return resp.content

    def delete(self, key: str) -> None:
        resp = self._request("DELETE", key=key)
        if resp.status_code not in (200, 204, 404):
            raise RuntimeError(f"S3 delete failed {resp.status_code}: {resp.text[:200]}")

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
            raise RuntimeError(f"S3 list failed {resp.status_code}: {resp.text[:200]}")
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
                        self.last_error = "HEAD still fails after bucket creation"
                    return ok
            self.last_error = f"HEAD bucket {resp.status_code}: {resp.text[:200]}"
            return False
        except Exception as exc:
            self.last_error = f"health check error: {exc!r}"
            return False
