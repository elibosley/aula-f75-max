"""Read battery-test data through the installed Studio process."""

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from keyboard_customize import validate


RETRY_DELAYS = (2, 5, 10)
TRANSIENT_CONFLICTS = (
    "Bluetooth discovery failed.",
    "No enrolled Bluetooth keyboard is connected.",
    "No verified Bluetooth settings reply.",
    "Bluetooth settings timed out.",
    "Keyboard settings are busy.",
    "Keyboard transport is busy;",
    "Bluetooth settings session expired or changed.",
    "Invalid or stale gauge measurement",
)


class StudioReadError(RuntimeError):
    """A Studio read failed, with a bounded diagnostic suitable for receipts."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def classify_http_error(error):
    if error.code == 423:
        return "studio_busy", True
    if error.code == 409:
        try:
            message = json.loads(error.read(4096)).get("error")
        except (OSError, ValueError, AttributeError):
            message = None
        error.studio_message = message[:2000] if isinstance(message, str) else None
        if isinstance(message, str) and message.startswith(TRANSIENT_CONFLICTS):
            return "bluetooth_unavailable", True
    return f"studio_http_{error.code}", False


class StudioSampler:
    def __init__(self, manifest, proc_matches, *, deadline=None, event_log=None):
        self.deadline = deadline
        self.event_log = event_log
        self.manifest = manifest
        self.proc_matches = proc_matches
        self.origin = manifest["studio_origin"]
        self.check_process()
        with urlopen(self.origin + "/api/hardware", timeout=10) as response:
            metadata = json.load(response)
        if not metadata.get("desktop") or not metadata.get("power_telemetry"):
            raise StudioReadError("studio_telemetry_unavailable")
        self.headers = {
            "Origin": self.origin,
            "X-F75-CSRF": metadata["csrf"],
            "Content-Type": "application/json",
        }

    def check_process(self):
        if not self.proc_matches(self.manifest["studio_process"]):
            raise StudioReadError("studio_process_changed")

    def log_event(self, event, **fields):
        data = dict(event=event, observed_at_unix=time.time(),
                    monotonic_seconds=time.monotonic(), **fields)
        stream = self.event_log if self.event_log is not None else sys.stderr
        print(json.dumps(data, separators=(",", ":")), file=stream, flush=True)
        if self.event_log is not None:
            os.fsync(stream.fileno())

    def request(self, action):
        if action not in ("read", "power"):
            raise ValueError("Only read-only measurements are allowed")
        board = self.manifest["board_identity"]
        body = dict(action=action, transport="bluetooth", expected_transport="bluetooth",
                    expected_slot=2, board_identity=board)
        attempt = 0
        outage_started = None
        while True:
            self.check_process()
            remaining = None if self.deadline is None else self.deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                self.log_event("deadline_reached", action=action, attempts=attempt)
                raise StudioReadError("measurement_deadline")
            request = Request(self.origin + "/api/hardware",
                              data=json.dumps(body).encode(), headers=self.headers)
            detail = None
            try:
                with urlopen(request, timeout=35 if remaining is None else min(35, remaining)) as response:
                    result = json.load(response)
            except HTTPError as error:
                with error:
                    reason, retryable = classify_http_error(error)
                    detail = getattr(error, "studio_message", None)
            except (TimeoutError, URLError, ConnectionError):
                reason, retryable = "studio_connection_unavailable", True
            else:
                self.check_process()
                if result.get("transport") != "bluetooth" or result.get("board_identity") != board:
                    raise StudioReadError("studio_board_or_transport_changed")
                if outage_started is not None:
                    self.log_event("recovered", action=action, failed_attempts=attempt,
                                   outage_seconds=time.monotonic() - outage_started)
                return result
            self.check_process()
            attempt += 1
            if outage_started is None:
                outage_started = time.monotonic()
            if not retryable or (self.deadline is None and attempt > len(RETRY_DELAYS)):
                self.log_event("read_failed", action=action, reason=reason, error_message=detail, attempts=attempt)
                raise StudioReadError(reason)
            delay = RETRY_DELAYS[attempt - 1] if attempt <= len(RETRY_DELAYS) else 60
            if self.deadline is not None:
                delay = max(0, min(delay, self.deadline - time.monotonic()))
            self.log_event("retry", action=action, reason=reason, attempt=attempt,
                           error_message=detail, delay_seconds=delay, outage_seconds=time.monotonic() - outage_started)
            time.sleep(delay)

    def sample(self, transport, probe=None, board=None):
        if transport != "bluetooth" or board != self.manifest["board_identity"]:
            raise ValueError("battery_only_identity_required")
        return self.request("power")["power"]

    def settings(self):
        data = bytes.fromhex(self.request("read")["document"]["base_hex"])
        validate(data)
        return data
