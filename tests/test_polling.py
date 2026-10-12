import itertools

from shizhen.cli import POLL_SCHEDULE, poll_delay
from .base import CliTestCase, PARSED, job


class PollingTests(CliTestCase):
    def setUp(self):
        super().setUp()
        self.server.on("POST", "/api/parse", body=PARSED)
        self.server.on("POST", "/api/media-jobs", status=202, body=job("queued"))

    def test_schedule_starts_at_3_and_caps_at_15(self):
        delays = [poll_delay(i) for i in range(30)]
        self.assertEqual(delays[0], 3)
        self.assertEqual(max(delays), 15)
        self.assertEqual(delays[-1], 15)
        self.assertEqual(delays, sorted(delays))
        self.assertEqual(POLL_SCHEDULE[-1], 15)

    def test_timeout_exits_5_with_job_id_and_never_cancels(self):
        self.server.on("GET", "/api/media-jobs/j1", body=job("processing"))
        code, data = self.run_json("extract", "u", "--timeout", "60")
        self.assertEqual(code, 5)
        self.assertEqual(data["code"], "WAIT_TIMEOUT")
        self.assertEqual(data["jobId"], "j1")
        self.assertTrue(data["retryable"])
        self.assertGreaterEqual(sum(self.clock.sleeps), 60)
        self.assertLess(sum(self.clock.sleeps), 60 + 15)
        self.assertEqual(self.clock.sleeps[:3], [3, 3, 3])
        self.assertEqual(max(self.clock.sleeps), 15)
        self.assertEqual(self.server.count("POST", "/api/media-jobs/j1/cancel"), 0)

    def test_default_timeout_is_600(self):
        self.server.on("GET", "/api/media-jobs/j1", body=job("queued"))
        code, data = self.run_json("extract", "u")
        self.assertEqual(code, 5)
        total = sum(self.clock.sleeps)
        self.assertTrue(600 <= total < 615, total)

    def test_ready_immediately_does_not_sleep(self):
        self.server.on("POST", "/api/media-jobs", status=201, body=job("ready"))
        self.serve_media()
        code, _ = self.run_json("extract", "u", "-o", self.out)
        self.assertEqual(code, 0)
        self.assertEqual(self.clock.sleeps, [])

    def test_cancelled_job_ends_with_error(self):
        self.server.on("GET", "/api/media-jobs/j1", body=job("cancelled"))
        code, data = self.run_json("extract", "u")
        self.assertEqual(code, 2)
        self.assertEqual(data["code"], "JOB_CANCELLED")
