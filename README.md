# Robot Principal - Coupe De France de Robotique

Code du robot principal de l'équipe DaVinciBot, pour la Coupe de France de Robotique.

## Sommaire

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Lancer les tests](#lancer-les-tests)
- [Structure du dépôt](#structure-du-dépôt)
- [Documentation](#documentation)
- [Organisation des branches](#organisation-des-branches)

## Prérequis

| Outil | Pour quoi | Nécessaire pour |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python et dépendances. uv installe lui-même Python 3.14 (`.python-version`). | Tout le code Python |
| [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/) (`pio`) | Compilation et tests des firmwares Teensy | `firmware/` seulement |
| [pnpm](https://pnpm.io/installation) | Dépendances et build du dashboard | `dashboard/` seulement |

Pour travailler sur le brain, uv suffit.

## Installation

```bash
git clone https://github.com/DaVinciBot/CoupeDeRobotique_RP
cd CoupeDeRobotique_RP
uv sync --frozen              # Python 3.14 + dépendances de uv.lock, dans .venv/
uv run pre-commit install     # ruff et pyright à chaque commit
```

`uv sync --frozen` n'écrit jamais dans `uv.lock` : tout le monde, la CI et la Pi ont les mêmes versions.

## Lancer les tests

Les mêmes contrôles que la CI (job `python`), à lancer depuis la racine :

```bash
uv run pytest                                   # tests
uv run ruff format && uv run ruff check         # formatage et lint
uv run pyright                                  # types
uv run lint-imports                             # règles d'import du socle
uv run python tools/core_check/theme_words.py   # mots du thème dans le socle
```

Firmware, dans `firmware/<carte>/` :

```bash
pio run -e teensy41           # compilation
pio test -e native            # tests sur PC
```

Dashboard, dans `dashboard/` :

```bash
pnpm install --frozen-lockfile
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

Les firmwares et le dashboard n'ont pas encore rejoint `dev` : leurs commandes sont celles que la CI lancera dès qu'ils seront là.

## Structure du dépôt

```text
├── packages/          # paquets Python du workspace uv, chacun avec src/ et tests/
│   ├── brain/         # dvb_brain : domain/ services/ ports/ adapters/ app/
│   ├── common_msgs/   # dvb_common_msgs : messages entre processus
│   ├── lidar/         # dvb_lidar : réception UDP, filtrage, suivi
│   ├── net/           # dvb_net : lien avec le calcul déporté
│   ├── sim/           # dvb_sim : simulateur 2D, Teensy virtuelle
│   ├── supervisor/    # dvb_supervisor : API du dashboard, gestion des processus
│   └── usb_com/       # dvb_usb_com : protocole Pi <-> Teensy
├── dashboard/         # React + TypeScript (Vite, pnpm)
├── firmware/          # un projet PlatformIO par carte Teensy
├── lidar_driver/      # image Docker du pilote lidar
├── editions/          # un module par thème annuel, _template/ pour en démarrer un
├── config/            # configuration du robot (robot.json)
├── deploy/            # installation sur la Pi (systemd, nginx, udev)
├── tools/             # outils de CI (core_check)
└── docs/              # architecture, TODO, ADR (docs/adr/)
```

Le **socle** (`packages/`, `dashboard/`, `firmware/`, `lidar_driver/`, `deploy/`) ne dépend pas du thème de l'année et resservira aux prochaines coupes. Tout ce qui est propre à un règlement est dans `editions/<édition>/`. La CI vérifie cette séparation.

Plusieurs dossiers sont encore vides : ils se remplissent dans l'ordre de [docs/TODO.md](docs/TODO.md).

## Documentation

- [Architecture logicielle du robot principal (CDR 2027)](docs/ARCHITECTURE%20RP%202027.md) : organisation du code, choix techniques et raisons de ces choix. Sert aussi de base pour les prochaines coupes.
- [TODO](docs/TODO.md) : ce qui reste à faire, dans l'ordre.
- [ADR](docs/adr/) : une décision d'architecture par fichier.
- [Démarrer une nouvelle édition](editions/_template/README.md).
- [CONTRIBUTING.md](CONTRIBUTING.md) : branches, commits, PR, relectures.

## Organisation des branches

- `main` : code testé, celui qui part en compétition.
- `dev` : branche d'intégration et branche par défaut.
- `feat/*`, `fix/*`, `perf/*`, `test/*`, `refactor/*`, `docs/*` : travail en cours, créées depuis `dev`.
- `hotfix/*` : correction urgente, créée depuis `main`.

Les règles complètes sont dans [CONTRIBUTING.md](CONTRIBUTING.md).
