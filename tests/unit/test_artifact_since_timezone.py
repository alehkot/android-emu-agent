"""Logcat lower bounds preserve absolute instants across host timezones."""

from __future__ import annotations

import os
import shlex
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from android_emu_agent.artifacts.manager import ArtifactManager, resolve_logcat_since


@pytest.fixture(params=["UTC0", "EST5EDT", "JST-9"])
def host_timezone(request):
    old = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    try:
        yield request.param
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-30T15:30:00.123Z",
        "2026-10-30T11:30:00.123-04:00",
        "2026-10-31T00:30:00.123+09:00",
        "2026-10-30T15:30:00.123",  # Existing timezone-less ISO contract is UTC.
    ],
)
@pytest.mark.usefixtures("host_timezone")
def test_iso_bounds_preserve_instant(value):
    seconds = int(datetime(2026, 10, 30, 15, 30, tzinfo=UTC).timestamp())
    assert resolve_logcat_since(value) == (f"{seconds}.123", True)


@pytest.mark.parametrize("value", ["10m", "10m ago", "10 minutes ago"])
@pytest.mark.usefixtures("host_timezone")
def test_relative_bounds_use_utc_clock_not_host_wall_time(value):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 30, 15, 40, 0, 123000, tzinfo=UTC).astimezone(tz)

    with patch("android_emu_agent.utils.time_parser.datetime", FixedClock):
        assert resolve_logcat_since(value) == ("1793374200.123", True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, (None, False)),
        ("", (None, False)),
        (100, ("100", False)),
        ("100", ("100", False)),
        ("10-30 11:30:00.123", ("10-30 11:30:00.123", True)),
        ("2026-10-30 11:30:00.123", ("2026-10-30 11:30:00.123", True)),
    ],
)
@pytest.mark.usefixtures("host_timezone")
def test_native_device_times_and_line_counts_are_unchanged(value, expected):
    assert resolve_logcat_since(value) == expected


@pytest.mark.asyncio
@pytest.mark.usefixtures("host_timezone")
async def test_capture_sends_fractional_epoch_with_existing_filters(tmp_path):
    device = MagicMock()
    device.shell.side_effect = ["1234", "retained log entry"]
    manager = ArtifactManager(output_dir=tmp_path)
    path = await manager.pull_logs(
        device,
        "s-test",
        package="com.example.app",
        level="error",
        since="2026-10-30T11:30:00.123-04:00",
    )
    args = shlex.split(device.shell.call_args_list[1].args[0])
    assert args == ["logcat", "-d", "-t", "1793374200.123", "*:E", "--pid=1234"]
    assert path.read_text() == "retained log entry"


def test_whole_second_still_has_decimal_to_avoid_line_count():
    assert resolve_logcat_since("2026-10-30T15:30:00Z") == ("1793374200.000", True)
