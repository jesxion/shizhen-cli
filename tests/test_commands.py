import os

from shizhen import __version__
from .base import CliTestCase, PARSED, TOKEN, job


class ParseUsageTests(CliTestCase):
    def test_parse_json_and_headers(self):
        self.server.on("POST", "/api/parse", body=PARSED)
        code, data = self.run_json("parse", "看看 https://v.douyin.com/abc/ 复制")
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(data["platform"], "douyin")
        self.assertEqual(data["qualities"][0]["qualityId"], "source")
        rec = self.server.requests[0]
        self.assertEqual(rec.json(), {"url": "看看 https://v.douyin.com/abc/ 复制"})
        self.assertEqual(rec.headers["authorization"], "Bearer " + TOKEN)
        self.assertEqual(rec.headers["x-shizhen-cli"], __version__)

    def test_parse_human_output_is_chinese_text(self):
        self.server.on("POST", "/api/parse", body=PARSED)
        code, out, _ = self.run_cli("parse", "https://v.douyin.com/abc/")
        self.assertEqual(code, 0)
        self.assertIn("标题", out)
        self.assertFalse(out.lstrip().startswith("{"))

    def test_json_stdout_is_single_object(self):
        self.server.on("POST", "/api/parse", body=PARSED)
        code, out, err = self.run_cli("parse", "u", "--json")
        self.assertEqual(out.count("\n"), 1)
        self.assertNotIn(TOKEN, out + err)

    def test_usage_computes_used(self):
        self.server.on("GET", "/api/usage", body={"limited": True, "dailyLimit": 5, "remaining": 2, "resetAt": "2026-10-13T00:00:00+08:00"})
        code, data = self.run_json("usage")
        self.assertEqual(code, 0)
        self.assertEqual(data["used"], 3)
        self.assertEqual(data["remaining"], 2)
        self.assertEqual(data["resetAt"], "2026-10-13T00:00:00+08:00")

    def test_usage_unlimited(self):
        self.server.on("GET", "/api/usage", body={"limited": False})
        code, data = self.run_json("usage")
        self.assertEqual(code, 0)
        self.assertFalse(data["limited"])


class JobsTests(CliTestCase):
    def test_jobs_list(self):
        self.server.on("GET", "/api/media-jobs", body={"items": [dict(job("ready"), parseResult={"title": "甲"})]})
        code, data = self.run_json("jobs")
        self.assertEqual(code, 0)
        self.assertEqual(data["jobs"][0]["jobId"], "j1")
        self.assertEqual(data["jobs"][0]["title"], "甲")

    def test_single_job(self):
        self.server.on("GET", "/api/media-jobs/j9", body=job("processing", "j9"))
        code, data = self.run_json("jobs", "j9")
        self.assertEqual((code, data["state"]), (0, "processing"))


class ExtractTests(CliTestCase):
    def setUp(self):
        super().setUp()
        self.server.on("POST", "/api/parse", body=PARSED)

    def test_extract_video_end_to_end(self):
        self.server.on("POST", "/api/media-jobs", status=202, body=job("queued"))
        states = iter([job("processing"), job("ready", asset={"fileName": "x.mp4", "sizeBytes": 9})])
        self.serve_media()
        self.server.on("GET", "/api/media-jobs/j1", handler=lambda r: (200, next(states)))
        code, data = self.run_json("extract", "https://v.douyin.com/abc/", "-o", self.out)
        self.assertEqual(code, 0, data)
        self.assertEqual(data["fileName"], "测试视频 标题.mp4")
        with open(os.path.join(self.out, "测试视频 标题.mp4"), "rb") as handle:
            self.assertEqual(handle.read(), b"FAKEVIDEO")
        self.assertEqual(self.clock.sleeps, [3, 3])
        created = [r for r in self.server.requests if r.method == "POST" and r.path == "/api/media-jobs"][0].json()
        self.assertEqual(created["kind"], "video")
        self.assertEqual(created["qualityId"], "source")
        self.assertEqual(created["sourceUrl"], PARSED["sourceUrl"])
        self.assertEqual([f for f in os.listdir(self.out) if f.endswith(".part")], [])

    def test_extract_audio_with_quality_names_file(self):
        self.server.on("POST", "/api/media-jobs", status=201, body=job("ready", kind="audio"))
        self.serve_media(b"AUDIO", "x.m4a")
        code, data = self.run_json("extract", "u", "--audio", "--quality", "derived-720", "-o", self.out)
        self.assertEqual(code, 0, data)
        self.assertEqual(data["fileName"], "测试视频 标题-音频.m4a")
        created = [r for r in self.server.requests if r.path == "/api/media-jobs" and r.method == "POST"][0].json()
        self.assertEqual((created["kind"], created["qualityId"]), ("audio", "derived-720"))

    def test_no_wait_returns_job_id(self):
        self.server.on("POST", "/api/media-jobs", status=202, body=job("queued", "jx"))
        code, data = self.run_json("extract", "u", "--no-wait")
        self.assertEqual((code, data["jobId"], data["state"]), (0, "jx", "queued"))
        self.assertEqual(self.clock.sleeps, [])

    def test_image_album_rejected(self):
        self.server.on("POST", "/api/parse", body=dict(PARSED, isImage=True))
        code, data = self.run_json("extract", "u")
        self.assertEqual((code, data["code"]), (2, "IMAGE_NOT_SUPPORTED"))

    def test_protected_audio_is_refused_without_creating_a_job(self):
        parsed = dict(PARSED, platform="suno", capabilities={
            "video": {"supported": False}, "audio": {"supported": False, "reasonCode": "AUTHORIZED_EXPORT_REQUIRED"}})
        self.server.on("POST", "/api/parse", body=parsed)
        code, data = self.run_json("extract", "u", "--audio")
        self.assertEqual((code, data["code"]), (2, "AUTHORIZED_EXPORT_REQUIRED"))
        self.assertIn("小程序", data["message"])
        self.assertEqual(self.server.count("POST", "/api/media-jobs"), 0)

    def test_server_side_protected_audio_conflict_gets_the_same_hint(self):
        self.server.on("POST", "/api/parse", body=PARSED)  # an older parse result without capabilities
        self.server.on("POST", "/api/media-jobs", status=409, body={"detail": {
            "code": "AUTHORIZED_EXPORT_REQUIRED", "message": "该音频需要平台授权的导出地址。", "retryable": True}})
        code, data = self.run_json("extract", "u", "--audio")
        self.assertEqual((code, data["code"], data["retryable"]), (2, "AUTHORIZED_EXPORT_REQUIRED", False))
        self.assertIn("小程序", data["message"])

    def test_unsupported_without_a_reason_code_is_left_to_the_server(self):
        parsed = dict(PARSED, capabilities={"video": {"supported": False}})
        self.server.on("POST", "/api/parse", body=parsed)
        self.server.on("POST", "/api/media-jobs", body=job("queued"))
        self.server.on("GET", "/api/media-jobs/j1", body=job("failed", error={
            "code": "NO_VIDEO", "message": "x", "retryable": False}))
        code, _ = self.run_json("extract", "u", "--no-wait")
        self.assertEqual(code, 0)
        self.assertEqual(self.server.count("POST", "/api/media-jobs"), 1)

    def test_job_failed_not_retryable_is_exit_2(self):
        self.server.on("POST", "/api/media-jobs", status=202, body=job("queued"))
        self.server.on("GET", "/api/media-jobs/j1", body=job(
            "failed", error={"code": "NO_AUDIO_TRACK", "message": "没有音轨", "retryable": False}))
        code, data = self.run_json("extract", "u", "--audio")
        self.assertEqual((code, data["code"], data["jobId"]), (2, "NO_AUDIO_TRACK", "j1"))

    def test_job_failed_retryable_is_exit_5(self):
        self.server.on("POST", "/api/media-jobs", status=202, body=job("queued"))
        self.server.on("GET", "/api/media-jobs/j1", body=job(
            "failed", error={"code": "SOURCE_FETCH", "message": "取流失败", "retryable": True}))
        code, data = self.run_json("extract", "u")
        self.assertEqual((code, data["retryable"]), (5, True))


class DownloadTests(CliTestCase):
    def test_download_ready_job(self):
        self.serve_media()
        code, data = self.run_json("download", "j1", "-o", self.out)
        self.assertEqual(code, 0, data)
        self.assertEqual(data["fileName"], "测试视频 标题.mp4")
        self.assertEqual(data["sizeBytes"], 9)

    def test_download_not_ready_is_exit_5(self):
        self.server.on("GET", "/api/media-jobs/j1", body=job("processing"))
        code, data = self.run_json("download", "j1", "-o", self.out)
        self.assertEqual((code, data["code"]), (5, "JOB_NOT_READY"))

    def test_download_expired_job_is_exit_2(self):
        self.server.on("GET", "/api/media-jobs/j1", body=job("expired"))
        code, data = self.run_json("download", "j1", "-o", self.out)
        self.assertEqual(code, 2)

    def test_external_download_url_relative_and_token_sent(self):
        self.server.on("GET", "/api/media-jobs/j1", body=job("ready"))
        self.server.on("GET", "/api/media-jobs", body={"items": []})
        self.server.on("POST", "/api/media-jobs/j1/download", body={
            "mode": "external", "externalDownloadUrl": "/api/media-download/tok", "fileName": "视频.mp4", "sizeBytes": 3})
        self.server.on("GET", "/api/media-download/tok", body=b"abc")
        code, data = self.run_json("download", "j1", "-o", self.out)
        self.assertEqual(code, 0, data)
        self.assertEqual(data["fileName"], "视频.mp4")  # 无标题时退回服务端文件名

    def test_token_not_sent_to_other_origin(self):
        other = type(self.server)().start()
        try:
            other.on("GET", "/f.mp4", body=b"zzz")
            self.server.on("GET", "/api/media-jobs/j1", body=job("ready"))
            self.server.on("GET", "/api/media-jobs", body={"items": []})
            self.server.on("POST", "/api/media-jobs/j1/download", body={
                "downloadUrl": other.url + "/f.mp4", "fileName": "f.mp4", "sizeBytes": 3})
            code, data = self.run_json("download", "j1", "-o", self.out)
            self.assertEqual(code, 0, data)
            headers = other.requests[0].headers
            self.assertNotIn("authorization", headers)
            self.assertNotIn("x-shizhen-cli", headers)
        finally:
            other.stop()

    def test_incomplete_download_leaves_no_files(self):
        self.serve_media(b"abc", size=10)
        code, data = self.run_json("download", "j1", "-o", self.out)
        self.assertEqual((code, data["code"]), (5, "DOWNLOAD_INCOMPLETE"))
        self.assertEqual(os.listdir(self.out), [])

    def test_expired_link_leaves_no_files(self):
        self.serve_media()
        self.server.on("GET", "/files/x.mp4", status=403, body={"detail": "expired"})
        code, data = self.run_json("download", "j1", "-o", self.out)
        self.assertEqual((code, data["code"]), (2, "DOWNLOAD_EXPIRED"))
        self.assertEqual(os.listdir(self.out), [])
