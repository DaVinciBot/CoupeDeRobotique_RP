---
name: review-branch
description: Revue détaillée obligatoire avant tout `git push` ou `gh pr create` (le hook review_gate refuse sinon le push). Vérifie que la branche fait exactement ce qui a été demandé, respecte l'architecture, le règlement et les invariants de sûreté, est testée hors robot et sert de base solide pour la suite ; lance des relectures indépendantes par agents, proportionnées à la taille et au risque du diff ; enregistre le tampon de revue du commit HEAD. À utiliser avant chaque push, et quand on demande de vérifier ou relire une branche.
---

# Revue d'une branche avant push

Le but n'est pas que le code « marche maintenant » : il doit faire **exactement** ce qui a été demandé, être cohérent avec le reste du dépôt, être testé, et servir de base aux cases suivantes de `docs/TODO.md` sans être refait. Une revue bâclée est pire qu'une revue absente, parce qu'elle donne une fausse assurance. Une revue disproportionnée coûte des jetons sans rien trouver de plus : le nombre d'agents suit la taille et le risque du diff (étape 3).

Le hook git `pre-push` de `tools/review_gate/review_gate.py` (ADR 0009), actif seulement dans les commandes de Claude, refuse de pousser un commit qui n'a pas de tampon. Le tampon s'écrit uniquement par la commande `stamp` de l'étape 7.

## 0. Préparer

1. Commiter tout le travail : la revue porte sur HEAD, et `stamp` refuse un arbre modifié.
2. `git fetch origin`, puis la base : `git merge-base HEAD origin/dev` (`origin/main` pour une branche `hotfix/*`).
3. Rassembler ce qui servira de référence aux relectures, **par écrit** :
   - **la demande, mot pour mot** : les messages de la personne qui décrivent le travail (et leurs précisions ultérieures), pas un résumé ;
   - les cases de `docs/TODO.md` concernées ;
   - les **numéros** des sections de `docs/ARCHITECTURE RP 2027.md` et des ADR de `docs/adr/` concernés ;
   - les règles du règlement concernées (versions et fichiers : CLAUDE.md, « Sources de vérité »), s'il y a du comportement en match ;
   - la liste des fichiers modifiés : `git diff --stat <base>...HEAD`.

## 1. Contrôles automatiques

Les commandes du CLAUDE.md, toutes, depuis la racine. En plus, selon ce qui a changé :

- `firmware/` : `pio run -e teensy41` et `pio test -e native` dans chaque `firmware/<carte>/` touchée ;
- `dashboard/` : `pnpm lint && pnpm typecheck && pnpm test && pnpm build` ;
- `domain/`, `services/` ou `editions/` : les scénarios de match (`tests/scenarios/`), dès qu'ils existent.

Un contrôle qui échoue se corrige avant d'aller plus loin. Ne jamais désactiver ni affaiblir un test ou une règle pour faire passer.

## 2. Auto-relecture

Lire `git diff <base>...HEAD` **en entier, fichier par fichier** (pas seulement le dernier commit). Construire le tableau de traçabilité : chaque exigence de la demande → fichiers qui la réalisent → test qui la prouve. Puis vérifier :

- **Périmètre** : chaque ligne modifiée se rattache à la demande ; rien en plus, rien d'oublié.
- **Invariants de sûreté** du CLAUDE.md : aucun n'est affaibli.
- **Architecture** : frontières des couches, socle sans thème, pas de décision hors architecture sans ADR.
- **Conventions** : typage, `dataclass(frozen=True, slots=True)`/`Enum`, unités SI, valeurs du robot et du jeu dans la config.
- **Matériel** : rien d'inventé (messages Teensy, géométrie, câblage, séquences, formats UDP) ; les inconnues sont marquées dans la config et dans « Points à valider » de `docs/TODO.md`.
- **Tests** : ils testent le comportement demandé, hors robot, y compris les cas d'erreur réels ; ils échoueraient si le code était faux.
- **Solidité pour la suite** : lire les cases suivantes de la TODO qui reposeront sur ce code. Pourront-elles s'y appuyer telles quelles ? Pas de rustine temporaire, de valeur en dur « pour l'instant », de `# type: ignore`, de `Any`, d'`except` large, de TODO caché.
- **Documentation** : TODO cochée, ADR écrit si besoin, architecture et README cohérents.
- **Signature** : aucun commit ni texte de PR ne met Claude en co-auteur ou signataire.

## 3. Choisir le niveau

Le niveau le plus haut atteint par un fichier du diff l'emporte. Le noter dans le rapport, avec la raison.

| Niveau | Le diff touche | Relectures |
| --- | --- | --- |
| 0 | Du Markdown seulement, hors ADR, architecture, `CLAUDE.md` et `.claude/` : case cochée, README, guide | Aucun agent : l'auto-relecture de l'étape 2 suffit |
| 1 | Tout le reste | `dvb-reviewer` |
| 2 | Un invariant de sûreté du CLAUDE.md (arrêt, fin de match, tirette, évitement, 350 mm, heartbeat), le contrat d'un port, `firmware/`, `packages/usb_com/`, `tools/review_gate/`, `.claude/settings.json`, `packages/supervisor/`, `packages/net/`, `dashboard/`, `deploy/`, ou plus de 400 lignes de code hors tests | `dvb-reviewer` et **un** spécialiste, celui qui couvre le risque principal (tableau de l'étape 4) |

Dans le doute entre deux niveaux, prendre le plus haut.

## 4. Relectures indépendantes

Lancer les agents du niveau **en parallèle, dans un seul message**. Chacun reçoit le même dossier : la demande mot pour mot, la base et la commande de diff, la liste des fichiers, les cases TODO, les **numéros** des sections d'architecture, ADR et règles à lire (rien d'autre à lire en entier), et la mention « contrôles de l'étape 1 passés, ne pas les relancer ». **Ne pas lui donner ses propres conclusions** : on veut un regard qui n'est pas ancré sur le sien. Préciser qu'il ne modifie rien et qu'il rend au plus 10 retours avec fichier:ligne, gravité (bloquant, important, mineur) et scénario d'échec concret.

| Rôle | Agent préféré | Repli s'il n'est pas disponible |
| --- | --- | --- |
| Niveaux 1 et 2 | `dvb-reviewer` (agent du projet, `.claude/agents/`) | Session ouverte avant son ajout : `general-purpose`, à qui l'on demande de lire `.claude/agents/dvb-reviewer.md` et de le suivre |
| Spécialiste, code Python ou C++ | `voltagent-qa-sec:surgeon-reviewer` | `feature-dev:code-reviewer`, sinon `general-purpose` |
| Spécialiste, `firmware/`, `packages/usb_com/`, contrat brain ↔ Teensy | `voltagent-domains:embedded-systems` | `general-purpose` |
| Spécialiste, `packages/supervisor/`, `packages/net/`, `dashboard/`, `deploy/` | skill `security-review` ou `voltagent-qa-sec:security-auditor` | `general-purpose` |

Un agent `general-purpose` de repli reçoit en plus la checklist de son rôle. Noter dans le rapport quels agents ont tourné et lesquels manquaient.

## 5. Trier et corriger

Utiliser la skill `superpowers:receiving-code-review` si elle est disponible. Chaque retour se vérifie dans le code avant d'y croire (un agent peut se tromper avec assurance), puis :

- **bloquant** : écrire d'abord le test qui montre le défaut, puis corriger, puis commiter (Conventional Commits) ;
- **important** : corriger de la même façon s'il est dans le périmètre de la demande, sinon le reporter ;
- **mineur** : corriger s'il est trivial, sinon le lister dans le rapport ;
- **rejeté** : écrire pourquoi, avec la preuve ;
- **reporté** : « Points à valider » de `docs/TODO.md` ou question à la personne, jamais corrigé en douce.

Un désaccord sur le règlement ou sur le matériel se pose à la personne au lieu d'être tranché.

## 6. Re-vérifier

Relancer les contrôles de l'étape 1 et relire soi-même le diff des corrections.

**Une seule re-relecture par agent, ciblée**, et seulement si la correction d'un retour bloquant n'est pas triviale (conception, contrat, sûreté). L'agent qui l'a signalé reçoit les retours bloquants et le diff des corrections ; il vérifie qu'ils sont corrigés sans rien casser autour, sans refaire la revue de la branche. Les retours importants et mineurs ne relancent jamais d'agent. S'il reste un bloquant après cette re-relecture, s'arrêter et demander à la personne.

## 7. Rapport et tampon

Écrire le rapport **hors du dépôt** (dossier temporaire de la session), avec ces six sections, chacune remplie :

```markdown
# Revue de <branche>

## Demande
La demande mot pour mot, les cases TODO visées.

## Traçabilité
Exigence → fichiers → test, une ligne par exigence.

## Contrôles
Commandes lancées et résultat.

## Relectures
Niveau choisi et pourquoi ; agents lancés (et manquants), verdict de chacun ; re-relecture éventuelle.

## Corrections
Retours corrigés (commit), rejetés (raison), reportés (où).

## Points ouverts
Ce qui reste à valider (matériel, règlement, autre équipe), ou « Aucun ».
```

Puis :

```bash
uv run python tools/review_gate/review_gate.py stamp --report <rapport>
```

`stamp` relance les étapes `uv run` de la CI sur HEAD (pas les jobs firmware et dashboard : ils sont lancés à l'étape 1), vérifie les six sections et enregistre le tampon dans `.git/dvb-review/<sha>.md`. Tout nouveau commit après le tampon demande une revue de complément.

## 8. Pousser et ouvrir la PR

`git push`, puis `gh pr create` vers `dev`. Le hook refuse de pousser un commit fait après le tampon : tout commiter avant la revue. La description de PR suit `.github/pull_request_template.md` ; sa section « Revue avant push » résume le rapport (niveau, agents utilisés, écarts corrigés, points ouverts).

## Revue de complément

Pour les commits faits après un tampon en réponse à des retours (relecture de la PR, oubli signalé) ou pour un merge de `dev`. Du travail nouveau, qui n'est ni l'un ni l'autre, demande une revue normale.

1. Repérer le dernier commit tamponné de la branche, en remontant les premiers parents (un merge de `dev` n'y mêle pas les tampons des autres branches ; marche aussi dans un worktree) :

   ```bash
   dir="$(git rev-parse --git-common-dir)/dvb-review"
   for sha in $(git rev-list --first-parent HEAD); do [ -f "$dir/$sha.md" ] && { echo "$sha"; break; }; done
   ```

   Puis relire seulement `git diff <tamponné>..HEAD`.
2. Un merge de `dev` sans conflit ni autre changement : les contrôles de l'étape 1 seuls, sans auto-relecture ni agent (`dev` est déjà relu), puis le point 4.
3. Sinon : étapes 1 et 2 sur ce diff, puis le niveau de l'étape 3 calculé **sur ce diff** ; un agent ne tourne que si le complément est de niveau 2, avec le dossier de l'étape 4 limité au complément.
4. Un rapport aux six sections, appliqué au complément : la « Demande » contient les retours ou la demande à l'origine des commits, mot pour mot. Puis `stamp`.

## Interdits

- Écrire ou copier un tampon autrement que par `stamp`.
- Contourner le hook (`--no-verify`, variables `GIT_CONFIG_*`, `gh api`, outil MCP GitHub, autre outil).
- Alléger la revue sous le niveau de l'étape 3 sans le dire dans le rapport.
- Mettre Claude en co-auteur ou en signataire, où que ce soit.

Une personne qui veut pousser sans revue le fait elle-même, depuis son terminal.
