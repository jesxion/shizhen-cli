import json
import shutil
import tempfile
import unittest

from .fakeserver import FakeServer, FakeClock, run_cli

TOKEN = "sz_test_fake_token_value"

PARSED = {"platform": "douyin", "title": "测试视频 #话题 标题", "author": "作者", "duration": 12.5,
          "sourceUrl": "https://v.douyin.com/abc/", "contentId": "c1", "isImage": False,
          "qualities": [{"qualityId": "source", "label": "原画"}, {"qualityId": "derived-720", "label": "720P 压缩版"}]}


def job(state="queued", job_id="j1", kind="video", error=None, **extra):
    value = {"jobId": job_id, "kind": kind, "state": state, "stage": state, "qualityId": "source",
             "pollAfterSeconds": 3, "asset": None, "error": error}
    value.update(extra)
    return value


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer().start()
        self.tmp = tempfile.mkdtemp(prefix="shizhen-test-")
        self.cfg = self.tmp + "/cfg"
        self.out = self.tmp + "/out"
        self.env = {"SHIZHEN_API": self.server.url, "SHIZHEN_TOKEN": TOKEN, "SHIZHEN_CONFIG_DIR": self.cfg}
        self.clock = FakeClock()

    def tearDown(self):
        self.server.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv, stdin="", env=None):
        return run_cli(list(argv), env if env is not None else self.env, stdin, self.clock)

    def run_json(self, *argv, **kw):
        code, out, err = self.run_cli(*argv, "--json", **kw)
        return code, json.loads(out)

    def serve_media(self, payload=b"FAKEVIDEO", file_name="x.mp4", size=None, job_id="j1"):
        """让 job_id 对应的任务已完成，并可下载 payload。"""
        self.server.on("GET", "/api/media-jobs/" + job_id,
                       body=job("ready", job_id, asset={"fileName": file_name, "sizeBytes": len(payload)}))
        self.server.on("GET", "/api/media-jobs",
                       body={"items": [dict(job("ready", job_id), parseResult={"title": PARSED["title"]})]})
        self.server.on("POST", "/api/media-jobs/%s/download" % job_id, body={
            "mode": "miniapp", "downloadUrl": self.server.url + "/files/" + file_name,
            "fileName": file_name, "sizeBytes": size if size is not None else len(payload)})
        self.server.on("GET", "/files/" + file_name, status=200, body=payload)
