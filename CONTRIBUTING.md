# Contribuer au Robot Principal

## Branches

| Branche | Rôle | Créée depuis |
|---|---|---|
| `main` | Code testé, prêt pour la compétition | – |
| `dev` | Intégration, branche par défaut | – |
| `feat/nom` | Nouvelle fonctionnalité | `dev` |
| `fix/nom` | Correction de bug | `dev` |
| `perf/nom` | Amélioration de performance | `dev` |
| `test/nom` | Ajout ou modification de tests | `dev` |
| `refactor/nom` | Réorganisation du code sans changement de comportement | `dev` |
| `docs/nom` | Documentation | `dev` |
| `hotfix/nom` | Correction urgente en compétition | `main` |

## Flux de travail

1. Créer la branche depuis `dev`, avec un préfixe (`feat/`, `fix/`, `perf/`, `test/`, `refactor/`, `docs/`).
2. Pousser la branche et ouvrir une PR vers `dev`.
3. Le merge se fait via PR, après une relecture (voir [Pull requests](#pull-requests)).
4. Quand `dev` est testé et prêt pour la compétition, ouvrir une PR `dev → main`.

## Hotfix

1. Créer `hotfix/nom` depuis `main`.
2. Ouvrir une PR vers `main`.
3. Reporter ensuite le correctif dans `dev` : PR `hotfix/nom → dev`, ou merge de `main` vers `dev`.

## Messages de commit

Format [Conventional Commits](https://www.conventionalcommits.org/fr/), en anglais :

```
type(scope): description
```

- `type` : `feat`, `fix`, `perf`, `test`, `refactor` ou `docs`, comme les préfixes de branche. S'y ajoutent `build` (dépendances, outillage), `ci` (intégration continue) et `chore` (maintenance diverse).
- `scope` (facultatif) : la partie du code concernée, par ex. `nav`, `lidar`, `safety`.
- `description` : courte, à l'impératif, en minuscules, sans point final.

Exemples :

```
feat(nav): add visibility graph planner
fix(safety): stop motors when lidar goes silent
docs: add commit message format
```

## Pull requests

- **Petites PR.** Une PR par case de [docs/TODO.md](docs/TODO.md), ou par petit groupe de cases d'une même sous-section.
- **Une relecture par PR.** Une autre personne que l'auteur relit et approuve avant le merge. Pour les coordonnées d'une table ou un contrat entre deux équipes (protocole Teensy, format UDP), le relecteur est quelqu'un qui peut vérifier le fond.
- **Avant de demander la relecture**, les contrôles de la CI passent en local (commandes dans le [README](README.md#lancer-les-tests)).
- **Dans la description** : les cases de `docs/TODO.md` concernées, comment c'est testé, ce qui reste à valider côté matériel.
- **Les cases se cochent dans la même PR** que le travail qui les termine.

## Décisions d'architecture (ADR)

Le document de référence est [docs/ARCHITECTURE RP 2027.md](docs/ARCHITECTURE%20RP%202027.md). Une décision qui n'y figure pas, ou qui s'en écarte, s'écrit dans un ADR :

- un fichier court `docs/adr/NNNN-sujet.md`, avec le numéro libre suivant ;
- même plan que [l'ADR 0001](docs/adr/0001-repository-layout.md) : statut, date, cases de la TODO, contexte, décision, alternatives écartées, conséquences ;
- rédigé en français, ajouté dans la PR qui applique la décision et cité dans sa description ;
- un ADR mergé ne se réécrit pas : une nouvelle décision fait un nouvel ADR, qui indique celui qu'il remplace.

## Travailler avec Claude Code

Le dossier `.claude/` est versionné ([ADR 0009](docs/adr/0009-claude-review-before-push.md)) :

| Fichier | Rôle |
| --- | --- |
| `.claude/settings.json` | Hook git `pre-push` réservé aux commandes de Claude (variables `GIT_CONFIG_*`) et hook Claude Code sur les commandes git et gh et les outils MCP GitHub, tous deux dans `tools/review_gate/review_gate.py` ; outils Edit et Write interdits sur les tampons ; aucune signature de Claude |
| `.claude/skills/review-branch/` | Revue détaillée avant push : contrôles, relectures indépendantes par agents proportionnées au diff, corrections, rapport, tampon |
| `.claude/agents/dvb-reviewer.md` | Agent de relecture du projet : conformité à la demande, au règlement, aux invariants de sûreté et à l'architecture, bugs, solidité pour la suite |

- **Revue avant push.** Claude ne peut pas pousser un commit qui n'a pas de tampon de revue (`.git/dvb-review/<sha>.md`, jamais versionné) : un hook git `pre-push`, déclaré par les variables `GIT_CONFIG_*` de `.claude/settings.json`, ne tourne que dans les commandes de Claude et voit ce que git pousse réellement. Le tampon s'obtient par la skill `review-branch`, qui finit par `uv run python tools/review_gate/review_gate.py stamp --report <rapport>`. `--no-verify` et les outils MCP GitHub qui publient sont refusés. Claude ne peut pas pousser une copie de travail sans `tools/review_gate/` (branche antérieure au dispositif : merger `dev` d'abord ; autre dépôt). Les personnes ne sont pas concernées : leur terminal n'a pas ces variables.
- **Aucune signature de Claude.** Le hook refuse un commit, un push, une PR ou une issue dont le texte met Claude en co-auteur ou en signataire (lignes que Claude Code écrit lui-même, pas le prénom Claude).
- **Version.** Claude Code 2.1.295 ou plus récent (`onFailure` des hooks), git 2.54 ou plus récent (hooks déclarés dans la config git) et uv avec Python 3.14 (les hooks passent par `uv run`). Sans uv, les commandes git et gh de Claude sont refusées ; avec un git plus ancien, ses push et ses PR le sont.
- **Plugins recommandés.** Le CLAUDE.md (section 5) utilise les skills et agents suivants quand ils sont installés, avec un repli sinon : `superpowers` et `feature-dev` (marketplace `claude-plugins-official`, dépôt `anthropics/claude-plugins-official`), `andrej-karpathy-skills` (marketplace `karpathy-skills`, dépôt `forrestchang/andrej-karpathy-skills`), `voltagent-qa-sec` et `voltagent-domains` (marketplace `voltagent-subagents`, dépôt `VoltAgent/awesome-claude-code-subagents`). Installation dans Claude Code : `/plugin marketplace add <dépôt>`, puis `/plugin install <plugin>@<marketplace>`, par exemple `/plugin install voltagent-qa-sec@voltagent-subagents`.

## Règles automatiques

- Pas de push direct sur `dev` ni sur `main` : tout passe par une PR.
- Une PR vers `main` doit venir de `dev` ou d'un `hotfix/*`. Sinon le check `main-source` échoue et bloque le merge.
- Un nom de branche sans préfixe reconnu est signalé par un avertissement dans la PR, mais ne bloque pas le merge. Le préfixe reste recommandé pour garder l'historique lisible.
- Pas de force-push ni de suppression sur `dev` et `main`.
