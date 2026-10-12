import socket
import unittest

from shizhen.errors import exit_code_for
from .base import CliTestCase, PARSED, job


def err(code, message="消息", retryable=False, **extra):
    return {"detail": dict({"code": code, "message": message, "retryable": retryable}, **extra)}


class ExitCodeMapping(unittest.TestCase):
    def test_table(self):
        cases = [
            (400, "", False, 2), (404, "JOB_NOT_FOUND", False, 2), (403, "CONTENT_REJECTED", False, 2),
            (409, "SUBTITLE_WITHDRAWN", False, 2), (422, "", False, 2),
            (429, "DAILY_PROCESSING", False, 3), (429, "TOKEN_RATE_LIMIT", False, 3),
            (503, "SERVICE_BUDGET_PAUSED", False, 3), (0, "DAILY_PARSE", False, 3),
            (401, "", False, 4), (403, "TOKEN_SCOPE", False, 4), (401, "TOKEN_EXPIRED", False, 4),
            (502, "", True, 5), (503, "", True, 5), (503, "TOKEN_QUOTA_UNAVAILABLE", True, 5),
            (504, "", True, 5), (0, "SOURCE_FETCH", True, 5), (409, "JOB_NOT_READY", True, 5),
            (426, "CLI_TOO_OLD", False, 6),
        ]
        for status, code, retryable, expected in cases:
            self.assertEqual(exit_code_for(status, code, retryable), expected, (status, code))


class ExitCodesOverHttp(CliTestCase):
    def check(self, status, body, expected, code=None, route=("POST", "/api/parse"), argv=("parse", "u")):
        self.server.on(route[0], route[1], status=status, body=body)
        got, data = self.run_json(*argv)
        self.assertEqual(got, expected, data)
        self.assertFalse(data["ok"])
        if code:
            self.assertEqual(data["code"], code)
        return data

    def test_success_is_0(self):
        self.server.on("POST", "/api/parse", body=PARSED)
        self.assertEqual(self.run_json("parse", "u")[0], 0)

    def test_input_errors_are_2(self):
        self.check(400, {"detail": "暂不支持该平台"}, 2)
        self.check(409, err("SUBTITLE_WITHDRAWN"), 2, "SUBTITLE_WITHDRAWN")

    def test_quota_is_3_and_carries_reset(self):
        data = self.check(429, err("DAILY_PROCESSING", "今日额度已用完", False, resetAt="2026-10-13T00:00:00+08:00"),
                          3, "DAILY_PROCESSING")
        self.assertEqual(data["resetAt"], "2026-10-13T00:00:00+08:00")
        self.assertEqual(data["message"], "今日额度已用完")
        self.assertIs(data["retryable"], False)
        self.check(503, err("SERVICE_BUDGET_PAUSED"), 3)
        self.check(429, err("TOKEN_RATE_LIMIT"), 3)

    def test_auth_is_4(self):
        self.check(401, {"detail": "unauthorized"}, 4, "TOKEN_INVALID")
        self.check(403, err("TOKEN_SCOPE"), 4, "TOKEN_SCOPE")

    def test_server_contract_codes(self):
        self.check(401, err("TOKEN_DISABLED", "令牌功能未开启"), 4, "TOKEN_DISABLED")
        self.check(401, err("TOKEN_INVALID", "无效"), 4, "TOKEN_INVALID")
        data = self.check(429, err("TOKEN_RATE_LIMIT", "太快", False, resetAt="2026-10-12T10:01:00+08:00"), 3)
        self.assertEqual(data["resetAt"], "2026-10-12T10:01:00+08:00")

    def test_unavailable_is_5(self):
        self.check(502, {"detail": "解析服务暂时不可用"}, 5)
        self.check(503, err("TOKEN_QUOTA_UNAVAILABLE", retryable=True), 5)
        self.check(504, {}, 5)

    def test_old_cli_is_6(self):
        self.check(426, err("CLI_TOO_OLD", "请升级"), 6, "CLI_TOO_OLD")
        self.check(426, {"detail": "请升级"}, 6, "CLI_TOO_OLD")

    def test_missing_token_is_4(self):
        env = {k: v for k, v in self.env.items() if k != "SHIZHEN_TOKEN"}
        code, out, err_text = self.run_cli("usage", "--json", env=env)
        self.assertEqual(code, 4)

    def test_connection_refused_is_5(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        env = dict(self.env, SHIZHEN_API="http://127.0.0.1:%d" % port)
        code, out, _ = self.run_cli("usage", "--json", env=env)
        self.assertEqual(code, 5)

    def test_argparse_errors_are_2(self):
        self.assertEqual(self.run_cli("parse")[0], 2)
        self.assertEqual(self.run_cli("nosuchcommand")[0], 2)
        self.assertEqual(self.run_cli("login", "sz_secret")[0], 2)  # login 不接受命令行参数

    def test_human_mode_errors_go_to_stderr(self):
        self.server.on("POST", "/api/parse", status=429, body=err("DAILY_PROCESSING", "今日额度已用完", resetAt="R"))
        code, out, errtext = self.run_cli("parse", "u")
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertIn("今日额度已用完", errtext)
        self.assertIn("R", errtext)

    def test_timeout_is_5(self):
        # 服务端不响应：把客户端超时改小
        from shizhen import api
        old = api.TIMEOUT
        import threading
        release = threading.Event()
        self.server.on("GET", "/api/usage", handler=lambda r: (release.wait(1.5), (200, {}))[1])
        orig = api.Client.__init__

        def patched(self_, base, token, timeout=0.3):
            orig(self_, base, token, timeout)

        api.Client.__init__ = patched
        try:
            code, data = self.run_json("usage")
        finally:
            api.Client.__init__ = orig
            release.set()
        self.assertEqual((code, data["code"]), (5, "NETWORK_ERROR"))
