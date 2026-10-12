import os
import shutil
import tempfile
import unittest

from shizhen import naming
from .base import CliTestCase


class NamingTests(unittest.TestCase):
    def test_hashtags_and_illegal_chars_removed(self):
        self.assertEqual(naming.clean_title('好看的 #美食 #探店 视频: a/b?"c"'), "好看的 视频 a b c")

    def test_truncate_to_30_code_points(self):
        title = "字" * 40
        self.assertEqual(naming.clean_title(title), "字" * 30)
        emoji = "😀" * 31
        self.assertEqual(naming.clean_title(emoji), "😀" * 30)

    def test_fallback_and_audio_suffix(self):
        self.assertEqual(naming.file_name("", "video", ".mp4"), "拾帧.mp4")
        self.assertEqual(naming.file_name("#tag", "audio", ".m4a"), "拾帧-音频.m4a")
        self.assertEqual(naming.file_name("标题", "audio", ".m4a"), "标题-音频.m4a")
        self.assertEqual(naming.file_name("标题", "video", ".mp4"), "标题.mp4")

    def test_unique_path_increments(self):
        d = tempfile.mkdtemp()
        try:
            first = naming.unique_path(d, "a.mp4")
            self.assertEqual(os.path.basename(first), "a.mp4")
            open(first, "w").close()
            second = naming.unique_path(d, "a.mp4")
            self.assertEqual(os.path.basename(second), "a (2).mp4")
            open(second, "w").close()
            self.assertEqual(os.path.basename(naming.unique_path(d, "a.mp4")), "a (3).mp4")
        finally:
            shutil.rmtree(d)


class DownloadNamingTests(CliTestCase):
    def test_same_name_not_overwritten(self):
        self.serve_media()
        names = []
        for _ in range(3):
            code, out, _ = self.run_cli("download", "j1", "-o", self.out, "--json")
            self.assertEqual(code, 0)
            import json
            names.append(json.loads(out)["fileName"])
        self.assertEqual(names, ["测试视频 标题.mp4", "测试视频 标题 (2).mp4", "测试视频 标题 (3).mp4"])
        self.assertEqual(len(os.listdir(self.out)), 3)

    def test_part_file_used_then_renamed(self):
        seen = []
        payload = b"data"

        def handler(rec):
            seen.append(sorted(os.listdir(self.out)) if os.path.isdir(self.out) else [])
            return 200, payload

        self.serve_media(payload)
        self.server.on("GET", "/files/x.mp4", handler=handler)
        code, out, _ = self.run_cli("download", "j1", "-o", self.out, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(os.listdir(self.out)), ["测试视频 标题.mp4"])
        self.assertTrue(all(not n.endswith(".mp4") for n in seen[0]))  # 下载过程中还没有最终文件

    def test_output_dir_created(self):
        self.serve_media()
        nested = os.path.join(self.out, "a", "b")
        code, _, _ = self.run_cli("download", "j1", "-o", nested, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(os.listdir(nested)), 1)
