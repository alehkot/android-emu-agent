from __future__ import annotations

from datetime import UTC, datetime

import pytest

from android_emu_agent.errors import AgentError
from android_emu_agent.utils.time_parser import parse_datetime


def test_parse_datetime_none_returns_none() -> None:
    assert parse_datetime(None) is None


def test_parse_datetime_int_returns_int() -> None:
    assert parse_datetime(12345) == 12345


def test_parse_datetime_negative_int_raises() -> None:
    with pytest.raises(AgentError) as exc:
        parse_datetime(-5)
    assert exc.value.code == "ERR_INVALID_SINCE_TIMESTAMP"


def test_parse_datetime_raw_string_int() -> None:
    assert parse_datetime("123456789") == 123456789


def test_parse_datetime_relative_minutes() -> None:
    # 5 minutes ago = roughly 300 * 1000 ms ago
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    parsed = parse_datetime("5m ago")
    assert parsed is not None
    assert (now_ms - parsed) == pytest.approx(300000, abs=1000)


def test_parse_datetime_relative_hours() -> None:
    # 2 hours ago
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    parsed = parse_datetime("2 hours ago")
    assert parsed is not None
    assert (now_ms - parsed) == pytest.approx(2 * 3600 * 1000, abs=1000)


def test_parse_datetime_relative_days() -> None:
    # 1 day ago
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    parsed = parse_datetime("1 day ago")
    assert parsed is not None
    assert (now_ms - parsed) == pytest.approx(24 * 3600 * 1000, abs=1000)


def test_parse_datetime_iso_8601() -> None:
    dt = datetime(2026, 2, 22, 20, 24, 23, tzinfo=UTC)
    expected_ms = int(dt.timestamp() * 1000)
    assert parse_datetime("2026-02-22T20:24:23Z") == expected_ms
    assert parse_datetime("2026-02-22T20:24:23") == expected_ms


def test_parse_datetime_invalid_format_raises() -> None:
    with pytest.raises(AgentError) as exc:
        parse_datetime("invalid datetime")
    assert exc.value.code == "ERR_INVALID_DATETIME_FORMAT"
