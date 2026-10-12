"""对拾帧服务的 HTTP 调用与文件下载（仅标准库）。"""
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import __version__
from .errors import CliError, EXIT_UNAVAILABLE, from_response

TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60


class Client:
    def __init__(self, base, token, timeout=TIMEOUT):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self):
        return {"Authorization": "Bearer " + self.token, "X-Shizhen-CLI": __version__,
                "User-Agent": "shizhen-cli/" + __version__, "Accept": "application/json"}

    def request(self, method, path, body=None, headers=None):
        data = None
        merged = self._headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            merged["Content-Type"] = "application/json"
        if headers:
            merged.update(headers)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=merged)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            try:
                parsed = json.loads(exc.read().decode("utf-8", "replace"))
            except ValueError:
                parsed = None
            raise from_response(exc.code, parsed)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            raise CliError(EXIT_UNAVAILABLE, "NETWORK_ERROR", "无法连接拾帧服务：%s" % _reason(exc), True)
        try:
            return status, (json.loads(raw.decode("utf-8")) if raw else {})
        except ValueError:
            raise CliError(EXIT_UNAVAILABLE, "BAD_RESPONSE", "服务返回了无法解析的内容。", True)

    def parse(self, text):
        return self.request("POST", "/api/parse", {"url": text})[1]

    def create_job(self, source_url, kind, quality_id, content_id=""):
        body = {"sourceUrl": source_url, "kind": kind, "qualityId": quality_id}
        if content_id:
            body["contentId"] = content_id
        return self.request("POST", "/api/media-jobs", body, {"Idempotency-Key": uuid.uuid4().hex})[1]

    def job(self, job_id):
        return self.request("GET", "/api/media-jobs/" + urllib.parse.quote(job_id, safe=""))[1]

    def jobs(self):
        return self.request("GET", "/api/media-jobs")[1]

    def grant(self, job_id):
        return self.request("POST", "/api/media-jobs/%s/download" % urllib.parse.quote(job_id, safe=""))[1]

    def usage(self):
        return self.request("GET", "/api/usage")[1]

    def fetch(self, url, dest_part, expected_size=None):
        """下载到 dest_part。只有地址与 API 同源时才带令牌。"""
        target = urllib.parse.urljoin(self.base + "/", url)
        headers = {"User-Agent": "shizhen-cli/" + __version__}
        if _origin(target) == _origin(self.base):
            headers.update(self._headers())
        req = urllib.request.Request(target, headers=headers)
        written = 0
        try:
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(dest_part, "wb") as out:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
        except urllib.error.HTTPError as exc:
            _drop(dest_part)
            code = "DOWNLOAD_EXPIRED" if exc.code in (403, 404, 410) else "DOWNLOAD_FAILED"
            raise CliError(2 if code == "DOWNLOAD_EXPIRED" else EXIT_UNAVAILABLE, code,
                           "下载地址不可用或已过期（HTTP %d），请重新申请。" % exc.code, code != "DOWNLOAD_EXPIRED")
        except (urllib.error.URLError, OSError, ConnectionError, socket.timeout) as exc:
            _drop(dest_part)
            raise CliError(EXIT_UNAVAILABLE, "NETWORK_ERROR", "下载中断：%s" % _reason(exc), True)
        except Exception:
            _drop(dest_part)
            raise
        if expected_size and written != expected_size:
            _drop(dest_part)
            raise CliError(EXIT_UNAVAILABLE, "DOWNLOAD_INCOMPLETE",
                           "下载不完整（%d / %d 字节）。" % (written, expected_size), True)
        return written


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme, parts.netloc.lower())


def _reason(exc):
    return str(getattr(exc, "reason", None) or exc)


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass
