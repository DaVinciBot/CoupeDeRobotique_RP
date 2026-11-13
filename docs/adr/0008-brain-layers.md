# ADR 0008 — Couches du brain et place des types

- **Statut** : proposé
- **Date** : 2026-11-13
- **Cases** : [TODO 1.3](../TODO.md#13-qualité), et la place des types des cases 3.1, 3.3, 3.5, 4 et 9.1

## Contexte

L'[architecture, section 5.3](../ARCHITECTURE%20RP%202027.md#53-organisation-du-brain) range le brain en cinq couches : `domain` ne dépend de rien, `services` dépend de `domain` et des ports, `ports` ne contient que des interfaces (`typing.Protocol`), `adapters` implémente les ports, `app` compose le tout. Jusqu'ici, la CI ne vérifiait que la pureté de `domain`.

En ajoutant la vérification de toutes les couches, on voit que le plan de la TODO la contredit à plusieurs endroits :

- `Track` est prévu dans les ports (3.5), alors que le `WorldSnapshot` (4), qui le contient, doit être dans `domain` ([ADR 0006](0006-edition-interface.md)) ;
- `MoveKind` et `MoveCommand` sont prévus dans les ports (3.3), alors que `domain/motion_plan.py` (5.3) les produit ;
- le schéma de la config est prévu dans `app/config.py` (9.1), alors que `domain` et les services ont besoin de ses valeurs (rayon du robot, marges, durées de vie) et n'ont pas le droit d'importer `app` ;
- `MatchClock` est prévue dans `domain` avec un `elapsed()` sans argument, qui demanderait de lire l'heure, et un `is_attack_phase()`, qui est une règle de 2027 dans le socle.

## Décision

**Un contrat import-linter `layers`** dans le `pyproject.toml` racine : `app`, puis `adapters` et `services`, puis `ports`, puis `domain`. Chaque couche n'importe que les couches du dessous. `adapters` et `services` s'ignorent : seul `app` sait quel adaptateur est branché (CLAUDE.md). Le contrat qui interdit `asyncio` dans `domain` reste.

**Place des types** :

- **`ports/` ne contient que les `Protocol` et `Watch`.** Les types de valeurs qui passent par un port vont dans `domain`, à côté de leur premier utilisateur : `MoveCommand`, `MotionStatus` et `StopMode` dans `domain/motion.py`, `Track` et `TrackSet` dans `domain/world.py`, `ActuatorResult` avec les actionneurs. Le port les importe.
- **Modèle du monde dans `domain/world.py`** : `Source`, `Observed`, `ElementState`, `WorldSnapshot` et `WorldModel`. `WorldModel` ne lit pas l'heure, l'appelant donne la date de chaque mesure. Un snapshot ne change jamais : chaque mise à jour crée de nouvelles collections au lieu de modifier les anciennes.
- **Config** : `app/config.py` décode `config/robot.json` (msgspec, mm et degrés) vers des dataclasses SI définies dans `domain`, comme `MatchConstants` aujourd'hui. Les services reçoivent ces dataclasses, jamais le module de config.
- **`MatchClock` dans `domain`, sans lecture d'horloge** : démarrée à `t0`, avec `elapsed(now)`, `remaining(now)` et `in_phase(phase_id, now)`, qui lit `Scoring.phase_starts`. La phase d'attaque reste un identifiant de l'édition (`"attack"`), jamais un nom du socle.

## Alternatives écartées

- **Les types de valeurs dans `ports/`** : `domain` ne pourrait plus les utiliser (planificateur, modèle du monde, découpage des mouvements).
- **Un module `types.py` fourre-tout** : un fichier qui grossit sans fin et dont personne n'est responsable.
- **Ne vérifier que `domain`** : une dépendance `services → adapters` ou `services → app` passerait la CI.

## Conséquences

- Les cases 3.1, 3.3, 3.5, 4 et 9.1 de la TODO indiquent maintenant où vont leurs types.
- Un import interdit (par exemple `services` qui importe `app`) casse la CI ; c'est vérifié à la main en ajoutant un tel import.
