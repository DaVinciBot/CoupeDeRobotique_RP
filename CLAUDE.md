# CLAUDE.md

Consignes pour travailler sur le code du robot principal DaVinciBot (Coupe de France de Robotique 2027, qualification Eurobot). Elles s'ajoutent aux instructions de la personne qui demande ; en cas de conflit, sa demande l'emporte, sauf sur les invariants de sûreté.

**Compromis :** ces consignes privilégient la prudence à la vitesse. Pour une tâche triviale, juger au cas par cas.

## Sources de vérité

- `docs/ARCHITECTURE RP 2027.md` : organisation du code et raisons des choix. Toute modification doit rester cohérente avec ce document ; s'il faut s'en écarter, le dire et proposer un ADR dans `docs/adr/`.
- `docs/TODO.md` : ce qui reste à faire, dans l'ordre. Une tâche demandée correspond en général à une ou plusieurs cases ; les citer dans la PR.
- Règlement : règlement général Eurobot (RG v1.3) et règles de jeu 2027 (RJ v1.0). Toute stratégie, action de jeu ou comportement en match se vérifie contre eux : citer la règle (ex. RG H.3, RJ E.2.b). Si le règlement est ambigu ou ne couvre pas le cas, le dire clairement au lieu de trancher seul.

## Conventions

- Code, noms et commentaires en anglais ; documentation, ADR et descriptions de PR en français.
- Python 3.14, typage partout, pyright strict. `dataclass(frozen=True, slots=True)` ou `msgspec.Struct` et `Enum` plutôt que des dictionnaires.
- Unités SI partout dans le code (m, rad, s). Conversion seulement aux bords (stratégies en mm et degrés, affichage, messages Teensy). Une variable hors SI porte son unité dans son nom (`x_mm`, `theta_deg`).
- Repère : origine en bas à gauche vu du public, x vers la droite (0 à 3 m), y vers le fond (0 à 2 m), θ trigonométrique.
- Une boucle asyncio par processus ; jamais de données modifiables partagées entre threads.
- Toute dépendance ajoutée doit avoir une roue aarch64 pour Python 3.14 (Raspberry Pi 5). Le vérifier et le dire si ce n'est pas le cas.

Commandes :

```bash
uv sync --frozen              # install
uv run pytest                 # tests
uv run ruff format && uv run ruff check
uv run pyright
uv run lint-imports           # import rules of the core
uv run python tools/core_check/theme_words.py   # theme words in the core
uv run python tools/core_check/theme_coordinates.py   # theme coordinates in the core
pio run -e teensy41           # firmware build (in firmware/<board>/)
pio test -e native            # firmware tests on PC
uv run python tools/review_gate/review_gate.py stamp --report <file>   # review of HEAD (section 6)
```

## 1. Réfléchir avant de coder

**Ne pas supposer. Ne pas cacher une incertitude. Exposer les compromis.**

Avant d'implémenter :

- Énoncer ses hypothèses. En cas de doute, demander.
- Si plusieurs interprétations existent, les présenter au lieu d'en choisir une en silence.
- Si une approche plus simple existe, le dire. Contester quand c'est justifié.
- Si quelque chose n'est pas clair, s'arrêter, nommer ce qui bloque, demander.
- **Ne jamais inventer** ce qui dépend du matériel ou d'une autre équipe : contenu des messages Teensy, géométrie du robot, câblage (tirette, BAU), séquences des mécanismes, format UDP du lidar ou du calcul déporté. Si l'information n'est ni dans le code, ni dans l'architecture, ni dans `docs/TODO.md`, demander ; si elle reste inconnue, la marquer explicitement dans la config (valeur refusée en profil `match`) et l'ajouter aux « Points à valider » de `docs/TODO.md`.
- Si une demande touche la méca, l'élec ou un firmware Teensy, dire précisément ce qui devra être validé côté matériel.

## 2. La simplicité d'abord

**Le minimum de code qui résout le problème. Rien de spéculatif.**

- Aucune fonctionnalité au-delà de la demande.
- Aucune abstraction pour un code utilisé une seule fois.
- Pas de paramètre de config « au cas où ». En revanche, une valeur qui décrit le robot ou le jeu (dimensions, gains, durées, points, zones) ne s'écrit jamais en dur : elle va dans `config/robot.json` ou dans les fichiers de l'édition.
- Pas de gestion d'erreur pour des cas impossibles. Les pannes réelles (Teensy muette, lidar muet, exception) ne sont pas des cas impossibles : elles sont gérées par le `SafetyMonitor`, pas au coup par coup.
- Si 200 lignes pourraient en faire 50, réécrire.

Se demander : « Un ingénieur senior trouverait-il ça trop compliqué ? » Si oui, simplifier.

## 3. Des changements chirurgicaux

**Ne toucher que ce qui est nécessaire. Ne nettoyer que ce qu'on a soi-même sali.**

En modifiant du code existant :

- Ne pas « améliorer » le code, les commentaires ou la mise en forme voisins.
- Ne pas refactorer ce qui n'est pas cassé.
- Suivre le style existant, même si on ferait autrement.
- Si on remarque du code mort sans rapport, le signaler sans le supprimer.

Respecter les frontières de l'architecture :

- `domain/` n'importe ni asyncio, ni `services/`, ni `adapters/`, ni `app/`.
- Le socle n'importe jamais `editions/*` et ne contient aucun mot ni aucune coordonnée du thème de l'année. Ce qui est propre à 2027 va dans `editions/cdr_2027/`.
- Seul `app/` sait quel adaptateur (réel, simulé, faux) est branché.
- Une PR du brain ne modifie pas un firmware ni usb_com, sauf si la demande le dit.

Quand ses changements créent des orphelins :

- Supprimer les imports, variables et fonctions que SES changements ont rendus inutiles.
- Ne pas supprimer le code mort préexistant sans demande.

Le test : chaque ligne modifiée se rattache directement à la demande.

## 4. Une exécution guidée par des objectifs

**Définir des critères de réussite. Boucler jusqu'à les avoir vérifiés.**

Transformer chaque tâche en objectif vérifiable, hors du robot :

- « Ajouter l'évitement » → « Écrire un test avec `FakeLidar` et `FakeClock` où un adversaire entre dans la zone, vérifier que `stop` est appelé en moins d'un cycle, puis le faire passer. »
- « Corriger le bug de fin de match » → « Écrire un scénario qui reproduit le robot encore en mouvement après 100 s, puis le faire passer. »
- « Refactorer le planificateur » → « Les tests et le benchmark passent avant et après. »

Moyens de test, du plus rapide au plus complet : tests unitaires du `domain`, faux matériel (`adapters/fake/`) avec `FakeClock`, scénarios de match du simulateur, Teensy virtuelle sur `pty`, rejeu de logs et de balayages lidar enregistrés. Toujours dire comment le code proposé se teste sans le robot.

Pour une tâche en plusieurs étapes, annoncer un plan court :

```
1. [Étape] → vérifier : [contrôle]
2. [Étape] → vérifier : [contrôle]
3. [Étape] → vérifier : [contrôle]
```

Avant de rendre la main : ruff, pyright et pytest passent ; les scénarios de match passent si `domain/`, `services/` ou `editions/` ont changé. Avant tout push ou toute PR : la revue de la section 6.

## 5. Utiliser les skills et agents disponibles

**Un skill ou un agent disponible qui s'applique à la tâche n'est pas facultatif.**

En début de tâche, regarder les skills et agents de la session et utiliser ceux du tableau qui s'appliquent. S'il en manque un, prendre le repli et le dire dans le rapport de revue. La skill `review-branch` et les agents `dvb-*` sont versionnés dans `.claude/` : ils sont toujours là.

| Moment | Si disponible | Repli |
| --- | --- | --- |
| Concevoir une fonctionnalité ou un changement non trivial | `superpowers:brainstorming`, `superpowers:writing-plans` ; confronter le plan à l'architecture avec `dvb-architecture-reviewer` | agent `Plan` |
| Écrire le code | `superpowers:test-driven-development`, `andrej-karpathy-skills:karpathy-guidelines` | le test d'abord, à la main |
| Bug, test qui échoue, comportement inattendu | `superpowers:systematic-debugging`, `voltagent-qa-sec:debugger` | reproduire par un test avant de corriger |
| Firmware, usb_com, contrat brain ↔ Teensy | `voltagent-domains:embedded-systems` | `general-purpose` |
| Avant de dire « fini » ou « ça passe » | `superpowers:verification-before-completion` | relancer les commandes et lire leur sortie |
| Avant chaque `git push` ou `gh pr create` | skill `review-branch` (section 6) | — |
| Retours de relecture, d'un agent ou d'une personne | `superpowers:receiving-code-review` | vérifier chaque retour dans le code avant de l'appliquer |

Un agent de relecture reçoit la demande mot pour mot et le diff, jamais ses propres conclusions : on veut un regard indépendant.

## 6. Vérifier en profondeur avant de pousser

**Ce qui part sur GitHub est vérifié, cohérent et testé, pas seulement « ça marche maintenant ».**

- Avant tout `git push` et toute `gh pr create`, suivre la skill `review-branch` : contrôles, relecture de tout le diff, relectures indépendantes par agents, corrections, rapport, tampon. Un hook (`.claude/settings.json`, `tools/review_gate/`, ADR 0009) refuse le push ou la PR tant que le commit HEAD n'a pas de tampon.
- La revue répond à quatre questions. La branche fait-elle exactement la demande, rien de plus ? Est-elle cohérente avec l'architecture, les ADR, le règlement et les invariants de sûreté ? Est-elle testée hors robot ? Les cases suivantes de `docs/TODO.md` pourront-elles s'appuyer dessus sans la réécrire ?
- Le résumé du rapport va dans la section « Revue avant push » de la PR.
- Interdit : écrire un tampon autrement que par `review_gate.py stamp`, contourner le hook, alléger la revue sans le dire. Une personne qui veut pousser sans revue le fait elle-même, depuis son terminal.

## Invariants de sûreté (non négociables)

Aucune demande ne justifie de les affaiblir. Si une demande les contredit, le signaler et ne pas l'appliquer.

- Le robot s'arrête proprement en cas de perte de la Teensy, de lidar muet, d'exception non gérée ou de BAU. Il ne part jamais au hasard.
- Le match dure 100 s à partir du retrait de la tirette ; à la fin, tout s'arrête, actionneurs compris (RG H.2, H.3). Le minuteur de fin ne dépend pas de la stratégie.
- Le départ ne se fait que par la tirette, lue seulement quand le robot est armé (RG F.6, faux départ RG H.4). La tirette virtuelle n'existe qu'en profil `test`.
- L'évitement n'est jamais désactivable en profil `match` (désactivation volontaire = forfait, RG H.4).
- Aucun actionneur au-dessus de 350 mm (RG F.3).
- La Teensy moteur s'arrête seule après 200 ms sans heartbeat ; ne jamais supprimer ni allonger ce délai sans ADR.

## Git et PR

- Branches créées depuis `dev` avec un préfixe : `feat/`, `fix/`, `perf/`, `test/`, `refactor/`, `docs/` ; `hotfix/` depuis `main`. Règles complètes dans `CONTRIBUTING.md`.
- Messages en Conventional Commits, en anglais : `feat(nav): add visibility graph planner`.
- Claude ne se met **jamais** en co-auteur ni en signataire : aucune ligne `Co-Authored-By`, aucune mention « Generated with Claude Code » ni rien d'équivalent dans les commits, PR, issues, commentaires ou relectures. Le hook `review_gate` refuse ces lignes et `attribution` est vide dans `.claude/settings.json`.
- Petites PR vers `dev`, une relecture obligatoire. Quand c'est utile, proposer un découpage en plusieurs PR.
- Dans la description de PR (`.github/pull_request_template.md`) : cases de `docs/TODO.md` concernées, comment c'est testé, ce qui reste à valider côté matériel, résumé de la revue (section 6). Cocher les cases dans la même PR.

---

**Ces consignes fonctionnent si :** les diffs contiennent moins de changements inutiles, on réécrit moins de code trop compliqué, et les questions arrivent avant l'implémentation plutôt qu'après les erreurs.
