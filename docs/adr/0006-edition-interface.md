# ADR 0006 — Interface `Edition` et chargement d'une édition

- **Statut** : proposé
- **Date** : 2026-11-13
- **Cases** : [TODO 2.7](../TODO.md#27-interface-edition)

## Contexte

L'[architecture, section 0](../ARCHITECTURE%20RP%202027.md#0-un-code-réutilisable-dune-année-sur-lautre) décrit un `Protocol` `Edition` : `id`, `arena`, `register_actions(registry)`, `rules()` et `sim_elements()`. `MatchRules` y ajoute `is_action_allowed(action, world, t)`, `forbidden_zones(world)` et `end_zones(side)`. Plusieurs de ces membres utilisent des types qui n'existent pas encore : `WorldSnapshot` (TODO 4), `ActionRegistry` (7.1) et `SimElements` (11.1).

Le socle doit charger l'édition par son nom, lu dans la config. Or le dossier `editions/` n'était pas importable : le projet racine du workspace uv était « virtual », et `sys.path.append` est exclu ([ADR 0001](0001-repository-layout.md)).

## Décision

**Une interface qui grandit avec le socle.** On ne déclare que ce qui peut être typé aujourd'hui :

| Membre | Arrive avec |
| --- | --- |
| `Edition.id`, `Edition.arena`, `Edition.scoring`, `Edition.rules()` | 2.7 (cette décision) |
| `MatchRules.end_zones(side)` | 2.7 |
| `MatchRules.is_action_allowed(action, world, t)`, `MatchRules.forbidden_zones(world)` | le `WorldSnapshot` (4), les garde-fous (7.2) |
| `Edition.register_actions(registry)` | le registre d'actions (7.1) |
| `Edition.sim_elements()` | la simulation (11.1) |

- **`scoring` s'ajoute à l'interface de la section 0.** L'horloge de match (3.1) et le garde-fou des tirs (7.2) liront le début de la phase d'attaque dans `Scoring.phase_starts` ([ADR 0005](0005-scoring-and-strategy-format.md)).
- **`MatchRules` est dans `dvb_brain.domain.match_rules`**, car la carte de navigation (5.1, `domain`) s'en servira. Le `WorldSnapshot` (4), que prendront `is_action_allowed` et `forbidden_zones`, devra donc lui aussi être dans `domain`.
- **`Edition` et `load_edition` sont dans `dvb_brain.app.edition`.** Seule la composition manipule l'édition entière : les services reçoivent `arena`, `scoring`, `rules()` et plus tard le registre, jamais l'`Edition`. Le contrat import-linter des couches le vérifie ([ADR 0008](0008-brain-layers.md)). `register_actions` pourra y référencer des types de `services` sans déplacer le `Protocol`. La place de `SimElements` sera choisie en 11.1 : `dvb-sim` est un autre processus, et le brain ne doit pas dépendre de `dvb_sim`. Les membres sont en lecture seule (`@property`) : une dataclass gelée est conforme.
- **Chaque module d'édition expose `load() -> Edition`**, qui lit `arena.json` et `scoring.json`. Rien n'est lu à l'import. L'`id` est le nom du dossier (`Path(__file__).parent.name`) : copier `_template` ne demande pas de le changer.
- **`load_edition(name)`** importe `editions.<name>` avec `importlib`, appelle `load()`, vérifie que le résultat est une `Edition` dont l'`id` vaut `name`, puis vérifie la symétrie de la table (`check_symmetry`). Le côté jaune est joué en miroir à travers les `mirror_id` (section 9.5) : un `mirror_id` faux pourrait mener dans une aire adverse (RG H.4), on le refuse donc au lancement et pas seulement dans les tests de l'édition.
- **Deux erreurs au lancement (9.2).** `EditionError` quand l'édition est introuvable : nom qui n'est pas un nom de module, paquet `editions` non installé, module absent, pas de `load()`, objet qui n'est pas une `Edition`, `id` différent. `SchemaError` quand ses fichiers sont invalides ou sa table n'est pas symétrique : le message nomme le fichier et le champ, comme pour la config (9.1). Un module manquant à l'intérieur de l'édition garde son propre `ModuleNotFoundError`.
- **pyright strict sur le code des éditions** (`editions/*.py`, `editions/*/*.py`), comme sur le socle : les garde-fous du règlement (7.2) y vivront. Les tests des éditions restent en mode `basic`, comme ceux du socle.
- **Le projet racine installe le paquet `editions`** : `[build-system]` uv_build, `module-name = "editions"`, `module-root = ""`. `uv sync` le rend importable partout (tests, brain, pyright), sans `sys.path.append` dans le code. L'installation éditable ajoute la racine du dépôt au chemin d'import (fichier `.pth`) : `tools`, `config` ou `packages` deviennent aussi importables, sans effet tant qu'aucun code ne les importe. Le socle n'importe toujours jamais une édition en dur : import-linter le vérifie.
- **Imports relatifs dans les éditions** (`from .rules import Rules`) : copier `_template` n'oblige pas à renommer les imports.

## Alternatives écartées

- **Créer tout de suite des versions minimales de `WorldSnapshot`, `ActionRegistry` et `SimElements`** : des types à refaire dans les sections 4, 7.1 et 11.1.
- **`pythonpath = ["."]` dans la config pytest** : `editions` n'est importable que dans les tests, et le lancement réel (9.2) reste à régler.
- **Un objet `EDITION` construit à l'import du module** : il lirait les fichiers à l'import, ce qu'on a exclu en reprenant le code de 2026.
- **`Edition` dans `domain`** : `register_actions` (7.1) prendra des types de `services`, que `domain` n'a pas le droit d'importer.

## Conséquences

- Le nom de l'édition viendra de `config/robot.json` (`"edition": "cdr_2027"`, TODO 9.1).
- La liste des types d'action du test des stratégies 2027 attend le registre de la TODO 7.1, et non plus 2.7 comme le prévoyait l'ADR 0005.
- `editions/_template` est une édition chargeable : le test du chargeur du socle s'en sert, pour ne citer aucun mot du thème.
