# ADR 0001 — Organisation du dépôt 2027

- **Statut** : proposé
- **Date** : 2026-11-06
- **Cases** : [TODO 1.1](../TODO.md#11-arborescence)

## Contexte

Le code 2026 était rangé dans `robot1/` et `common/`. Les modules s'importaient avec `sys.path.append`, la configuration s'exécutait à l'import, et le code Python reposait sur taskbrain et loggerplusplus ([architecture, section 2](../ARCHITECTURE%20RP%202027.md#2-ce-quon-retient-du-code-2026)).

En 2027, on sépare un socle réutilisable et un module d'édition par thème ([architecture, section 0](../ARCHITECTURE%20RP%202027.md#0-un-code-réutilisable-dune-année-sur-lautre)). Brain, firmware, container lidar, simulation et dashboard partagent des contrats : protocole usb_com, format UDP du lidar, messages du bus.

Deux branches sont déjà ouvertes avec l'ancienne organisation : `feat/asservissement-v1` (firmware moteur dans `robot1/teensy_moteur/`) et `feat/lidar` (container dans `LIDAR/`).

## Décision

Un seul dépôt pour le robot principal, toutes éditions confondues. Les PAMI et le calcul déporté gardent leurs propres dépôts. L'arborescence est celle de la [section 14.1 de l'architecture](../ARCHITECTURE%20RP%202027.md#141-arborescence) :

| Dossier | Contenu | Rempli par |
| --- | --- | --- |
| `packages/` | Paquets Python du workspace uv, chacun avec `src/` et `tests/` | TODO 1.2 |
| `dashboard/` | React + TypeScript (Vite, pnpm) | TODO 19 |
| `firmware/` | Un projet PlatformIO par carte : `teensy_motor/`, `teensy_actuators/` | TODO 1.1, 13, 14 |
| `lidar_driver/` | Image Docker Ubuntu + ROS 2, export UDP des balayages | TODO 1.1, 16.1 |
| `editions/` | `_template/` et un module par édition (`cdr_2027/`) | TODO 1.5, 2.4 |
| `config/` | `robot.json` | TODO 9.1 |
| `deploy/` | Unités systemd, nginx, règles udev, profils NetworkManager | TODO 20 |
| `tools/` | `core_check/` : règles d'import et recherche des mots du thème dans le socle | TODO 1.3 |
| `docs/adr/` | Une décision d'architecture par fichier | — |

Un dossier encore vide contient un `.gitkeep`, supprimé quand son contenu arrive. Ses sous-dossiers sont créés en même temps que ce contenu.

Le code Python de 2026 n'est pas repris. Il sert seulement de référence.

## Alternatives écartées

- **Garder l'organisation 2026** (`robot1/`, `common/`) : elle repose sur `sys.path.append` et ne permet pas de faire de vrais paquets.
- **Un dépôt par composant** (brain, firmware, lidar) : `messages.h` et `messages.py` doivent être comparés en CI (TODO 12), et la Teensy virtuelle se compile à partir du firmware moteur (TODO 11.2). Les deux sont plus simples dans un seul dépôt.
- **Un dépôt par édition** : le socle serait dupliqué chaque année, alors que les anciens modules d'édition restent dans le dépôt pour rejouer leurs logs et leurs stratégies (architecture, section 0).

## Conséquences

Le code existant est déplacé par les auteurs des branches, dans leur branche, une fois cet ADR mergé dans `dev` :

1. Merger `dev` dans la branche (et pas `main`, qui ne contient pas encore cette organisation).
2. Déplacer le code et supprimer le `.gitkeep` devenu inutile. L'ordre compte : `git mv` range le dossier à l'intérieur de la cible si elle existe déjà, et échoue si le dossier parent de la cible n'existe pas (`git rm` du `.gitkeep` supprime le dossier vide).

   ```bash
   # feat/asservissement-v1 : firmware/ doit exister pendant le git mv
   git mv robot1/teensy_moteur firmware/teensy_motor
   git rm firmware/.gitkeep

   # feat/lidar : lidar_driver/ ne doit pas exister pendant le git mv
   git rm lidar_driver/.gitkeep
   git mv LIDAR lidar_driver
   ```

3. Seul le firmware est concerné par cette migration. Le Python de `feat/asservissement-v1` (`robot1/rasp/`, `config.json`, `pyproject.toml` à la racine) suit la règle ci-dessus : il ne rejoint pas `dev` tel quel et sert de référence pour les cases 1.2, 9.1 et 15.1. `common/usb_com` est repris par la section 12.

`firmware/teensy_actuators/` sera créé avec la section 14 : aucune branche ne contient encore ce firmware.
