import json
import os
import stat
import unittest

from shizhen import config
from .base import CliTestCase, TOKEN

OTHER = "sz_from_config_file"


class TokenTests(CliTestCase):
    def write_config(self, token):
        os.makedirs(self.cfg, exist_ok=True)
        with open(os.path.join(self.cfg, "config.json"), "w", encoding="utf-8") as handle:
            json.dump({"token": token}, handle)

    def auth_of_last(self):
        return self.server.requests[-1].headers["authorization"]

    def test_env_wins_over_config(self):
        self.write_config(OTHER)
        self.server.on("GET", "/api/usage", body={"limited": False})
        self.run_cli("usage")
        self.assertEqual(self.auth_of_last(), "Bearer " + TOKEN)

    def test_config_used_when_no_env(self):
        self.write_config(OTHER)
        env = {k: v for k, v in self.env.items() if k != "SHIZHEN_TOKEN"}
        self.server.on("GET", "/api/usage", body={"limited": False})
        self.assertEqual(self.run_cli("usage", env=env)[0], 0)
        self.assertEqual(self.auth_of_last(), "Bearer " + OTHER)

    def test_empty_env_falls_back_to_config(self):
        self.write_config(OTHER)
        env = dict(self.env, SHIZHEN_TOKEN="  ")
        self.server.on("GET", "/api/usage", body={"limited": False})
        self.run_cli("usage", env=env)
        self.assertEqual(self.auth_of_last(), "Bearer " + OTHER)

    def test_login_reads_stdin_validates_and_saves(self):
        env = {k: v for k, v in self.env.items() if k != "SHIZHEN_TOKEN"}
        self.server.on("GET", "/api/usage", body={"limited": False})
        code, out, err = self.run_cli("login", stdin=OTHER + "\n", env=env)
        self.assertEqual(code, 0)
        self.assertEqual(config.load_token(env), OTHER)
        self.assertEqual(self.auth_of_last(), "Bearer " + OTHER)
        self.assertNotIn(OTHER, out + err)
        if os.name != "nt":
            mode = stat.S_IMODE(os.stat(os.path.join(self.cfg, "config.json")).st_mode)
            self.assertEqual(mode, 0o600)

    def test_login_ignores_env_token(self):
        # login 保存的是 stdin 里的令牌，而不是环境变量里的
        self.server.on("GET", "/api/usage", body={"limited": False})
        self.run_cli("login", stdin=OTHER + "\n")
        self.assertEqual(self.auth_of_last(), "Bearer " + OTHER)
        self.assertEqual(config.load_token({"SHIZHEN_CONFIG_DIR": self.cfg}), OTHER)

    def test_login_rejected_token_not_saved(self):
        env = {k: v for k, v in self.env.items() if k != "SHIZHEN_TOKEN"}
        self.server.on("GET", "/api/usage", status=401, body={"detail": "nope"})
        code, _, _ = self.run_cli("login", stdin="sz_bad\n", env=env)
        self.assertEqual(code, 4)
        self.assertIsNone(config.load_token(env))

    def test_login_empty_stdin_is_exit_2(self):
        self.assertEqual(self.run_cli("login", stdin="")[0], 2)

    def test_logout_removes_file(self):
        self.write_config(OTHER)
        code, data = self.run_json("logout")
        self.assertEqual((code, data["removed"]), (0, True))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, "config.json")))
        code, data = self.run_json("logout")
        self.assertEqual((code, data["removed"]), (0, False))

    def test_default_config_paths(self):
        unix = config.config_path({"HOME": "/h"})
        if os.name == "nt":
            self.assertTrue(config.config_path({"APPDATA": "C:\\A"}).startswith("C:\\A"))
            self.assertTrue(config.config_path({"APPDATA": "C:\\A"}).endswith(os.path.join("shizhen", "config.json")))
        else:
            self.assertTrue(unix.endswith(os.path.join(".config", "shizhen", "config.json")))

    def test_api_base_override_and_default(self):
        self.assertEqual(config.api_base({}), "https://jesxion.com")
        self.assertEqual(config.api_base({"SHIZHEN_API": "http://x:1/"}), "http://x:1")

    def test_token_never_printed_on_error(self):
        self.server.on("GET", "/api/usage", status=401, body={"detail": TOKEN})
        code, out, err = self.run_cli("usage", "--json")
        self.assertEqual(code, 4)
        self.assertNotIn(TOKEN, out + err)


if __name__ == "__main__":
    unittest.main()
