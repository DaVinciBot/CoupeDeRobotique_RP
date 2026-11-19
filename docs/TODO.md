# TODO — Robot principal CDR 2027

Checklist de tout ce qu'il faut faire pour le robot principal, dans l'ordre où le faire. Elle suit le document d'architecture (`docs/ARCHITECTURE RP 2027.md`) ; les numéros entre parenthèses renvoient à ses sections.

**Ordre de travail.** Le socle du dépôt d'abord (section 1). Ensuite, deux parties avancent en même temps, chacune dans son ordre, sans attendre l'autre :

- le brain et la Pi : sections 2 à 11, 15.3, 15.4, puis 16 à 20, testées sur le faux matériel et le simulateur, sans carte Teensy ;
- les cartes Teensy : sections 12 à 14, contrats d'abord, testées en `native` et sur la Teensy virtuelle, sans le brain.

Elles se rejoignent dans les adaptateurs des cartes Teensy (15.1, 15.2), puis sur la table (section 21). Les points de rencontre sont dans le tableau ci-dessous. Une case qui attend une case de l'autre partie, ou placée plus loin dans la sienne, le dit : « (attend 12.1) ». Sans cette mention, une case ne dépend que des cases au-dessus d'elle dans sa partie.

**Règles pour cocher une case.**

- Une PR par case, ou par petit groupe de cases d'une même sous-section. Jamais une PR « brain v1 ».
- Une case n'est cochée qu'une fois la PR mergée dans `dev`, tests compris.
- Une décision qui n'est pas dans le document d'architecture → un ADR court dans `docs/adr/`, référencé dans la PR.
- Un point qui bloque une case et dépend d'une autre équipe → l'ajouter à la section « Points à valider » en fin de fichier.

**Jalons.** Ils servent à savoir où on en est, pas à cocher.

| Jalon | Critère |
| --- | --- |
| A — Brain testable | Sections 1 (hors firmware) à 4 faites : `uv run pytest` couvre domain, ports et modèle du monde |
| B — Match sur faux matériel | Sections 5 à 10 faites : la stratégie `homologation` se joue de bout en bout sur le faux matériel |
| C — Match simulé en CI | Section 11 faite : la matrice de scénarios passe en CI |
| D — Brain sur la vraie base | Sections 12.1, 12.3 (hors messages actionneurs), 13 et 15.1 faites : la stratégie `homologation` roule sur la table |
| E — Homologable | Section 21.2 faite, à la pré-coupe au plus tard |

Les jalons A à C ne demandent aucune carte Teensy, et les sections 12 à 14 ne demandent pas le brain : D les réunit.

**Points de rencontre.** Les cases dont dépendent des cases d'une autre partie, ou placées avant elles, et ce qui permet d'avancer sans les attendre.

| Point de rencontre | Case | Nécessaire à | En attendant |
| --- | --- | --- | --- |
| Contrat brain ↔ Teensy moteur | 12.1 | 12.3 (messages moteur), 13.4, 15.1 ; détails de 6.2, 8.1, 8.3 et 19.2 | Le brain code contre `MotionPort` (case 3.3, ADR 0010) avec `FakeMotion` (case 3.5) et `SimMotion` (case 11.2) |
| Contrat brain ↔ Teensy actionneurs | 12.2 | 12.3 (messages actionneurs), 14, 15.2 | Le brain code contre `ActuatorPort` (case 3.4) avec `FakeActuators` (case 3.5) |
| usb_com v2 | 12.3 | 13.4, 13.5, 15.1, 15.2 | Le brain n'utilise pas usb_com avant la section 15 |
| Teensy virtuelle | 13.5 | 15.1 | `SimMotion` (case 11.2) pour les scénarios de match |
| Format UDP du lidar | 16.1 | 11.3 (sortie UDP du lidar simulé), 16.2 | `SimLidarTracks` (case 11.3) |

---

## 1. Socle du dépôt

### 1.1 Arborescence

- [x] Créer l'arborescence de la section 14.1 : `packages/`, `dashboard/`, `firmware/`, `lidar_driver/`, `editions/`, `config/`, `deploy/`, `tools/`, `docs/adr/`.
- [x] Ranger le firmware moteur dans `firmware/teensy_motor/`.
- [ ] Ranger le firmware actionneurs dans `firmware/teensy_actuators/`.
- [x] Ranger le container lidar dans `lidar_driver/`.
- [x] Ne pas reprendre le code Python de 2026 (config exécutée à l'import, `sys.path.append`, `loggerplusplus`, taskbrain) : s'en servir comme référence seulement.
- [x] ADR 0001 « Organisation du dépôt 2027 ».

### 1.2 Workspace uv

- [x] `pyproject.toml` racine : `[tool.uv.workspace] members = ["packages/*"]`, `requires-python = ">=3.14,<3.15"`.
- [x] `.python-version` = `3.14`.
- [x] `packages/brain/` : `pyproject.toml` (paquet `dvb-brain`, module `dvb_brain`), `src/dvb_brain/{domain,services,ports,adapters,app}/__init__.py`, `tests/`.
- [x] Squelettes vides avec la même structure : `packages/usb_com`, `packages/lidar`, `packages/net`, `packages/supervisor`, `packages/sim`, `packages/common_msgs` (messages entre processus, 5.2).
- [x] Dépendances runtime du brain limitées à `msgspec`, `numpy`, `shapely>=2`. Les autres (`pyzmq`, `pyserial-asyncio-fast`, `gpiozero`, `lgpio`) arrivent avec l'adaptateur qui en a besoin.
- [x] Groupe dev : `pytest`, `pytest-asyncio`, `pytest-benchmark`, `hypothesis`, `ruff`, `pyright`, `pre-commit`, `import-linter`.
- [x] Vérifier qu'il existe une roue aarch64 pour Python 3.14 de chaque dépendance : `uv pip compile --python-version 3.14 --python-platform aarch64-unknown-linux-gnu --only-binary :all:`. Noter les exceptions dans un ADR.
- [x] `uv.lock` commité ; `uv sync --frozen` partout.

### 1.3 Qualité

- [x] `ruff` : `line-length = 100`, règles `E,F,I,UP,B,SIM,RUF,ASYNC,PTH,N`, formatage activé.
- [x] `pyright` en mode `strict` sur `packages/*/src`, `basic` sur les tests.
- [x] `.pre-commit-config.yaml` : ruff format, ruff check, pyright (hook local).
- [ ] `clang-format` pour le firmware, vérifié en CI.
- [x] Contrôles du socle :
  - [x] règles import-linter (`[tool.importlinter]` du `pyproject.toml` racine) : le socle n'importe jamais `editions.*` ; `domain` n'importe ni `services`, ni `adapters`, ni `app`, ni asyncio, ni les modules d'entrée-sortie et d'horloge (`pathlib`, `os`, `io`, `time`, `datetime`, `socket`, `subprocess`, `threading`) ; couches du brain dans l'ordre de la section 5.3, `services` et `adapters` indépendants (ADR 0008) ;
  - [x] `tools/core_check/theme_words.py` : cherche les mots du thème dans le socle et dans `config/match.json` (`pierre`, `stone`, `graal`, `grail`, `catapulte`, `château`, `castle`, `écurie`, `chevalier`…) et échoue s'il en trouve (0) ;
  - [x] `tools/core_check/theme_coordinates.py` : recherche des coordonnées du thème dans le socle, d'après les `arena.json` des éditions.
- [x] Revue avant push des changements faits avec Claude Code (ADR 0009) : skill `review-branch`, agents `dvb-*`, hook git `pre-push` réservé à Claude (`tools/review_gate/`) qui refuse un push sans tampon de revue et toute signature de Claude.

### 1.4 CI — `.github/workflows/ci.yml`

- [x] Job `python` : `astral-sh/setup-uv`, `uv sync --frozen`, ruff, pyright, import-linter, core_check, pytest.
- [x] Job `firmware` : `pio run -e teensy41` et `pio test -e native` pour chaque firmware.
- [x] Job `dashboard` (quand il existe) : `pnpm install --frozen-lockfile`, lint, typecheck, Vitest, build.
- [x] Rendre les jobs obligatoires dans le ruleset de `dev`.

### 1.5 Documentation de base

- [x] README : prérequis (uv, PlatformIO, pnpm), installation, lancer les tests, structure du dépôt.
- [x] CONTRIBUTING : Conventional Commits, une relecture par PR, ADR pour les décisions.
- [x] `editions/_template/` vide mais complet (table, zones, éléments, actions, règles, simulation, stratégie d'homologation), rempli au fil des sections 2 et 7.

---

## 2. Brain — couche `domain` (pure, sans temps ni matériel)

### 2.1 Géométrie — `domain/geometry.py`

- [x] `Vec2` (m) : `+`, `-`, `*`, norme, `dot`, `cross`, `rotate`, `angle`. `@dataclass(frozen=True, slots=True)`.
- [x] `Pose` (m, rad) : `position`, `heading_vector`, `compose`, `inverse`, `to_local(p)`, `to_world(p)`.
- [x] `normalize_angle(a)` dans (−π, π], `angle_diff(a, b)`, `shortest_rotation(a, b)`.
- [x] `domain/units.py` : `mm_to_m`, `deg_to_rad` et inverses, utilisés seulement aux bords (3.1).
- [x] Tests Hypothesis : `compose(p, inverse(p))` = identité, `normalize_angle` idempotent, `to_world(to_local(x)) == x`.

### 2.2 Modèle générique de la table — `domain/arena.py`

- [x] `Side(Enum)` : `BLUE`, `YELLOW`.
- [x] `ZoneKind(StrEnum)` générique : `START`, `END`, `FORBIDDEN`, `EXCLUSIVE_OPPONENT`, `CONSTRUCTION`, `STORAGE`, `OBSTACLE`, `OTHER`.
- [x] `Zone` : `id`, `kinds: frozenset[ZoneKind]` (ADR 0002), `owner: Side | None`, `polygon` (m), `height` (m), `tags: frozenset[str]`, `mirror_id`.
- [x] `ElementSpec` : `id`, `kind: str` (défini par l'édition), `pose`, `size`, `mirror_id`.
- [x] `Arena` : dimensions, épaisseur des bordures, zones, éléments, tags ArUco par côté ; `zones_of(kind, side)`, `zone(id)`, `contains(zone_id, point)`, `polygon_inside(zone_id, footprint)`.
- [x] Schéma msgspec de `arena.json` (mm et degrés, ADR 0002) et décodage `parse_arena(data)` ; une erreur nomme le champ et la valeur, et `app/files.py` y ajoute le fichier (ADR 0008).

### 2.3 Symétrie — `domain/symmetry.py`

- [x] `mirror_pose(pose, table_width)` : x → L − x, θ → π − θ, normalisé (9.5).
- [x] `mirror_zone_id`, `mirror_element_id` via `mirror_id`.
- [x] Tests : `mirror(mirror(p)) == p` (Hypothesis) ; chaque zone a un symétrique de même aire.

### 2.4 Table 2027 — `editions/cdr_2027/arena.json`

- [x] Plateau 3000 × 2000 mm, bordures 22 mm d'épaisseur et 70 mm de haut (RJ D.2).
- [x] Salles du trône 500 × 500 mm, aires de départ et d'arrivée (RJ D.3) : `START` + `END`.
- [x] Cours du château, remparts (murs 200 × 400 mm, tours Ø 200 mm), douves, écuries 200 × 300 mm, carrières (RJ D.4), relevés sur l'annexe du règlement (ADR 0004). La plateforme du calcul déporté (RG G) est hors de l'aire de jeu : non décrite (ADR 0002).
- [x] Remparts, cour et salle du trône adverses en `EXCLUSIVE_OPPONENT` : entrer dans une aire adverse à accès exclusif = forfait (RG H.4).
- [x] 30 pierres 320 × 110 × 110 mm, 3 par carrière (RJ D.4), avec leur `mirror_id`.
- [x] Tags ArUco : 1–5 bleu, 6–10 jaune (RG G.6), 13 sur les pierres (RJ D.4).
- [ ] Poses de fin candidates dans chaque salle du trône, robot entièrement dans la zone (RJ E.3). Une pose provisoire au centre de chaque salle ; reste à vérifier que l'empreinte réelle du robot y tient.
- [x] Test de chargement : symétrie de chaque zone, rien hors table, ids uniques.
- [ ] Relecture des coordonnées par une deuxième personne, plan de l'annexe à côté.

### 2.5 Barème et constantes de match

- [x] `editions/cdr_2027/scoring.json` : points de chaque action (RJ F, E.2.c, E.3.c). Aucun point dans le code.
- [x] Constantes génériques dans la config du socle (`config/match.json`) : durée 100 s (RG H.2), hauteur max 350 mm (RG F.3). La phase d'attaque à 85 s (RJ E.4) est une règle de l'année : dans `scoring.json` de l'édition (ADR 0005).

### 2.6 Format `cdr.strategy` — `domain/strategy_model.py`

- [x] Classes msgspec de la section 9.1 : `Strategy`, `Step`, `Move`, `Tolerance`, `Action`, `MoveMode(StrEnum)`, `OnTimeout` (`skip`, `abort`, `goto:<id>` parsé en type somme).
- [x] Conversion mm / deg → SI au chargement.
- [x] `mirror_strategy(strategy, arena)` : symétrie de chaque `move` et `element_id`, changement de `side`.
- [x] Validations statiques : `schema_version`, `kind`, ids d'étape uniques, cibles de `goto:` existantes, `element_id` connus, `actions[].type` enregistrés par l'édition, `not_before_s` ≤ 100. Les types d'action sont passés en paramètre jusqu'au registre (7.1) et à l'`Edition` (2.7) (ADR 0005).
- [x] `editions/cdr_2027/strategies/homologation.strategy.json` écrite à la main : sortir de la salle du trône, une action, revenir (RG I.3.b). Prise des pierres de `quarry_front_4` puis une tour ; poses d'approche provisoires.

### 2.7 Interface `Edition`

- [x] `Protocol` `Edition` (section 0) dans `app/edition.py` : `id`, `arena`, `scoring`, `rules` (ADR 0006). `register_actions` arrive avec le registre (7.1), `sim_elements` avec la simulation (11.1).
- [x] `MatchRules` générique dans `domain/match_rules.py` : `end_zones(side)`. `is_action_allowed` et `forbidden_zones` arrivent avec le `WorldSnapshot` (7.2).
- [x] Chargement par nom via `importlib` : `load_edition("cdr_2027")` appelle le `load()` du module et vérifie son `id`. `editions` est installé par le projet racine du workspace. Le nom sera lu dans la config en 9.1.

### 2.8 Machine à états du match — `domain/match_fsm.py`

- [x] `MatchState(Enum)` : `IDLE`, `INIT`, `READY`, `CALIBRATING`, `ARMED`, `RUNNING`, `ENDING`, `FINISHED`, `FAULT` (11.1).
- [x] `MatchEvent` : `LAUNCH`, `CHECKS_OK`, `CALIBRATE`, `ARM`, `DISARM`, `CORD_PULLED`, `END_BUDGET`, `T_END` ; `Fault(reason)` à part, avec sa raison (ADR 0007).
- [x] `transition(state, event) -> MatchState | Refused(reason)` avec une table explicite et `match` (ADR 0007). `T_END` termine aussi `RUNNING` (RG H.3) ; un nouveau `CALIBRATE` relance un recalage raté.
- [x] Depuis `ARMED`, seuls `DISARM` et `CORD_PULLED` ; `CORD_PULLED` ignoré dans tout autre état (RG F.6, faux départ RG H.4).
- [x] `FAULT` atteignable depuis tous les états non finaux, sortie seulement par relance manuelle : `FAULT` et `FINISHED` sont terminaux et refusent tout, une panne comprise, et la relance passe par une nouvelle exécution du brain (ADR 0007).
- [x] Test exhaustif : chaque paire (état, événement) a un résultat attendu.

---

## 3. Brain — ports et faux matériel

### 3.1 Horloge — `ports/clock.py`

- [x] `Clock` Protocol : `now()` (monotone, s), `async sleep(dt)`, `async sleep_until(t)`.
- [x] `SystemClock` dans `adapters/clock.py` (`time.monotonic`, `asyncio.sleep`) : `ports/` ne contient que les `Protocol` et `Watch` (ADR 0008, ADR 0010).
- [x] `FakeClock` dans `adapters/fake/clock.py` : `advance(dt)` réveille les `sleep` dans l'ordre et laisse les tâches réveillées tourner avant l'échéance suivante (ADR 0010).
- [x] `MatchClock` (domain, sans lecture d'horloge, ADR 0008) : créée à `t0`, `elapsed(now)`, `remaining(now)`, `in_phase(phase_id, now)` d'après `Scoring.phase_starts`. Une seule instance, créée à la tirette par le `MatchManager` (RG H.2).

### 3.2 `Watch[T]` — `ports/watch.py`

- [x] Dernière valeur + notification : `set(v)`, `get() -> T | None`, `async wait_next(timeout)`, `async wait_for(predicate, timeout)`. Timeouts comptés sur la `Clock` (ADR 0010).

### 3.3 `MotionPort`

- [x] Types dans `domain/motion.py` (ADR 0008, ADR 0010), copies en SI des messages de l'ADR 0003 : `MoveCommand` (`kind` : `MoveKind` `ROTATE_BY`, `ROTATE_TO`, `STRAIGHT`, `GOTO`, `PUSH_UNTIL_BLOCKED` ; `x`, `y`, `theta`, `distance`, `max_speed` et `max_accel` des translations, 0 = limite réglée ; `reverse` et `has_heading` d'un `GOTO`), `MotionState` (`MOVING`, `ARRIVED`, `BLOCKED`, `STOPPED`), `MotionStatus` (`move_id`, `state`, `pose`, `v`, `omega`, `vbat`, `teensy_time`, `boot_id`, `heartbeat` et les drapeaux `configured`, `emergency_stop`, `heartbeat_lost`, `vbat_missing`, `estop_sensor_missing`, `trace_running`), `StopMode` (`SMOOTH`, `URGENT`).
- [x] `MotionPort` : `async move(cmd) -> MotionStatus` (`move_id` attribué par le port, jamais 0), `async stop(mode)`, `async set_max_speed(max_speed) -> bool` (renvoi du `GOTO` en cours, ADR 0003), `async heartbeat()`, `async reset_pose(pose)`, `status() -> Watch[MotionStatus]`, `link_ok()`. Contrat dans l'ADR 0010 : un mouvement à la fois, annuler `move()` arrête le robot, `stop` n'attend jamais la Teensy.

### 3.4 Autres ports

- [x] `ActuatorPort` : `async command(actuator_id, position_name, timeout) -> ActuatorResult` (`DONE`, `BLOCKED`, `TIMEOUT`), `async release_all(final)` (`final` verrouille le port comme `stop(URGENT)`, ADR 0011), `state(actuator_id)`, `sensor(name) -> Watch[bool]`.
- [x] `LidarPort` : `tracks() -> Watch[TrackSet]` ; `Track(id, center, radius, velocity, confirmed)` et `TrackSet` dans `domain/world.py` (ADR 0008).
- [x] `RemoteVisionPort` : `observations() -> Watch[RemoteObservations]`, `async send(event)` (types provisoires, ADR 0011).
- [x] `StartSwitchPort` : `inserted()`, `async wait_pulled() -> float` (instant du premier front, `t0` du match, ADR 0011).
- [x] `TelemetryPort` : `publish(topic, msg)` non bloquant, jeté si personne n'écoute.
- [x] BAU lu via `MotionStatus.emergency_stop`, pas de port séparé.
- [x] `Ports` : dataclass qui regroupe tous les ports, horloge comprise (`ports/__init__.py`, ADR 0011).

### 3.5 Faux matériel — `adapters/fake/`

- [x] `FakeMotion` : exécution idéale avec une durée calculée (vitesse, accélération), limites ramenées aux réglages comme sur la Teensy (ADR 0003) ; scénarios injectables : blocage après x m, Teensy muette, redémarrage, BAU.
- [x] Tests de contrat du `MotionPort` (ADR 0010), communs à `FakeMotion`, `SimMotion` (11.2) et à l'adaptateur Teensy (15.1) : annuler `move()` arrête le robot, second `move()` refusé, `stop()` et `heartbeat()` sans exception même lien mort, `stop(SMOOTH)` freiné à `MAX_ACCEL` réglé quel que soit le `max_accel` du mouvement, `stop(URGENT)` définitif (enregistré avant le premier `await`, heartbeat maintenu), `set_max_speed()` qui ralentit un `GOTO` sans l'arrêter et ne relance jamais un mouvement arrêté, `reset_pose()` refusé robot en mouvement.
- [x] `FakeActuators` : durées fixes, taux d'échec réglable.
- [x] `FakeLidar` : pistes scriptées dans le temps.
- [x] `FakeStartSwitch` : `pull()` déclenché par le test.
- [x] Fixtures pytest `ports`, `clock`, `arena`, `strategy` dans `tests/conftest.py` (édition `_template`), avec `FakeRemoteVision` et `FakeTelemetry`.

---

## 4. Brain — modèle du monde

- [x] `Source(StrEnum)` : `ODOMETRY`, `LIDAR`, `REMOTE`, `STRATEGY`, `CONFIG`.
- [x] `Observed[T]` (5.5) : `value`, `stamp`, `source`, `age(now)`, `is_fresh(now, ttl)`.
- [x] `ElementState` générique : `present`, `taken`, `placed_at`, `carried_by_us`, `confidence`, `tags` (ADR 0012).
- [x] `WorldSnapshot` (`domain/world.py`, comme tout le modèle du monde, ADR 0008) : `t`, `robot_pose`, `robot_velocity`, `opponents`, `our_elements` et `seen_elements` lus par `element(id)`, `our_constructions`, `carrying`, `remote`, `lidar_alive`, `remote_alive` (ADR 0012).
- [x] `WorldModel`, seul à écrire : `update_odometry`, `update_tracks`, `update_remote`, `mark_element`, `add_construction`, `snapshot(now)` en O(1). Pas de lecture d'horloge : chaque mise à jour porte sa date, le snapshot reçoit l'heure. Un snapshot n'est jamais modifié après coup (nouvelles collections à chaque mise à jour).
- [x] Durées de vie dans `robot.json` (pistes lidar 0,3 s, calcul déporté 0,3 s, éléments vus 2 s, historique d'odométrie 2 s) : section `world`, décodée par `app/config.py` (ADR 0012).
- [x] Règles de fusion explicites : lidar pour l'évitement, calcul déporté pour identifier les robots (`Track.confirmed`, 16.2) et l'état des éléments (vue fraîche et plus récente que notre état, ADR 0012). Lien tag → élément : voir les Points à valider.
- [x] Historique d'odométrie sur 2 s, `pose_at(t)` par interpolation (8.3), sans extrapolation : `PoseHistory`, réutilisable par `dvb-lidar`.
- [x] Tests : vieillissement, snapshot non modifié après une mise à jour, interpolation.

---

## 5. Brain — navigation

### 5.1 Carte de navigation — `domain/navmap.py`

- [ ] Obstacles statiques depuis `Arena` : bordures, `FORBIDDEN`, `EXCLUSIVE_OPPONENT`, éléments fixes, nos constructions.
- [ ] Gonflage `shapely.buffer(robot_radius + margin)`, marge de 20 mm dans la config (8.1).
- [ ] Espace libre = table réduite du rayon du robot.
- [ ] Obstacles dynamiques : un disque gonflé par piste adverse.
- [ ] Zones interdites conditionnelles de `MatchRules.forbidden_zones(world)`.

### 5.2 Planificateur — `domain/planner.py`

- [ ] Nœuds : sommets des obstacles gonflés simplifiés, départ, arrivée.
- [ ] Arêtes : segment entièrement dans l'espace libre (tester les cas de tangence).
- [ ] Partie statique précalculée ; recalcul seulement quand `our_constructions` change.
- [ ] A\* (`heapq`), heuristique euclidienne, coût = longueur + pénalité par virage (réglable).
- [ ] Départ dans un obstacle gonflé → projection sur le bord libre le plus proche ; arrivée dans un obstacle → `None` avec la raison.
- [ ] `Path` : points, longueur, `estimated_duration(speed, accel, rot_speed)`.
- [ ] Tests Hypothesis : aucun segment ne coupe un obstacle ; chemin trouvé quand une grille fine en trouve un.
- [ ] Benchmark sur la table 2027 avec 2 adversaires, objectif < 10 ms sur la Pi 5 ; sinon `asyncio.to_thread` (8.2).

### 5.3 Chemin → mouvements — `domain/motion_plan.py`

- [ ] `Path` + `MoveMode` + `theta` final optionnel → un `GOTO` par point, `REVERSE` selon le mode, `HAS_HEADING` au dernier point si `theta` est donné (9.4, ADR 0003, ADR 0010).
- [ ] Mode `auto` : marche arrière seulement sous `reverse_max_distance` et si le gain de rotation dépasse `reverse_min_gain`.
- [ ] Vitesse de marche arrière plafonnée (lidar 270°, rien derrière).
- [ ] Tests par table de cas.

### 5.4 Service `Navigator` — `services/navigator.py`

- [ ] `async go_to(target, deadline) -> NavResult` (`ARRIVED`, `BLOCKED_BY_OPPONENT`, `NO_PATH`, `TIMEOUT`, `MOTION_FAULT`).
- [ ] Envoi des `MoveCommand` un par un, vérification de la tolérance en position et en angle à l'arrivée (9.3).
- [ ] Attentes bornées sur la `Clock`, jamais par `asyncio.timeout` ni `asyncio.wait_for`, que `FakeClock` ne fait pas avancer : outil commun tiré de `Watch._next` (ADR 0010).
- [ ] Cible absolue conservée lors d'une replanification.
- [ ] `push_until_blocked(direction, max_dist)` et `recalibrate(wall)` : `RESET_POSE` avec la coordonnée et l'angle de la bordure, l'autre coordonnée gardée (7.2) ; attendre un statut autre que `MOVING` avant `reset_pose` (ADR 0010).
- [ ] Tests avec `FakeMotion` et `FakeClock`.

---

## 6. Brain — évitement

### 6.1 Zone de sécurité — `domain/safety_zone.py`

- [ ] `stopping_distance(v, decel, reaction_time)` = v · t + v² / (2 · décel), t ≈ 0,13 s (8.4).
- [ ] Rectangle devant le robot dans le sens de marche (largeur robot + marge, longueur arrêt + marge).
- [ ] Cercle de rayon `robot_radius + margin` pendant une rotation sur place.
- [ ] Mode réduit près d'un élément ou de nos constructions : zone raccourcie et vitesse réduite, jamais supprimée.
- [ ] Masquage des pistes sur nos constructions (+ quelques cm).
- [ ] Tests : v = 0,3 m/s → ≈ 85 mm et v = 0,5 m/s → ≈ 190 mm avant marge avec 1 m/s² ; adversaire juste dans / juste hors de la zone.

### 6.2 Service `Avoidance` — `services/avoidance.py`

- [ ] Tâche à la fréquence des pistes, lecture du snapshot.
- [ ] Obstacle dans la zone → `stop(SMOOTH)` immédiat + événement `ObstacleStop`.
- [ ] Obstacle plus loin sur la trajectoire → vitesse max réduite par `MotionPort.set_max_speed` (renvoi du `GOTO` en cours, ADR 0003, ADR 0010), seulement quand la vitesse plafond change : chaque renvoi remet à zéro la détection de blocage de la Teensy.
- [ ] Lidar muet depuis 300 ms → arrêt et aucun départ tant qu'il ne revient pas (8.5).
- [ ] En profil `match`, la config refuse toute désactivation de l'évitement (désactivation volontaire = forfait, RG H.4).

### 6.3 Réaction du `Navigator`

- [ ] Sur `ObstacleStop` : attente jusqu'à `wait_s` (1,5 s).
- [ ] Toujours bloqué → replanification avec l'adversaire en obstacle ; 3 échecs ou pas de chemin → `BLOCKED_BY_OPPONENT`.
- [ ] Jamais de passage en force.
- [ ] Scénarios : adversaire qui traverse puis part, adversaire immobile sur la cible, adversaire qui suit le robot.

---

## 7. Brain — stratégie et règles de l'édition

### 7.1 Registre d'actions

- [ ] `ActionRegistry` (socle) : `register(type_name, handler)`, `get(type_name)`.
- [ ] Handler : `async (ctx: ActionContext, action: Action) -> ActionResult` ; contexte = actionneurs, monde, navigator, horloge.
- [ ] `ActionResult` : `DONE`, `FAILED(reason)`, `SKIPPED(reason)`, plus les mises à jour du monde.
- [ ] Actions génériques `wait` et `noop` dans le socle.
- [ ] `Edition.register_actions(registry)` (ADR 0006) ; le test des stratégies 2027 lit les types d'action dans le registre.
- [ ] Actions 2027 dans `editions/cdr_2027/actions.py` : `pick_stones`, `build_wall`, `build_tower`, `build_gate`, `raise_grail`, `shoot_balls`, d'abord avec des séquences plausibles, puis les séquences réelles quand les mécanismes sont figés.

### 7.2 Garde-fous du règlement — `editions/cdr_2027/rules.py`

- [ ] `MatchRules.is_action_allowed(action, world, t)` et `MatchRules.forbidden_zones(world)` dans le socle, avec le `WorldSnapshot` de la section 4, qui doit donc être dans `domain/` (ADR 0006).
- [ ] Vol de pierres refusé tant qu'une carrière n'est pas vide, et jamais en détruisant le château adverse (RJ E.1).
- [ ] Au plus 3 pierres stockées dans notre cour (RJ E.1).
- [ ] Graal porté → interdit de sortir de la cour et des remparts ; Graal adverse jamais déplacé (RJ E.2.b).
- [ ] Tirs de boulets refusés avant 85 s (RJ E.4).
- [ ] Élément porté au-dessus de 350 mm seulement en zone de construction et dans le château ; actionneur jamais au-dessus de 350 mm (RG F.3, RJ E.2.b).
- [ ] Un test par règle avec un `WorldSnapshot` construit à la main.

### 7.3 `StrategyExecutor` — `services/strategy_executor.py`

- [ ] Boucle : `go_to(move)` → attente `not_before_s` → actions dans l'ordre → étape suivante (9.3).
- [ ] `timeout_s` couvre déplacement, attente et actions ; `on_timeout` : `skip`, `abort`, `goto:<id>` (une fois par saut).
- [ ] Écarts autorisés sans changer l'ordre : contourner, attendre, sauter une étape impossible, ajuster dans la tolérance ; chaque écart loggé avec sa raison.
- [ ] `BLOCKED_BY_OPPONENT` traité comme un timeout de l'étape.
- [ ] Exposition de `current_step`, `progress`, `score_estimate`.

### 7.4 Fin de match — `services/endgame.py`

- [ ] Calcul continu du temps de retour (planificateur) + `end_reserve_s`.
- [ ] Temps restant atteint → annulation de l'étape, `release_all(final=False)`, actionneurs rentrés, retour en salle du trône (RJ E.3).
- [ ] Pose de fin avec l'empreinte entièrement dans la zone (10 pts au lieu de 5, RJ E.3.c), autre pose candidate si la première est occupée.
- [ ] Plus rien tenu par un actionneur à la fin (RJ E.2.b) ; Graal au niveau 4 libre de tout actionneur.
- [ ] Test : stratégie trop longue → fin dans la zone avant 100 s sur 20 graines.

---

## 8. Brain — match et sûreté

### 8.1 `MatchManager` — `services/match_manager.py`

- [ ] `INIT` : attente des liens, vérification du profil `match` et de l'absence de ressource simulée (4.5).
- [ ] `INIT` : envoi des 17 réglages d'asservissement (5.6) à la Teensy moteur, un `SET_CONTROL_PARAMS` par réglage, puis attente de `MotionStatus.configured` ; méthode du `MotionPort` à ajouter (ADR 0003, ADR 0010) (attend 12.1).
- [ ] `CALIBRATING` : recalage contre deux bordures puis `RESET_POSE`, objectif < 30 s (préparation de 3 min, RG H.1) ; robot entièrement dans la salle du trône ensuite (RJ D.3.b). Un nouveau `CALIBRATE` recommence un recalage raté (ADR 0007).
- [ ] `ARMED` : tirette en place exigée, seul le front « retirée » compte (anti-rebond dans l'adaptateur, 15.3).
- [ ] `RUNNING` : `MatchClock` créée au front (ADR 0010), envoi du départ au calcul déporté (× 3), lancement de l'exécuteur et de la fin de match.
- [ ] Minuteur de fin indépendant de la stratégie : à 100 s moins `hard_stop_margin_s`, `stop(URGENT)`, `release_all(final=True)`, plus aucune commande (RG H.3 ; −50 pts si le robot bouge encore, RG H.4).

### 8.2 `SafetyMonitor` — `services/safety.py`

- [ ] Première tâche du `TaskGroup` (5.3), heartbeat 20 Hz vers la Teensy moteur par `MotionPort.heartbeat()`, maintenu après `stop(URGENT)` (ADR 0010).
- [ ] Surveillance : statut absent depuis 300 ms, `boot_id` changé, port série en erreur, BAU, heartbeat perdu vu par la Teensy (`heartbeat_lost`), boucle asyncio en retard de plus de 100 ms.
- [ ] Réaction unique : `stop(URGENT)`, `release_all(final=True)` (ADR 0011), `FAULT(reason)` ; jamais de relance automatique d'un match.
- [ ] `run_brain` avec `finally` qui tente `stop(URGENT)` et `release_all(final=True)` même si les ports sont morts.
- [ ] `SIGTERM` et `SIGINT` → même arrêt propre.
- [ ] Tests : exception dans une action, Teensy muette, BAU → `FAULT` et `stop` appelé.

### 8.3 Vérifications avant d'armer

- [ ] Checks : Teensy moteur, actionneurs, lidar frais, pose recalée, côté choisi, stratégie valide pour ce côté, tirette en place, V_bat du statut au-dessus du seuil, aucune ressource simulée. En profil `match`, refus si le statut signale un capteur absent (`vbat_missing`, `estop_sensor_missing`, ADR 0003).
- [ ] Refus d'armer si un check échoue, raison en clair.

---

## 9. Brain — configuration, composition et logs

### 9.1 Configuration — `app/config.py`, `config/robot.json`

- [ ] Schéma msgspec (5.6), qui étend celui de la case 4 (section `world`) : `edition`, `profile`, géométrie du robot (rayon, empreinte, position et hauteur du lidar), numéros de série des Teensy, navigation, évitement, durées de vie, asservissement, actionneurs, réel / simulé / désactivé par sous-système. Décodé vers des dataclasses SI de `domain/`, que reçoivent les services (ADR 0008).
- [ ] Chargement au lancement, jamais à l'import.
- [ ] Validations croisées : profil `match` ⇒ tout réel sauf le calcul déporté, évitement actif.
- [ ] Hauteur de chaque position nommée d'actionneur, déclarée dans la config (l'angle d'un servo ne la donne pas) : au-dessus de la hauteur max de `config/match.json` (RG F.3), la config est refusée ; une hauteur inconnue est marquée et refusée en profil `match` (ADR 0011).
- [ ] Erreur lisible qui nomme le champ (`navigation.avoidance.wait_s: expected >= 0, got -1`).
- [ ] Valeurs encore inconnues marquées explicitement, refusées en profil `match`.

### 9.2 Composition — `app/main.py`

- [ ] `build_ports(cfg) -> Ports` selon le profil (`match`, `test`, `sim`, `replay`) : seul endroit qui sait quel adaptateur est branché. Les adaptateurs réels s'y ajoutent avec la section 15.
- [ ] `run_brain(ports, cfg)` avec `asyncio.TaskGroup`.
- [ ] Tâche qui remplit le `WorldModel` depuis les ports : statuts de `MotionPort.status()` datés sur la `Clock` du brain, pistes du lidar, observations du calcul déporté (ADR 0012).
- [ ] Édition chargée au lancement par `load_edition(cfg.edition)`, ses actions enregistrées ; les services reçoivent ses morceaux, jamais l'`Edition` (ADR 0006).
- [ ] Commande `dvb-brain --config --profile --strategy --side`.
- [ ] Tirette virtuelle en profil `test` uniquement (4.5).

### 9.3 Logs — `app/logging_setup.py`

- [ ] `logging` standard, format `t | LEVEL | logger | event_id | key=value` (13).
- [ ] Helper `log_event(logger, event_id, **fields)`.
- [ ] Dossier par lancement : `logs/<date>_<side>_<strategy>/` avec `brain.log`, `config.json`, `strategy.json`.
- [ ] `QueueHandler` + `QueueListener` : aucune écriture disque dans la boucle asyncio.
- [ ] Événements obligatoires : étapes (pose visée / atteinte, erreur, durée, raison de sortie), commandes Teensy et réponses, décisions de navigation, changements d'état du match.
- [ ] Suppression automatique des plus vieux lancements de profil `test`, jamais de profil `match`.
- [ ] CLI `dvb-logs` : filtre par logger, événement, plage de temps.

---

## 10. Bus local entre processus

- [ ] `packages/common_msgs` : messages msgspec (msgpack) avec `source`, `seq`, `t_ms` (5.2).
- [ ] `zmq.asyncio` PUB/SUB sur `ipc://` pour les flux continus (dernière valeur seulement), REQ/REP pour les commandes du superviseur.
- [ ] Heartbeat de chaque processus toutes les 100 ms.
- [ ] Le brain publie odométrie (historique daté), état du match et télémétrie.
- [ ] Tests d'intégration : deux processus sur le bus, perte d'un éditeur détectée.

---

## 11. Simulation

### 11.1 Monde simulé — `packages/sim`

- [ ] Pas de temps fixe (5 ms), temps simulé ou réel, graine fixée.
- [ ] État : notre robot, adversaires, éléments de jeu (`Edition.sim_elements()`), score estimé.
- [ ] Collisions comptées.
- [ ] `Edition.sim_elements()` : type `SimElements` du socle, implémenté par chaque édition (ADR 0006).

### 11.2 Base roulante simulée

- [ ] `SimMotion` Python implémentant `MotionPort` : trapèze avec les paramètres d'asservissement, bruit d'odométrie, glissement, blocage contre un obstacle, pannes injectables.

### 11.3 Lidar simulé

- [ ] Raccourci `SimLidarTracks` (pistes vraies + bruit) tant que `dvb-lidar` n'existe pas.
- [ ] Lancer de rayons 270°, fréquence et résolution du TiM561, bruit, trous, coupures.
- [ ] Sortie dans le même format UDP que le container lidar (attend 16.1).

### 11.4 Adversaires et actionneurs

- [ ] Adversaires : `Static`, `RandomWalk`, `Blocker`, `Mirror`, `Scripted(path)`, rayon et vitesse réglables.
- [ ] Actionneurs : durées de la config, taux de réussite réglable, effet sur les éléments.

### 11.5 Scénarios de match en CI — `tests/scenarios/`

- [ ] Matrice 2 côtés × 4 adversaires × 5 graines pour chaque stratégie de `strategies/`.
- [ ] Assertions : aucune collision, aucune entrée en `EXCLUSIVE_OPPONENT`, arrêt avant 100 s, fin entièrement dans la salle du trône, sortie de zone + une action réussie (RG I.3.b).
- [ ] Moins de 2 min en CI ; job obligatoire pour les PR qui touchent `domain/`, `services/` ou `editions/` ; étape `uv run` ajoutée aux contrôles de `review_gate.py stamp` (ADR 0009).
- [ ] Rapport par scénario en artefact CI.

---

## 12. Contrats Teensy et usb_com v2

### 12.1 Contrat brain ↔ Teensy moteur — `docs/adr/0003-motion-protocol.md`

Écrit à partir du firmware moteur actuel et des attentes du brain : contrat de `MotionPort` et points à valider de l'ADR 0010. Accepté le 2026-11-19 dans l'ADR 0003 ; le brain le suit (ADR 0010).

- [x] Contenu exact de `HEARTBEAT`, `MOVE`, `STOP`, `RESET_POSE`, `MOTION_STATUS`, `SET_CONTROL_PARAMS`, `START_TRACE`, `TRACE_SAMPLE`, `TRACE_END` (6.2) : champs, types, unités, IDs.
- [x] Fréquences : heartbeat 20 Hz, statut 20 Hz à cadence fixe, arrêt de la Teensy après 200 ms sans heartbeat.
- [x] Sémantique d'un `MOVE` reçu pendant un autre ou pendant le freinage d'un `STOP` (`FakeMotion` le lance une fois le robot arrêté, ADR 0011), et de la vitesse max modifiée en cours de mouvement.
- [x] `STOP` normal freiné à `MAX_ACCEL` réglé, même valeur que `avoidance.decel` de la zone de sécurité, quel que soit le `max_accel` du `MOVE` en cours (21.1 ; écart 1 relevé par l'ADR 0010).
- [x] Comportements du firmware écrits dans l'ADR : `STOP` normal sans effet moteurs libres (après un `STOP` urgent, un BAU ou la perte du heartbeat) jusqu'au prochain `MOVE`, `MOVING` jusqu'à la fin du freinage, `MOVE` reçu pendant un freinage lancé une fois le robot arrêté (écart 2 relevé par l'ADR 0010).
- [x] Propositions de l'ADR 0010 tranchées : ignorer un `MOVE` qui reprend le `move_id` d'un mouvement fini (écart 4), garder la détection de blocage quand un `MOVE` continue le mouvement en cours (écart 5) : écartées.
- [x] Redémarrage de la Teensy détectable (`boot_id`) ; Teensy inerte tant qu'elle n'a pas reçu ses réglages.
- [x] ADR relu et approuvé côté firmware et côté brain avant d'en coder les messages (cases 12.3 et 13.4).

### 12.2 Contrat brain ↔ Teensy actionneurs — ADR dans `docs/adr/`

Écrit à partir des attentes du brain : `ActuatorPort` tel que le décrit la case 3.4, et l'architecture (10).

- [ ] Messages des commandes génériques (10) : servo à un angle, pas-à-pas à une position, sortie tout-ou-rien, lecture de capteur, à partir des messages actionneurs existants (6.2) ; réponses « fini », « bloqué », « timeout » ; sur un timeout, l'actionneur s'arrête où il est (ADR 0011).
- [ ] État et fins de course à 20 Hz, heartbeat et `boot_id` comme la Teensy moteur, posture par défaut sur perte du heartbeat, sauf après un relâchement final : tout reste relâché (ADR 0011).
- [ ] ADR relu et approuvé côté firmware et côté brain avant d'en coder les messages (cases 12.3 et 14).

### 12.3 usb_com v2 (C++ et Python)

- [x] Découpage COBS (`0x00` en fin de message) à la place de la signature de 4 octets (6.2).
- [x] CRC-16 à la place du CRC-8, même variante des deux côtés, documentée.
- [x] Trame : `[msg_id u8][payload N][len u8][crc16 u16]` puis COBS puis `0x00`.
- [x] Index de réception sur 16 bits, contrôle de la taille avant copie.
- [ ] Un seul écrivain côté Python (file asyncio).
- [x] Plages d'ID inchangées : 0–127 Pi → Teensy, 128–255 Teensy → Pi, 127 = NACK.
- [x] Nouveaux messages du contrat moteur (case 12.1), dans `messages.h` et `messages.py`.
- [ ] Nouveaux messages du contrat actionneurs (case 12.2), dans `messages.h` et `messages.py`.
- [ ] Teensy reconnue par son numéro de série.
- [x] CI : vérification que `messages.h` et `messages.py` ont les mêmes ID et tailles.
- [x] Tests aller-retour Python ↔ C++ (codec compilé sur PC), avec trames abîmées, tronquées et concaténées.

---

## 13. Firmware Teensy moteur — `firmware/teensy_motor`

### 13.1 Bibliothèque de contrôle portable

- [x] Correcteurs, générateur, odométrie et détection de blocage sans accès matériel, compilés en `teensy41` et `native` (7.1).
- [x] Tests `pio test -e native` de chaque brique.

### 13.2 Mesure et commande

- [ ] Lecture des roues codeuses AMT102-V par les décodeurs de quadrature de la Teensy.
- [ ] Commande PWM + DIR à 30–40 kHz, en tension, compensée par V_bat mesurée.
- [x] Deux PI de vitesse de roue.
- [x] P + anticipation sur distance et angle, répartition sur les roues.
- [x] Générateur de trapèze pour chaque mouvement.
- [x] Deux positions : parcours depuis le début du mouvement (boucles) et position absolue (recalée par `RESET_POSE`, éventuellement `CORRECT_POSE` plus tard).
- [x] Détection de blocage remontée dans le statut.
- [x] Mouvements : tourner (angle ou cap), avancer / reculer, aller à un point, pousser jusqu'au blocage, avec identifiant et statut.

### 13.3 Sûreté

- [x] Arrêt (décélération) après 200 ms sans `HEARTBEAT`.
- [x] `STOP` normal par le générateur, `STOP` urgent : commande et intégrateurs à zéro.
- [ ] Robot inerte tant que les réglages n'ont pas été reçus ; drivers à l'arrêt tant que le programme n'a pas démarré (R8).
- [ ] Détection du BAU (R2), commande et intégrateurs à zéro, état remonté dans `MOTION_STATUS`.
- [x] Identifiant de démarrage (`boot_id`) dans le statut.

### 13.4 Communication et réglage

- [x] `MOTION_STATUS` à fréquence fixe (≥ 10 Hz), indépendante des tours de `loop()`.
- [x] `SET_CONTROL_PARAMS` : gains et paramètres du générateur à chaud.
- [x] `START_TRACE` (échelon de tension en boucle ouverte ou de consigne en boucle fermée), `TRACE_SAMPLE`, `TRACE_END` avec les réglages réellement utilisés.
- [x] Messages `PRINT` réservés au debug, désactivables.

### 13.5 Teensy virtuelle

- [ ] Bibliothèque de contrôle (case 13.1) compilée en `native`, sur un pseudo-terminal (`pty`), avec le vrai protocole (case 12.3) et le watchdog (12.1).
- [ ] Option « débrancher » : couper le pseudo-terminal à la demande, pour tester la perte du lien (case 15.1).

---

## 14. Firmware Teensy actionneurs — `firmware/teensy_actuators`

- [ ] Commandes génériques seulement : servo à un angle, pas-à-pas à une position, sortie tout-ou-rien, lecture de capteur (10).
- [ ] Servos avec rampes, pas-à-pas non bloquants (AccelStepper ou TeensyStep), aucun `delay()` dans les callbacks.
- [ ] Prise d'origine au démarrage et après un BAU.
- [ ] Butées logicielles, dont la hauteur de 350 mm (RG F.3).
- [ ] Posture par défaut sur perte du heartbeat (`hold` ou `release` par actionneur), sauf après un relâchement final : tout reste relâché (ADR 0011).
- [ ] État et fins de course remontés à 20 Hz.
- [ ] Heartbeat et `boot_id` comme la Teensy moteur.
- [ ] Tests `native` de la logique de séquencement.

---

## 15. Brain — adaptateurs réels

### 15.1 Teensy moteur — `adapters/teensy/motion.py`

- [ ] Lecture asynchrone (`pyserial-asyncio-fast`) au-dessus d'usb_com v2, un seul écrivain.
- [ ] Port trouvé par numéro de série (`/dev/dvb-motor`), reconnexion automatique ; un lien perdu en match reste un `FAULT`.
- [ ] Conversion des types du brain (`MoveCommand`, `MotionStatus`) vers les messages de l'ADR 0003 dans cet adaptateur et nulle part ailleurs : ID, octet de drapeaux, `float`.
- [ ] `move()` : `move_id` attribué sur 16 bits, qui boucle sans repasser par 0, `Future` résolu par le `MOTION_STATUS` correspondant ; `set_max_speed()` renvoie le `GOTO` en cours avec le même `move_id` ; `reset_pose()` confirmé à la précision du fil près (`float`, θ modulo 2π).
- [ ] `PRINT` → `brain.log` sous `hardware.teensy`.
- [ ] Tests contre la Teensy virtuelle sur `pty` (case 13.5), trames abîmées et débranchement compris ; tests de contrat du `MotionPort` (3.5).

### 15.2 Teensy actionneurs — `adapters/teensy/actuators.py`

- [ ] Commandes par nom traduites via `robot.json` (positions nommées, vitesses, limites).
- [ ] Hauteur (RG F.3) : le port ne reçoit ni pose ni zone ; positions nommées au-dessus de 350 mm refusées au chargement de la config (9.1), règle selon la zone dans `MatchRules` (7.2), avant l'appel (ADR 0011).
- [ ] Mode réglage : position libre puis « enregistrer comme `<nom>` » dans la config.

### 15.3 Tirette et LED — `adapters/gpio.py`

- [ ] `gpiozero` avec la pin factory `lgpio` (RPi.GPIO ne fonctionne pas sur la Pi 5).
- [ ] Anti-rebond 50 ms, lecture seulement en `ARMED`.
- [ ] Banc d'essai : 50 retraits de tirette, aucun faux départ, latence front → `RUNNING` loggée.

### 15.4 Lidar et calcul déporté côté brain

- [ ] Adaptateur `LidarPort` abonné aux pistes de `dvb-lidar` sur le bus.
- [ ] Adaptateur `RemoteVisionPort` abonné à `dvb-net`.

---

## 16. Lidar

### 16.1 Container — `lidar_driver/`

- [ ] Image Docker Ubuntu + ROS 2 + pilote du TiM561, construite de façon reproductible (versions figées).
- [ ] Export UDP local de chaque balayage, daté de l'instant de la mesure (`header.stamp`), dans une horloge comparable à celle du brain.
- [ ] Angles calculés depuis `angle_min` et `angle_increment` du `LaserScan`.
- [ ] Format binaire documenté (en-tête + tableau float32) plutôt que du JSON.
- [ ] Ports UDP sans conflit entre l'émetteur et le récepteur.
- [ ] Politique de redémarrage Docker, temps de démarrage mesuré (prêt avant la fin de la checklist).
- [ ] CPU du container mesuré sur la Pi.

### 16.2 Processus `dvb-lidar` — `packages/lidar`

- [ ] Réception et décodage UDP.
- [ ] Placement de chaque balayage avec `pose_at(t_mesure)` (historique d'odométrie du bus).
- [ ] Pipeline numpy vectorisé (8.3) : filtrage hors table, sur notre robot, sur les éléments fixes et nos constructions ; regroupement ; centre et taille ; suivi (naissance après 2 balayages, disparition après 0,5 s).
- [ ] Confirmation des pistes par les tags ArUco adverses du calcul déporté (1–5 ou 6–10, RG G.6).
- [ ] Publication des `TrackSet` sur le bus.
- [ ] Enregistrement de balayages réels sur la table (robot immobile, adversaire qui passe) pour le rejeu en CI (12.2).
- [ ] Test de rejeu : mêmes adversaires détectés sur les enregistrements.

---

## 17. Calcul déporté — `packages/net`

- [ ] Réception UDP broadcast des observations ArUco datées, rejet des paquets trop vieux ou désordonnés (`seq`).
- [ ] Envoi UDP : couleur, départ du match (× 3), pose estimée à 10 Hz.
- [ ] Publication sur le bus.
- [ ] Observations → `WorldModel.mark_element(..., REMOTE)` : quel tag sur quel élément, une fois le format validé (ADR 0012).
- [ ] chrony sur la Pi, serveur NTP pour le calcul déporté.
- [ ] Format des messages documenté dans un ADR commun aux deux dépôts.

---

## 18. Superviseur — `packages/supervisor`

- [ ] FastAPI + uvicorn (1 worker) : `/api/brain/{start,stop,status}`, `/api/logs`, `/api/config`, `/api/strategies`, `/ws/telemetry`.
- [ ] Lancement du brain via `dvb-brain@<profil>.service`, jamais en sous-processus direct.
- [ ] Pont bus → WebSocket en msgpack, 30 Hz max, messages jetés si le navigateur est lent.
- [ ] Robot armé = API en lecture seule, sauf « désarmer » (4.3).
- [ ] Téléop : commande renouvelée toutes les 200 ms, sinon arrêt.
- [ ] Modèles Python → JSON Schema → types TypeScript générés en CI.
- [ ] `CPUQuota` dans l'unité systemd.

---

## 19. Dashboard — `dashboard/`

### 19.1 Socle

- [ ] React + TypeScript strict + Vite + Zustand, pnpm, ESLint, Vitest.
- [ ] Client WebSocket typé, reconnexion automatique, bandeau « déconnecté ».
- [ ] Bandeau permanent : état du match, ressources simulées, erreurs.
- [ ] Composant `TableView` en Canvas 2D dessiné depuis `arena.json`.
- [ ] Build en CI ; seul `dist/` va sur la Pi.

### 19.2 Écrans, dans cet ordre

- [ ] Match (téléphone) : côté, stratégie, checklist, bouton Armer, chrono, étape en cours, raison du dernier `FAULT`. Utilisable à une main en moins de 10 s.
- [ ] Carte live : robot, trajet prévu, étape, points lidar, pistes adverses et leur âge, éléments, zones interdites.
- [ ] Logs : direct, filtres, liste des lancements, téléchargement, suppression.
- [ ] Santé : appareils (dernier message, latence, version firmware), processus et container (CPU, mémoire, latence de boucle), température, disque, Wi-Fi, commit installé.
- [ ] Test / téléop : commandes unitaires, enchaînements, pavé directionnel « maintenir pour bouger ».
- [ ] Asservissement : courbes uPlot consigne / mesure, lancement d'essais, gains à chaud puis sauvegardés, export CSV (attend 12.1).
- [ ] Configuration : édition validée côté serveur, réel / simulé / désactivé.
- [ ] Maintenance : flasher les Teensy (`teensy_loader_cli`), redémarrer les services, éteindre la Pi.
- [ ] Stratégies (9.6) : édition sur carte, trajet par le vrai planificateur, alertes, frise 100 s avec 85 s et réserve, symétrie, simulation accélérée, « jouer à partir de cette étape », enregistrement validé.

---

## 20. Déploiement sur la Pi — `deploy/`

- [ ] Raspberry Pi OS, Python 3.14 installé par uv.
- [ ] Unités systemd : `dvb-supervisor` (`Restart=always`), `dvb-brain@.service`, `dvb-lidar`, `dvb-net`, container lidar ; `Nice=-5` pour brain et lidar.
- [ ] nginx : sert `dist/`, relaie `/api` et `/ws`.
- [ ] Règles udev : `/dev/dvb-motor`, `/dev/dvb-act` par numéro de série.
- [ ] NetworkManager : client Wi-Fi 6E (WPA3-SAE), point d'accès 5 GHz atelier, profil Internet activé à la main (4.4).
- [ ] Avahi pour `dvb.local`.
- [ ] Script `deploy/install.sh` idempotent.
- [ ] Mise à jour du code à la main par `git pull`, jamais depuis le dashboard.

---

## 21. Intégration, homologation, compétition

### 21.1 Mesures sur table

- [ ] Décélération réelle de la base → `avoidance.decel`.
- [ ] Dérive d'odométrie sur un parcours de 100 s → décision sur les recalages en cours de match (ADR).
- [ ] Temps de planification et CPU par processus sur la Pi (< 50 % au total, aucun cœur > 80 %).
- [ ] Temps du recalage automatique (< 30 s).
- [ ] Ce que voit le lidar à sa hauteur : murs, tours, portes, PAMI, pierres.

### 21.2 Homologation (RG I.3)

- [ ] Stratégie `homologation` : sortie de zone, une action validée, en 100 s, sans adversaire (RG I.3.b).
- [ ] Évitement démontré : obstacle posé devant le robot, arrêt puis reprise ou contournement.
- [ ] Minuterie démontrée : tout s'arrête à 100 s, actionneurs compris (RG H.3).
- [ ] Démarrage par cordon d'au moins 500 mm qui ne reste pas attaché au robot (RG F.6).
- [ ] BAU testé à chaque essai.

### 21.3 Entraînement

- [ ] Trois stratégies prêtes : `homologation`, une principale, une prudente.
- [ ] Chaque match de test rejoué sur la Carte live, écarts notés et corrigés.
- [ ] Fiche « jour de match » : préparation en 3 min (RG H.1), procédure en cas de `FAULT`, rôle de chacun.

### 21.4 Avant la coupe

- [ ] Gel de `main` une semaine avant, `hotfix/*` seulement.
- [ ] Tag Git de la version de coupe, commit affiché dans l'écran Santé.
- [ ] Image de la carte SD et copie du dépôt sur une clé USB.

---

## Points à valider

Chaque point bloque les cases indiquées.

| Point à valider | Cases bloquées |
| --- | --- |
| Empreinte réelle du robot (rayon, polygone, actionneurs rentrés) | 2.4, 5.1, 6.1, 7.4 |
| Position, orientation et hauteur du lidar sur le robot | 9.1, 16.2 |
| Séquences des mécanismes (prise de pierres, construction, Graal, lanceur) | 7.1, 14 |
| Poses d'approche de la stratégie `homologation` (carrière `quarry_front_4`, tour `blue_tower_front_outer`), selon l'empreinte du robot et les mécanismes ; sens de `element_id` pour `pick_stones` (une pierre ou toute la carrière) | 7.1, 21.2 |
| GPIO, pull-up et niveau logique de la tirette | 15.3 |
| Câblage du BAU conforme à R1, R2 et R8 du document d'asservissement | 13.3, 8.2 |
| Broche et niveau de la détection du BAU sur la Teensy moteur (R2) : `ESTOP_PIN` à renseigner dans `config.h` ; d'ici là, le statut signale `ESTOP_SENSOR_MISSING` | 13.3, 8.3 |
| Broche et rapport du pont diviseur de V_bat (R7) : `VBAT_PIN` et `VBAT_DIVIDER_RATIO` à renseigner ; d'ici là, 14,8 V par défaut et `VBAT_MISSING` dans le statut | 13.2, 8.3 |
| Codeurs sur des broches des décodeurs de quadrature matériels (R5) : les broches actuelles (11 à 14) passent par des interruptions | 13.2 |
| Roues codeuses : réglage du DIP switch des AMT102-V, diamètre et entraxe mesurés (`config.h`) | 13.2 |
| Distance entre l'axe des roues et la face qui pousse contre la bordure, et face utilisée pour le recalage | 8.1, 5.4 |
| Tension de poussée contre la bordure (`PUSH_VOLTAGE`) : force acceptable pour le robot et la table | 8.1 |
| Variante ROS 2 et pilote du TiM561, résolution angulaire réelle | 11.3, 16.1 |
| Horloge commune container lidar / brain pour l'horodatage des balayages | 16.1, 16.2 |
| Format UDP des échanges avec le calcul déporté, et contenu des observations (tags vus, pose sur la table, instant de l'image ; types provisoires de l'ADR 0011). Le modèle du monde les garde telles quelles ; leur lien avec les éléments (quel tag sur quel élément) en dépend (ADR 0012) | 17 |
| Liste exacte des « aires adverses à accès exclusif » (RG H.4) : le règlement 2027 ne la donne pas explicitement, à faire confirmer (FAQ). Le vol de pierres dans le château adverse (RJ E.1) suppose d'approcher ses remparts, que l'on interdit pour l'instant | 2.4, 5.1, 7.2 |
| Début exact de la phase d'attaque : « entre la 85e seconde et la fin du match » (RJ E.4.b) peut se lire t ≥ 84 s (la 85e seconde commence à 84 s) ou t ≥ 85 s. `scoring.json` dit 85 s pour l'instant ; une action faite avant la phase n'est pas comptée. À faire confirmer (FAQ). `MatchClock` (3.1) lit le début dans `scoring.json` sans trancher | 7.2 |
| Dates de la pré-coupe et de la CDR 2027 | 21.4 |
