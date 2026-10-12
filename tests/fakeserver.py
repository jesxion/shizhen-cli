"""本地假拾帧服务：按 (方法, 路径) 注册响应，记录收到的请求。"""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shizhen import cli


class Recorded:
    def __init__(self, method, path, headers, body):
        self.method, self.path, self.body = method, path, body
        self.headers = {k.lower(): v for k, v in headers.items()}

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else None


class FakeServer:
    def __init__(self):
        self.routes = {}
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                rec = Recorded(self.command, self.path, dict(self.headers), body)
                outer.requests.append(rec)
                route = outer.routes.get((self.command, self.path.split("?")[0]))
                if route is None:
                    status, payload, headers = 404, {"detail": "not found"}, {}
                else:
                    result = route(rec) if callable(route) else route
                    status, payload, headers = (tuple(result) + ({},))[:3]
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream" if isinstance(payload, bytes) else "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass

            do_GET = do_POST = do_DELETE = _handle

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)

    def on(self, method, path, status=200, body=None, headers=None, handler=None):
        self.routes[(method, path)] = handler or (lambda rec: (status, body if body is not None else {}, headers or {}))

    def count(self, method, path):
        return sum(1 for r in self.requests if r.method == method and r.path.split("?")[0] == path)


class FakeClock:
    """假时钟：sleep 只推进时间并记录间隔。"""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def run_cli(argv, env, stdin_text="", clock=None):
    out, err = io.StringIO(), io.StringIO()
    stdin = io.StringIO(stdin_text)
    kwargs = {}
    if clock is not None:
        kwargs = {"sleep": clock.sleep, "clock": clock.clock}
    code = cli.main(argv, env=env, stdin=stdin, stdout=out, stderr=err, **kwargs)
    return code, out.getvalue(), err.getvalue()
