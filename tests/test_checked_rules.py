"""The shipped rules files, as they are: each loads, and the ones the owner has checked say so."""
import importlib
import pkgutil

import pytest

from samay import engine

NAMES = [i.name for i in pkgutil.iter_modules(engine.__path__) if i.name not in ("entries", "profiles", "rules")]


def _real(mod):
    f = mod.load_rules
    return getattr(f, "__wrapped_real__", f)


@pytest.mark.parametrize("name", NAMES)
def test_every_shipped_rules_file_loads_and_a_checked_one_names_its_checker(name):
    mod = importlib.import_module(f"samay.engine.{name}")
    if not hasattr(mod, "RULES_PATH"):
        pytest.skip("not a rules module")
    rules = _real(mod)()
    if rules.level != "unchecked":
        assert rules.servable and rules.checked_by == "h2"
