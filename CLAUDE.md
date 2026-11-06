# CLAUDE.md

Consignes pour travailler sur le code du robot principal DaVinciBot (Coupe de France de Robotique 2027, qualification Eurobot). Elles s'ajoutent aux instructions de la personne qui demande ; en cas de conflit, sa demande l'emporte, sauf sur les invariants de sûreté.

**Compromis :** ces consignes privilégient la prudence à la vitesse. Pour une tâche triviale, juger au cas par cas.

## Sources de vérité

- `docs/ARCHITECTURE RP 2027.md` : organisation du code et raisons des choix. Toute modification doit rester cohérente avec ce document ; s'il faut s'en écarter, le dire et proposer un ADR dans `docs/adr/`.
- `TODO.md` : ce qui reste à faire, dans l'ordre. Une tâche demandée correspond en général à une ou plusieurs cases ; les citer dans la PR.
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
pio run -e teensy41           # firmware build (in firmware/<board>/)
pio test -e native            # firmware tests on PC
```

## 1. Réfléchir avant de coder

**Ne pas supposer. Ne pas cacher une incertitude. Exposer les compromis.**

Avant d'implémenter :

- Énoncer ses hypothèses. En cas de doute, demander.
- Si plusieurs interprétations existent, les présenter au lieu d'en choisir une en silence.
- Si une approche plus simple existe, le dire. Contester quand c'est justifié.
- Si quelque chose n'est pas clair, s'arrêter, nommer ce qui bloque, demander.
- **Ne jamais inventer** ce qui dépend du matériel ou d'une autre équipe : contenu des messages Teensy, géométrie du robot, câblage (tirette, BAU), séquences des mécanismes, format UDP du lidar ou du calcul déporté. Si l'information n'est ni dans le code, ni dans l'architecture, ni dans `TODO.md`, demander ; si elle reste inconnue, la marquer explicitement dans la config (valeur refusée en profil `match`) et l'ajouter aux « Points à valider » de `TODO.md`.
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

Avant de rendre la main : ruff, pyright et pytest passent ; les scénarios de match passent si `domain/`, `services/` ou `editions/` ont changé.

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
- Claude ne se met **jamais** en co-auteur ni en signataire : aucune ligne `Co-Authored-By`, aucune mention « Generated with Claude Code » ni rien d'équivalent dans les commits, PR, issues, commentaires ou relectures.
- Petites PR vers `dev`, une relecture obligatoire. Quand c'est utile, proposer un découpage en plusieurs PR.
- Dans la description de PR : cases de `TODO.md` concernées, comment c'est testé, ce qui reste à valider côté matériel. Cocher les cases dans la même PR.

---

**Ces consignes fonctionnent si :** les diffs contiennent moins de changements inutiles, on réécrit moins de code trop compliqué, et les questions arrivent avant l'implémentation plutôt qu'après les erreurs.
