"""Every test runs against a small GeoNames extract built with the real gazetteer builder, so CI
never needs the full database. Tests that want the real one use the `real_gazetteer` fixture."""
from pathlib import Path

import pytest

from samay import service
from samay.engine import geo, paths
from samay.engine.gazetteer_build import build

MINI = Path(__file__).parent / "fixtures" / "geonames-mini"
MINI_COUNTRIES = ["IN", "US", "UA", "IT"]


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
