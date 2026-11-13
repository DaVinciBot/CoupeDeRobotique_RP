"""Edition chosen by the config, loaded by name (architecture, section 0; ADR 0006).

The core never imports an edition: the config names it ("edition": "cdr_<year>") and
load_edition imports editions.<name> at startup. Each edition module exposes a load() function
that reads its files and returns its Edition; nothing is read at import.
"""

import importlib
from typing import Protocol, runtime_checkable

from dvb_brain.domain.arena import Arena
from dvb_brain.domain.match_rules import MatchRules
from dvb_brain.domain.scoring import Scoring


@runtime_checkable
class Edition(Protocol):
    """Theme of a year: table, scoring table and game rules.

    The interface grows with the core (ADR 0006): register_actions comes with the action
    registry (TODO 7.1), sim_elements with the simulation (TODO 11.1).
    """

    @property
    def id(self) -> str:
        """Name of the module of the edition, e.g. "cdr_<year>"; the arena_id of its strategies."""
        ...

    @property
    def arena(self) -> Arena: ...

    @property
    def scoring(self) -> Scoring: ...

    def rules(self) -> MatchRules: ...


class EditionError(Exception):
    """The edition named by the config cannot be loaded."""


def load_edition(name: str) -> Edition:
    """Import editions.<name> and return what its load() gives.

    At startup only: this reads the files of the edition. Raise an EditionError when there is no
    such edition, or when it does not give an Edition with this id.
    """
    module_name = f"editions.{name}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name not in ("editions", module_name):
            raise  # a module missing inside the edition: its own error says more
        raise EditionError(f"edition: no module {module_name}, got {name!r}") from error
    edition = module.load()
    if not isinstance(edition, Edition):
        raise EditionError(f"{module_name}.load(): expected an Edition, got {edition!r}")
    if edition.id != name:
        raise EditionError(f"{module_name}.load(): expected the id {name!r}, got {edition.id!r}")
    return edition
