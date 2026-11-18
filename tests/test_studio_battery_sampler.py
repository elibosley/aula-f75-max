"""A missed wireless reply can recover without accepting an unrelated device."""

import io
import contextlib
import tempfile
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from studio_battery_sampler import RETRY_DELAYS, StudioReadError, StudioSampler


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def http_error(status, message):
    return HTTPError("http://127.0.0.1:1234/api/hardware", status, "",
                     {}, response({"error": message}))


class StudioBatterySamplerTest(unittest.TestCase):
    def setUp(self):
        self.board = "a" * 64
        manifest = dict(studio_origin="http://127.0.0.1:1234",
                        studio_process={"pid": 1}, board_identity=self.board)
        self.alive = True
        with patch("studio_battery_sampler.urlopen", return_value=response(
                dict(desktop=True, power_telemetry=True, csrf="test"))):
            self.sampler = StudioSampler(manifest, lambda process: self.alive)

    def read(self):
        return self.sampler.sample("bluetooth", board=self.board)

    def test_recovers_from_missed_reply_busy_and_timeout(self):
        with patch("studio_battery_sampler.urlopen", side_effect=[
            http_error(409, "No verified Bluetooth settings reply. Keep the Mac unlocked."),
            http_error(423, "Keyboard is busy"),
            TimeoutError(),
            response(dict(transport="bluetooth", board_identity=self.board,
                          power={"estimate_percent": 99.17})),
        ]) as request, patch("studio_battery_sampler.time.sleep") as sleep:
            self.assertEqual(self.read(), {"estimate_percent": 99.17})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], list(RETRY_DELAYS))
        for call in request.call_args_list:
            self.assertEqual(json.loads(call.args[0].data),
                             dict(action="power", transport="bluetooth",
                                  expected_transport="bluetooth", expected_slot=2,
                                  board_identity=self.board))

    def test_retries_are_bounded(self):
        with patch("studio_battery_sampler.urlopen", side_effect=TimeoutError) as request, \
                patch("studio_battery_sampler.time.sleep"):
            with self.assertRaisesRegex(StudioReadError, "studio_connection_unavailable"):
                self.read()
        self.assertEqual(request.call_count, len(RETRY_DELAYS) + 1)

    def test_identity_permission_and_unknown_conflicts_are_terminal(self):
        for status, message in [
            (409, "A different keyboard is connected. Read it before applying settings."),
            (409, "The Bluetooth slot changed. Reload before saving settings."),
            (409, "Allow F75 Studio in Mac Input Monitoring to use Bluetooth."),
            (409, "An unknown error."),
            (403, "Reload this page before applying settings"),
        ]:
            with self.subTest(message=message), patch("studio_battery_sampler.urlopen",
                    side_effect=http_error(status, message)) as request:
                with self.assertRaisesRegex(StudioReadError, f"studio_http_{status}"):
                    self.read()
                request.assert_called_once()

    def test_wrong_response_and_restarted_app_are_terminal(self):
        with patch("studio_battery_sampler.urlopen", return_value=response(
                dict(transport="bluetooth", board_identity="b" * 64))) as request:
            with self.assertRaisesRegex(StudioReadError, "studio_board_or_transport_changed"):
                self.read()
            request.assert_called_once()
        with patch("studio_battery_sampler.urlopen",
                   side_effect=http_error(423, "Keyboard is busy")) as request, \
                patch("studio_battery_sampler.time.sleep",
                      side_effect=lambda delay: setattr(self, "alive", False)):
            with self.assertRaisesRegex(StudioReadError, "studio_process_changed"):
                self.read()
            request.assert_called_once()


class LongOutageTest(unittest.TestCase):
    def setUp(self):
        self.clock = 1000.0
        self.board = "a" * 64
        self.manifest = dict(studio_origin="http://127.0.0.1:1234",
                             studio_process={"pid": 1}, board_identity=self.board)

    def advance(self, seconds):
        self.clock += seconds

    def test_recovers_after_twenty_minutes_and_saves_logs_under_stdout_capture(self):
        with tempfile.TemporaryFile(mode="w+") as events:
            with patch("studio_battery_sampler.urlopen", return_value=response(
                    dict(desktop=True, power_telemetry=True, csrf="test"))):
                sampler = StudioSampler(self.manifest, lambda process: True,
                                        deadline=8200, event_log=events)
            with patch("studio_battery_sampler.time.monotonic", side_effect=lambda: self.clock), \
                    patch("studio_battery_sampler.time.sleep", side_effect=self.advance), \
                    patch("studio_battery_sampler.urlopen", side_effect=[
                        http_error(409, "No enrolled Bluetooth keyboard is connected.") for _ in range(25)
                    ] + [response(dict(transport="bluetooth", board_identity=self.board,
                                       power={"estimate_percent": 90.91}))]), \
                    contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(sampler.sample("bluetooth", board=self.board)["estimate_percent"], 90.91)
                events.seek(0)
                saved = [json.loads(line) for line in events]
            self.assertGreater(saved[-1]["outage_seconds"], 1200)
            self.assertEqual(saved[-1]["event"], "recovered")
            self.assertEqual(saved[-1]["failed_attempts"], 25)
            self.assertEqual(sum(row["event"] == "retry" for row in saved), 25)
            self.assertEqual(captured.getvalue(), "")

    def test_outage_reaches_deadline_with_retry_history_still_on_disk(self):
        with tempfile.TemporaryFile(mode="w+") as events:
            with patch("studio_battery_sampler.urlopen", return_value=response(
                    dict(desktop=True, power_telemetry=True, csrf="test"))):
                sampler = StudioSampler(self.manifest, lambda process: True,
                                        deadline=2800, event_log=events)
            with patch("studio_battery_sampler.time.monotonic", side_effect=lambda: self.clock), \
                    patch("studio_battery_sampler.time.sleep", side_effect=self.advance), \
                    patch("studio_battery_sampler.urlopen", side_effect=TimeoutError), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(StudioReadError, "measurement_deadline"):
                    sampler.sample("bluetooth", board=self.board)
                events.seek(0)
                saved = [json.loads(line) for line in events]
            self.assertEqual(self.clock, 2800)
            self.assertEqual(saved[-1]["event"], "deadline_reached")
            self.assertGreater(len(saved), 20)
