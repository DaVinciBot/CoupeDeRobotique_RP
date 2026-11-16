---
name: review-branch
description: Revue détaillée obligatoire avant tout `git push` ou `gh pr create` (le hook review_gate bloque sinon). Vérifie que la branche fait exactement ce qui a été demandé, respecte l'architecture, le règlement et les invariants de sûreté, est testée hors robot et sert de base solide pour la suite ; lance des relectures indépendantes par agents ; enregistre le tampon de revue du commit HEAD. À utiliser avant chaque push, et quand on demande de vérifier ou relire une branche.
---

# Revue d'une branche avant push

Le but n'est pas que le code « marche maintenant » : il doit faire **exactement** ce qui a été demandé, être cohérent avec le reste du dépôt, être testé, et servir de base aux cases suivantes de `docs/TODO.md` sans être refait. Prendre le temps. Une revue bâclée est pire qu'une revue absente, parce qu'elle donne une fausse assurance.

Le hook `tools/review_gate/review_gate.py` (ADR 0009) refuse `git push` et `gh pr create` tant que HEAD n'a pas de tampon. Le tampon s'écrit uniquement par la commande `stamp` de l'étape 6.

## 0. Préparer

1. Commiter tout le travail : la revue porte sur HEAD, et `stamp` refuse un arbre modifié.
2. `git fetch origin`, puis la base : `git merge-base HEAD origin/dev` (`origin/main` pour une branche `hotfix/*`).
3. Rassembler ce qui servira de référence aux relectures, **par écrit** :
   - **la demande, mot pour mot** : les messages de la personne qui décrivent le travail (et leurs précisions ultérieures), pas un résumé ;
   - les cases de `docs/TODO.md` concernées ;
   - les sections de `docs/ARCHITECTURE RP 2027.md` et les ADR de `docs/adr/` concernés ;
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

## 3. Relectures indépendantes

Lancer les agents **en parallèle, dans un seul message**. Chacun reçoit le même dossier : la demande mot pour mot, la base et la commande de diff, la liste des fichiers, les cases TODO, les sections d'architecture, ADR et règles à lire. **Ne pas lui donner ses propres conclusions** : on veut un regard qui n'est pas ancré sur le sien. Préciser qu'il ne modifie rien et qu'il rend des retours avec fichier:ligne, gravité (bloquant, important, mineur) et scénario d'échec concret.

| Quand | Agent préféré | Repli s'il n'est pas disponible |
| --- | --- | --- |
| Toujours | `dvb-request-reviewer` et `dvb-architecture-reviewer` (agents du projet, `.claude/agents/`) | Session ouverte avant leur ajout : `general-purpose`, à qui l'on demande de lire `.claude/agents/<nom>.md` et de le suivre |
| Code Python ou C++ modifié | `voltagent-qa-sec:surgeon-reviewer` | `feature-dev:code-reviewer`, sinon `general-purpose` |
| Tests ajoutés ou modifiés, ou code sans test | `voltagent-qa-sec:qa-expert` | `general-purpose` |
| `firmware/`, `packages/usb_com/`, contrat brain ↔ Teensy | `voltagent-domains:embedded-systems` | `general-purpose` |
| `packages/supervisor/`, `packages/net/`, `dashboard/`, `deploy/` | skill `security-review` ou `voltagent-qa-sec:security-auditor` | `general-purpose` |

Un agent `general-purpose` de repli reçoit en plus la checklist de sa ligne. Noter dans le rapport quels agents ont tourné et lesquels manquaient.

## 4. Trier et corriger

Utiliser la skill `superpowers:receiving-code-review` si elle est disponible. Pour chaque retour :

- le vérifier dans le code avant d'y croire (un agent peut se tromper avec assurance) ;
- **à corriger** : écrire d'abord le test qui montre le défaut, puis corriger, puis commiter (Conventional Commits) ;
- **rejeté** : écrire pourquoi, avec la preuve ;
- **hors périmètre** : le reporter (« Points à valider » de `docs/TODO.md` ou question à la personne), pas le corriger en douce.

Un désaccord sur le règlement ou sur le matériel se pose à la personne au lieu d'être tranché.

## 5. Re-vérifier

Relancer les contrôles de l'étape 1. Si les corrections ne sont pas triviales, relancer l'agent concerné sur le diff des corrections. Au bout de trois tours sans converger, s'arrêter et demander à la personne.

## 6. Rapport et tampon

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
Agents lancés (et manquants), verdict de chacun.

## Corrections
Retours corrigés (commit), rejetés (raison), reportés (où).

## Points ouverts
Ce qui reste à valider (matériel, règlement, autre équipe), ou « Aucun ».
```

Puis :

```bash
uv run python tools/review_gate/review_gate.py stamp --report <rapport>
```

`stamp` relance les étapes `uv run` de la CI sur HEAD (pas les jobs firmware et dashboard : ils sont lancés à l'étape 1), vérifie les six sections et enregistre le tampon dans `.git/dvb-review/<sha>.md`. Tout nouveau commit après le tampon demande une nouvelle revue de ce qui a changé.

## 7. Pousser et ouvrir la PR

`git push`, puis `gh pr create` vers `dev`, chacun seul dans sa commande, depuis le dossier du dépôt et pour la branche courante : le hook refuse un push combiné à un `cd`, à un `git commit` ou à une autre branche. La description de PR suit `.github/pull_request_template.md` ; sa section « Revue avant push » résume le rapport (agents utilisés, écarts corrigés, points ouverts).

## Interdits

- Écrire ou copier un tampon autrement que par `stamp`.
- Contourner le hook (`gh api`, outil MCP GitHub, alias, autre outil).
- Alléger la revue sans le dire dans le rapport.
- Mettre Claude en co-auteur ou en signataire, où que ce soit.

Une personne qui veut pousser sans revue le fait elle-même, depuis son terminal.
