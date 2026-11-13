import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

import pytest

from dvb_brain.app.edition import EditionError, load_edition
from dvb_brain.domain.arena import Arena, Side, Zone
from dvb_brain.domain.match_rules import MatchRules
from dvb_brain.domain.scoring import Scoring


@dataclass(frozen=True, slots=True)
class FakeRules:
    def end_zones(self, side: Side) -> tuple[Zone, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class FakeEdition:
    id: str
    arena: Arena
    scoring: Scoring

    def rules(self) -> MatchRules:
        return FakeRules()


def install_edition(monkeypatch: pytest.MonkeyPatch, name: str, load: Callable[[], object]) -> None:
    """Make editions.<name> importable, with this load() function."""
    module = ModuleType(f"editions.{name}")
    setattr(module, "load", load)  # noqa: B010
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_template_loads() -> None:
    edition = load_edition("_template")

    assert edition.id == "_template"
    assert edition.arena.zones == {}
    assert edition.scoring.points == {}
    assert edition.rules().end_zones(Side.BLUE) == ()
    assert edition.rules().end_zones(Side.YELLOW) == ()


def test_unknown_edition_is_named() -> None:
    with pytest.raises(EditionError, match=r"no module editions\.cdr_1999, got 'cdr_1999'"):
        load_edition("cdr_1999")


def test_module_missing_inside_the_edition_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    def import_module(name: str) -> ModuleType:
        raise ModuleNotFoundError("No module named 'missing_dependency'", name="missing_dependency")

    monkeypatch.setattr(importlib, "import_module", import_module)

    with pytest.raises(ModuleNotFoundError, match="missing_dependency"):
        load_edition("_template")


def test_edition_needs_a_load_function(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "editions.empty", ModuleType("editions.empty"))

    with pytest.raises(EditionError, match=r"editions\.empty: expected a load\(\) function"):
        load_edition("empty")


def test_load_must_give_an_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    install_edition(monkeypatch, "broken", lambda: "not an edition")

    with pytest.raises(EditionError, match=r"editions\.broken\.load\(\): expected an Edition"):
        load_edition("broken")


def test_id_must_be_the_module_name(monkeypatch: pytest.MonkeyPatch) -> None:
    template = load_edition("_template")
    install_edition(
        monkeypatch, "renamed", lambda: FakeEdition("other", template.arena, template.scoring)
    )

    with pytest.raises(EditionError, match=r"expected the id 'renamed', got 'other'"):
        load_edition("renamed")
