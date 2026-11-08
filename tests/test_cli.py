import pytest
from click.testing import CliRunner

from samay.cli import EXIT_AMBIGUOUS, EXIT_ERROR, cli
from samay.engine.paths import EPHEMERIS_PATH

needs_kernel = pytest.mark.skipif(not EPHEMERIS_PATH.exists(), reason="ephemeris file not present")
PUNE = ["--date", "1990-08-15", "--time", "14:30", "--place", "Pune"]


@needs_kernel
def test_chart_happy_path():
    r = CliRunner().invoke(cli, ["chart", *PUNE])
    assert r.exit_code == 0, r.output
    assert r.output.startswith("Lagna: ") and "UTC+05:30" in r.output


@needs_kernel
def test_today_and_dasha_with_now():
    for cmd in ("today", "dasha"):
        r = CliRunner().invoke(cli, [cmd, *PUNE, "--now", "2026-01-01T00:00:00"])
        assert r.exit_code == 0, r.output


def test_ambiguous_place_lists_choices():
    r = CliRunner().invoke(cli, ["chart", "--date", "1990-08-15", "--time", "14:30", "--place", "Springfield, US"])
    assert r.exit_code == EXIT_AMBIGUOUS
    assert r.output.count("--choice ") == 3


def test_ambiguous_time_lists_folds():
    r = CliRunner().invoke(cli, ["chart", "--date", "2021-11-07", "--time", "01:30", "--place", "New York City"])
    assert r.exit_code == EXIT_AMBIGUOUS
    assert "--fold 0" in r.output and "--fold 1" in r.output


def test_malformed_date():
    r = CliRunner().invoke(cli, ["chart", "--date", "15th Aug", "--time", "14:30", "--place", "Pune"])
    assert r.exit_code == EXIT_ERROR and "error:" in r.output


def test_data_info():
    r = CliRunner().invoke(cli, ["data-info"])
    assert r.exit_code == 0 and "profile_id: parashari-lahiri" in r.output
