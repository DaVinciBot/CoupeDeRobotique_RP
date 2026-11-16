# ADR 0009 — Revue obligatoire avant push pour Claude Code

- **Statut** : proposé
- **Date** : 2026-11-16
- **Cases** : [TODO 1.3](../TODO.md#13-qualité)

## Contexte

Une partie du code du robot est écrite avec Claude Code. Le `CLAUDE.md` lui demande de lancer ruff, pyright et pytest avant de rendre la main, mais rien ne l'oblige à vérifier en profondeur ce qu'il pousse. Les défauts qu'on veut éviter ne se voient pas dans la CI : un diff qui fait autre chose ou plus que la demande, un écart à l'architecture sans ADR, une règle du règlement mal lue, un invariant de sûreté affaibli, une valeur matérielle inventée, ou un code qui marche aujourd'hui mais que les cases suivantes de la TODO devront réécrire.

Des skills et des agents de relecture existent (superpowers, agents voltagent, feature-dev), mais ils ne servent que si Claude y pense, et tous les membres de l'équipe ne les ont pas installés.

Enfin, la règle « Claude ne se met jamais en co-auteur ni en signataire » du `CLAUDE.md` n'était appliquée que par la consigne, alors que Claude Code ajoute ces lignes par défaut.

## Décision

Le dossier `.claude/` est versionné et contient :

| Fichier | Rôle |
| --- | --- |
| `skills/review-branch/SKILL.md` | La procédure de revue : contrôles, relecture de tout le diff avec un tableau de traçabilité, relectures indépendantes par agents en parallèle, tri et correction des retours, rapport en six sections, tampon |
| `agents/dvb-request-reviewer.md` | Agent de relecture du projet : conformité à la demande, à la TODO, au règlement, aux invariants de sûreté ; rien d'inventé sur le matériel |
| `agents/dvb-architecture-reviewer.md` | Agent de relecture du projet : conformité à l'architecture et aux ADR, simplicité, solidité pour les cases suivantes de la TODO |
| `settings.json` | Hook `PreToolUse` sur les commandes `git` et `gh`, écriture des tampons interdite à Claude, `attribution` vide |

Le hook `tools/review_gate/review_gate.py` :

- refuse `git push` et `gh pr create` tant qu'il n'existe pas de tampon `.git/dvb-review/<sha>.md` pour le commit HEAD ;
- refuse un commit, un push, une PR ou une issue dont le texte met Claude en co-auteur ou en signataire.

Le tampon ne s'écrit que par `review_gate.py stamp --report <rapport>`, qui exige un arbre propre, un rapport dont les six sections sont remplies, et relance les contrôles du job `python` de la CI (un test vérifie que la liste reste celle de `ci.yml`). Les agents voltagent et les skills superpowers sont utilisés quand ils sont installés ; sinon la skill indique un repli (`general-purpose`). Le résumé du rapport va dans la PR (section « Revue avant push » du modèle).

Le hook ne concerne que Claude : un push lancé par une personne depuis son terminal ne passe pas par lui.

## Alternatives écartées

- **Consignes seules dans le `CLAUDE.md`** : rien ne bloque quand Claude oublie ou abrège la revue.
- **Hook git `pre-push`** : il toucherait aussi les personnes, ralentirait chaque push, et ne peut pas savoir si une relecture a eu lieu ; la CI fait déjà les contrôles.
- **Relecture par Claude dans la CI (GitHub Actions)** : clé d'API dans les secrets et coût à chaque PR, et la CI ne connaît pas la demande d'origine, qui est le premier critère de la revue. À reconsidérer si la revue locale ne suffit pas.

## Conséquences

- Un push de Claude prend plus de temps et de jetons : la skill adapte le nombre d'agents à ce qui a changé.
- Tout commit après le tampon demande une nouvelle revue de ce qui a changé.
- Les contrôles de `stamp` suivent ceux de la CI ; quand un job firmware ou dashboard devient obligatoire, la skill les fait lancer à la main en attendant de les ajouter à `stamp`.
- Le hook demande Claude Code 2.1.295 ou plus récent (`onFailure` des hooks) et un environnement uv installé (`uv sync --frozen`).
- Le hook protège contre l'oubli, pas contre un contournement volontaire (`sh -c`, autre outil) : celui-ci est interdit par le `CLAUDE.md`.
