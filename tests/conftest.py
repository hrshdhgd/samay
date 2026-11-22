"""Every test runs against a small GeoNames extract built with the real gazetteer builder, so CI
never needs the full database. Tests that want the real one use the `real_gazetteer` fixture."""

from pathlib import Path

import pytest

from samay import service
from samay.engine import geo, paths
from samay.engine.gazetteer_build import build

MINI = Path(__file__).parent / "fixtures" / "geonames-mini"
MINI_COUNTRIES = ["IN", "US", "UA", "IT"]


TEST_DB_KEY = "ZmFrZS1rZXktZm9yLXRlc3RzLW9ubHktMDAwMDAwMDA="  # a valid Fernet key; never used for real data


def _keep_rules_unchecked():
    """The shipped rules files are now checked; most tests were written against the unchecked state (hidden until checked), so each rules module's load_rules is wrapped to
    report level unchecked. Tests that want the real state call `samay.engine.<module>.load_rules.__wrapped_real__` (see tests/test_checked_rules.py).
    """
    import dataclasses
    import importlib
    import pkgutil

    from samay import engine

    for info in pkgutil.iter_modules(engine.__path__):
        if info.name in (
            "house_effects",
            "entries",
            "profiles",
            "rules",
        ):  # chapter 20 was checked before these were; the rest are not rules files
            continue
        mod = importlib.import_module(f"samay.engine.{info.name}")
        real = getattr(mod, "load_rules", None)
        if real is None or not hasattr(mod, "RULES_PATH"):
            continue

        def wrapped(*args, _real=real, **kwargs):
            r = _real(*args, **kwargs)
            return (
                dataclasses.replace(r, level="unchecked", checked_by=None)
                if getattr(r, "level", None) not in (None, "unchecked")
                else r
            )

        wrapped.__wrapped_real__ = real
        mod.load_rules = wrapped


_keep_rules_unchecked()


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    """Every test gets its own database and key. Without this, a test that builds a default Store()
    would open (and encrypt with the test key) the developer's real data/samay.db."""
    from samay import crypto

    monkeypatch.setenv("SAMAY_DB", str(tmp_path / "isolated" / "samay.db"))
    monkeypatch.setenv("SAMAY_DB_KEY", TEST_DB_KEY)
    monkeypatch.setattr(crypto, "KEY_FILE", tmp_path / "isolated" / "samay.key")


@pytest.fixture
def empty_entries(monkeypatch, tmp_path):
    """No sourced entries at all, for tests of the 'no checked source' paths (which must not depend on which
    topics happen to have entries today)."""
    from samay.engine import entries

    folder = tmp_path / "no-entries"
    folder.mkdir()
    monkeypatch.setattr(entries, "ENTRIES_DIR", folder)
    entries.load_entries.cache_clear()
    yield
    entries.load_entries.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def real_data_is_untouched():
    """Fail loudly if the suite changes the developer's real database."""
    real = paths.DATA_DIR / "samay.db"
    before = real.stat().st_mtime_ns if real.exists() else None
    yield
    after = real.stat().st_mtime_ns if real.exists() else None
    assert before == after, "a test modified the real data/samay.db"


@pytest.fixture(scope="session", autouse=True)
def fixture_gazetteer(tmp_path_factory):
    db = tmp_path_factory.mktemp("gazetteer") / "gazetteer.sqlite"
    build(MINI, db, MINI_COUNTRIES, snapshot="fixture")
    geo.configure(db)
    service.data_info.cache_clear()
    yield db
    geo.configure(None)


@pytest.fixture
def real_gazetteer(fixture_gazetteer):
    if not paths.GAZETTEER_PATH.exists():
        pytest.skip("data/gazetteer.sqlite not built (run scripts/build_gazetteer.py)")
    geo.configure(paths.GAZETTEER_PATH)
    yield paths.GAZETTEER_PATH
    geo.configure(fixture_gazetteer)
