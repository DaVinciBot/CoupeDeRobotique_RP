# ADR 0009 — Revue obligatoire avant push pour Claude Code

- **Statut** : proposé
- **Date** : 2026-11-16
- **Cases** : [TODO 1.3](../TODO.md#13-qualité)

## Contexte

Une partie du code du robot est écrite avec Claude Code. Le `CLAUDE.md` lui demande de lancer ruff, pyright et pytest avant de rendre la main, mais rien ne l'oblige à vérifier en profondeur ce qu'il pousse. Les défauts qu'on veut éviter ne se voient pas dans la CI : un diff qui fait autre chose ou plus que la demande, un écart à l'architecture sans ADR, une règle du règlement mal lue, un invariant de sûreté affaibli, une valeur matérielle inventée, ou un code qui marche aujourd'hui mais que les cases suivantes de la TODO devront réécrire.

Des skills et des agents de relecture existent (superpowers, agents voltagent, feature-dev), mais ils ne servent que si Claude y pense, et tous les membres de l'équipe ne les ont pas installés.

Enfin, la règle « Claude ne se met jamais en co-auteur ni en signataire » du `CLAUDE.md` n'était appliquée que par la consigne, alors que Claude Code ajoute ces lignes par défaut.

## Décision

Le dossier `.claude/` est versionné ([architecture, sections 14.1 et 14.2](../ARCHITECTURE%20RP%202027.md#141-arborescence)) et contient :

| Fichier | Rôle |
| --- | --- |
| `skills/review-branch/SKILL.md` | La procédure de revue : contrôles, relecture de tout le diff avec un tableau de traçabilité, relectures indépendantes par agents en parallèle, tri et correction des retours, rapport en six sections, tampon |
| `agents/dvb-request-reviewer.md` | Agent de relecture du projet : conformité à la demande, à la TODO, au règlement, aux invariants de sûreté ; rien d'inventé sur le matériel |
| `agents/dvb-architecture-reviewer.md` | Agent de relecture du projet : conformité à l'architecture et aux ADR, simplicité, solidité pour les cases suivantes de la TODO |
| `settings.json` | Hook git `pre-push` déclaré par les variables `GIT_CONFIG_*` de `env` ; hook `PreToolUse` sur les commandes git et gh et sur les outils GitHub des serveurs MCP ; outils Edit et Write interdits sur les tampons ; `attribution` vide |

Les variables `GIT_CONFIG_*` de `env` n'existent que dans les commandes lancées par Claude Code. Elles déclarent un hook git `pre-push` (`hook.dvb-review.command`, git 2.54 ou plus récent) qui s'ajoute à ceux de `.git/hooks` et lance `tools/review_gate/review_gate.py pre-push`. Git lui donne ce qu'il va réellement pousser, quelle que soit la commande qui l'a lancé (`cd`, `bash -c`, alias, script, `gh pr create`). Le hook refuse :

- un commit poussé qui n'a pas de tampon `.git/dvb-review/<sha>.md`, quelle que soit la branche ;
- un commit poussé dont le message met Claude en co-auteur ou en signataire (lignes que Claude Code écrit lui-même, pas le prénom Claude).

La suppression d'une branche distante ne publie rien et passe. Une copie de travail sans `tools/review_gate/` (branche antérieure au dispositif, autre dépôt) ne peut pas lancer le hook, et le push est refusé : merger `dev` dans la branche d'abord ; un autre dépôt se pousse depuis une session ouverte dans ce dépôt-là, ou par une personne.

Le hook `PreToolUse` (même script, sous-commande `hook`) refuse :

- une commande git ou gh qui écrit un texte (commit, tag, création, édition ou commentaire de PR ou d'issue) dont le texte (commande, fichiers `-F` et `--body-file`) met Claude en co-auteur ou en signataire ;
- un push avec `--no-verify`, qui sauterait le hook `pre-push` ;
- un push ou une PR quand le hook `pre-push` n'est pas actif (git trop ancien, session ouverte avant l'ajout des variables) ;
- un outil MCP GitHub qui publie sans `git push` (création de PR, push de fichiers, écriture de fichier).

En cas d'erreur interne, les deux hooks refusent plutôt que de laisser passer.

Le tampon ne s'écrit que par `review_gate.py stamp --report <rapport>`, qui exige un arbre propre, un rapport dont les six sections sont remplies, relance les étapes `uv run` de la CI (un test vérifie que la liste reste celle de `ci.yml`) et vérifie que HEAD n'a pas bougé pendant les contrôles. Les agents voltagent et les skills superpowers sont utilisés quand ils sont installés ; sinon la skill indique un repli (`general-purpose`). Le résumé du rapport va dans la PR (section « Revue avant push » du modèle).

Le dispositif ne concerne que Claude : le terminal d'une personne n'a pas ces variables, et un push lancé depuis lui ne passe par aucun de ces hooks.

## Alternatives écartées

- **Consignes seules dans le `CLAUDE.md`** : rien ne bloque quand Claude oublie ou abrège la revue.
- **Hook git `pre-push` dans `.git/hooks`** : installé dans le clone, il toucherait aussi les personnes, qui poussent sans tampon.
- **Hook `PreToolUse` qui lit le texte des commandes shell** (première version de cette branche) : il devait reconnaître chaque forme d'un push (`if`, `"$(…)"`, `xargs`, `bash -c`, `cd`, refspecs…), passait encore à côté des alias, des scripts et de `push.default`, et tournait sur toutes les commandes Bash, qu'il bloquait toutes s'il plantait. Le hook `pre-push` voit ce que git pousse vraiment, en une trentaine de lignes.
- **Relecture par Claude dans la CI (GitHub Actions)** : clé d'API dans les secrets et coût à chaque PR, et la CI ne connaît pas la demande d'origine, qui est le premier critère de la revue. À reconsidérer si la revue locale ne suffit pas.

## Conséquences

- Un push de Claude prend plus de temps et de jetons : la skill adapte le nombre d'agents à ce qui a changé.
- Tout commit après le tampon demande une nouvelle revue de ce qui a changé.
- `gh pr create` n'est pas contrôlé lui-même : la PR montre ce qui a été poussé, donc ce qui a été relu. Le merge d'une PR reste régi par CONTRIBUTING (une approbation) et par GitHub.
- `stamp` ne relance que les étapes `uv run` de la CI. Les jobs firmware et dashboard sont lancés à la main par la skill quand ils sont touchés ; un nouveau job `uv run` (scénarios de match, TODO 11.5) fait échouer le test de synchronisation tant qu'il n'est pas ajouté à `stamp`.
- Il faut Claude Code 2.1.295 ou plus récent (`onFailure` des hooks), git 2.54 ou plus récent et uv avec Python 3.14. Sans uv, les commandes git et gh de Claude sont refusées ; avec un git plus ancien, ses push et ses PR le sont (message du hook `PreToolUse`).
- Le hook `PreToolUse` juge sur le texte de la commande, et seulement pour les commandes que reconnaît le filtre `if` (`git …`, `gh …`). Il refuse aussi une commande qui écrit un texte en citant une ligne de signature, ou `git commit --no-verify && git push` ; il ne voit pas `bash -c 'git push --no-verify'`, ni, avec un git trop ancien, `bash -c 'git push'`.
- Le dispositif protège contre l'oubli, pas contre un contournement volontaire : variables `GIT_CONFIG_*` modifiées, `-c hook.dvb-review.enabled=false`, `gh api`, un tampon copié par une commande Bash, un autre outil. Celui-ci est interdit par le `CLAUDE.md`.
