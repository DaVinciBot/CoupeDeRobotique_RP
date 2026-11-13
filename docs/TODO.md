# TODO — Robot principal CDR 2027

Checklist de tout ce qu'il faut faire pour le robot principal, dans l'ordre où le faire. Elle suit le document d'architecture (`docs/ARCHITECTURE RP 2027.md`) ; les numéros entre parenthèses renvoient à ses sections.

**Ordre de travail.** Le socle du dépôt d'abord, puis le brain sans matériel (sections 2 à 10), puis la simulation. Les sections 12 à 14 (usb_com, firmware) avancent en parallèle : leur seul point de rencontre avec le brain est le contrat de la section 3, à figer tôt.

**Règles pour cocher une case.**

- Une PR par case, ou par petit groupe de cases d'une même sous-section. Jamais une PR « brain v1 ».
- Une case n'est cochée qu'une fois la PR mergée dans `dev`, tests compris.
- Une décision qui n'est pas dans le document d'architecture → un ADR court dans `docs/adr/`, référencé dans la PR.
- Un point qui bloque une case et dépend d'une autre équipe → l'ajouter à la section « Points à valider » en fin de fichier.

**Jalons.** Ils servent à savoir où on en est, pas à cocher.

| Jalon | Critère |
| --- | --- |
| A — Brain testable | Sections 1 à 4 faites : `uv run pytest` couvre domain, ports et modèle du monde |
| B — Match sur faux matériel | Sections 5 à 10 faites : la stratégie `homologation` se joue de bout en bout sur le faux matériel |
| C — Match simulé en CI | Section 11 faite : la matrice de scénarios passe en CI |
| D — Brain sur la vraie base | Sections 12, 13 et 15.1 faites : la stratégie `homologation` roule sur la table |
| E — Homologable | Section 21.2 faite, à la pré-coupe au plus tard |

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

## 3. Brain — ports, faux matériel et contrat moteur

### 3.1 Horloge — `ports/clock.py`

- [ ] `Clock` Protocol : `now()` (monotone, s), `async sleep(dt)`, `async sleep_until(t)`.
- [ ] `SystemClock` (`time.monotonic`, `asyncio.sleep`).
- [ ] `FakeClock` : `advance(dt)` réveille les `sleep` dans l'ordre.
- [ ] `MatchClock` (domain, sans lecture d'horloge, ADR 0008) : démarrée à `t0`, `elapsed(now)`, `remaining(now)`, `in_phase(phase_id, now)` d'après `Scoring.phase_starts`. Une seule instance, démarrée à la tirette (RG H.2).

### 3.2 `Watch[T]` — `ports/watch.py`

- [ ] Dernière valeur + notification : `set(v)`, `get() -> T | None`, `async wait_next()`, `async wait_for(predicate, timeout)`.

### 3.3 `MotionPort`

- [ ] Types dans `domain/motion.py` (ADR 0008) : `MoveKind` (`ROTATE_BY`, `ROTATE_TO`, `STRAIGHT`, `GOTO`, `PUSH_UNTIL_BLOCKED`), `MoveCommand` (`move_id`, `kind`, paramètres SI, `max_speed`, `max_accel`), `MotionState` (`MOVING`, `ARRIVED`, `BLOCKED`, `STOPPED`), `MotionStatus` (`move_id`, `state`, `pose`, `v`, `omega`, `emergency_stop`, `teensy_time`, `boot_id`), `StopMode` (`SMOOTH`, `URGENT`).
- [ ] `MotionPort` : `async move(cmd) -> MotionResult`, `async stop(mode)`, `async reset_pose(pose)`, `status() -> Watch[MotionStatus]`, `link_ok()`.

### 3.4 Contrat brain ↔ Teensy moteur — `docs/adr/0003-motion-protocol.md`

- [ ] Contenu exact de `HEARTBEAT`, `MOVE`, `STOP`, `RESET_POSE`, `MOTION_STATUS`, `SET_CONTROL_PARAMS`, `START_TRACE`, `TRACE_SAMPLE`, `TRACE_END` (6.2) : champs, types, unités, IDs.
- [ ] Fréquences : heartbeat 20 Hz, statut ≥ 10 Hz à cadence fixe, arrêt de la Teensy après 200 ms sans heartbeat.
- [ ] Sémantique d'un `MOVE` reçu pendant un autre, et de la vitesse max modifiée en cours de mouvement.
- [ ] Redémarrage de la Teensy détectable (`boot_id`) ; Teensy inerte tant qu'elle n'a pas reçu ses réglages.
- [ ] ADR relu et approuvé par les auteurs du firmware moteur et du brain avant de coder les deux côtés.

### 3.5 Autres ports

- [ ] `ActuatorPort` : `async command(actuator_id, position_name, timeout) -> ActuatorResult` (`DONE`, `BLOCKED`, `TIMEOUT`), `async release_all()`, `state(actuator_id)`, `sensor(name) -> Watch[bool]`.
- [ ] `LidarPort` : `tracks() -> Watch[TrackSet]` ; `Track(id, center, radius, velocity, confirmed)` et `TrackSet` dans `domain/world.py` (ADR 0008).
- [ ] `RemoteVisionPort` : `observations() -> Watch[RemoteObservations]`, `async send(event)`.
- [ ] `StartSwitchPort` : `inserted()`, `async wait_pulled()`.
- [ ] `TelemetryPort` : `publish(topic, msg)` non bloquant, jeté si personne n'écoute.
- [ ] BAU lu via `MotionStatus.emergency_stop`, pas de port séparé.
- [ ] `Ports` : dataclass qui regroupe tous les ports.

### 3.6 Faux matériel — `adapters/fake/`

- [ ] `FakeMotion` : exécution idéale avec une durée calculée (vitesse, accélération) ; scénarios injectables : blocage après x m, Teensy muette, redémarrage, BAU.
- [ ] `FakeActuators` : durées fixes, taux d'échec réglable.
- [ ] `FakeLidar` : pistes scriptées dans le temps.
- [ ] `FakeStartSwitch` : `pull()` déclenché par le test.
- [ ] Fixtures pytest `ports`, `clock`, `arena`, `strategy` dans `tests/conftest.py`.

---

## 4. Brain — modèle du monde

- [ ] `Source(StrEnum)` : `ODOMETRY`, `LIDAR`, `REMOTE`, `STRATEGY`, `CONFIG`.
- [ ] `Observed[T]` (5.5) : `value`, `stamp`, `source`, `age(now)`, `is_fresh(now, ttl)`.
- [ ] `ElementState` générique : `present`, `taken`, `placed_at`, `carried_by_us`, `confidence`, `tags`.
- [ ] `WorldSnapshot` (`domain/world.py`, comme tout le modèle du monde, ADR 0008) : `t`, `robot_pose`, `robot_velocity`, `opponents`, `elements`, `our_constructions`, `carrying`, `lidar_alive`, `remote_alive`.
- [ ] `WorldModel`, seul à écrire : `update_odometry`, `update_tracks`, `update_remote`, `mark_element`, `add_construction`, `snapshot()` en O(1). Pas de lecture d'horloge : chaque mise à jour porte sa date. Un snapshot n'est jamais modifié après coup (nouvelles collections à chaque mise à jour).
- [ ] Durées de vie dans `robot.json` (pistes lidar 0,3 s, calcul déporté 0,3 s, éléments vus 2 s).
- [ ] Règles de fusion explicites : lidar pour l'évitement, calcul déporté pour identifier les robots et l'état des éléments.
- [ ] Historique d'odométrie sur 2 s, `pose_at(t)` par interpolation (8.3).
- [ ] Tests : vieillissement, snapshot non modifié après une mise à jour, interpolation.

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

- [ ] `Path` + `MoveMode` + `theta` final optionnel → `ROTATE_TO`, `STRAIGHT`, …, `ROTATE_TO(theta)` (9.4).
- [ ] Mode `auto` : marche arrière seulement sous `reverse_max_distance` et si le gain de rotation dépasse `reverse_min_gain`.
- [ ] Vitesse de marche arrière plafonnée (lidar 270°, rien derrière).
- [ ] Tests par table de cas.

### 5.4 Service `Navigator` — `services/navigator.py`

- [ ] `async go_to(target, deadline) -> NavResult` (`ARRIVED`, `BLOCKED_BY_OPPONENT`, `NO_PATH`, `TIMEOUT`, `MOTION_FAULT`).
- [ ] Envoi des `MoveCommand` un par un, vérification de la tolérance en position et en angle à l'arrivée (9.3).
- [ ] Cible absolue conservée lors d'une replanification.
- [ ] `push_until_blocked(direction, max_dist)` et `recalibrate(wall)` : `RESET_POSE` avec la coordonnée et l'angle de la bordure, l'autre coordonnée gardée (7.2).
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
- [ ] Obstacle plus loin sur la trajectoire → vitesse max réduite.
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
- [ ] Temps restant atteint → annulation de l'étape, `release_all`, actionneurs rentrés, retour en salle du trône (RJ E.3).
- [ ] Pose de fin avec l'empreinte entièrement dans la zone (10 pts au lieu de 5, RJ E.3.c), autre pose candidate si la première est occupée.
- [ ] Plus rien tenu par un actionneur à la fin (RJ E.2.b) ; Graal au niveau 4 libre de tout actionneur.
- [ ] Test : stratégie trop longue → fin dans la zone avant 100 s sur 20 graines.

---

## 8. Brain — match et sûreté

### 8.1 `MatchManager` — `services/match_manager.py`

- [ ] `INIT` : attente des liens, envoi des réglages d'asservissement (5.6), vérification du profil `match` et de l'absence de ressource simulée (4.5).
- [ ] `CALIBRATING` : recalage contre deux bordures puis `RESET_POSE`, objectif < 30 s (préparation de 3 min, RG H.1) ; robot entièrement dans la salle du trône ensuite (RJ D.3.b). Un nouveau `CALIBRATE` recommence un recalage raté (ADR 0007).
- [ ] `ARMED` : tirette en place exigée, anti-rebond 50 ms, seul le front « retirée » compte.
- [ ] `RUNNING` : `MatchClock.start()` au front, envoi du départ au calcul déporté (× 3), lancement de l'exécuteur et de la fin de match.
- [ ] Minuteur de fin indépendant de la stratégie : à 100 s moins `hard_stop_margin_s`, `stop(URGENT)`, `release_all`, plus aucune commande (RG H.3 ; −50 pts si le robot bouge encore, RG H.4).

### 8.2 `SafetyMonitor` — `services/safety.py`

- [ ] Première tâche du `TaskGroup` (5.3), heartbeat 20 Hz vers la Teensy moteur.
- [ ] Surveillance : statut absent depuis 300 ms, `boot_id` changé, port série en erreur, BAU, boucle asyncio en retard de plus de 100 ms.
- [ ] Réaction unique : `stop(URGENT)`, posture par défaut, `FAULT(reason)` ; jamais de relance automatique d'un match.
- [ ] `run_brain` avec `finally` qui tente `stop(URGENT)` même si le port est mort.
- [ ] `SIGTERM` et `SIGINT` → même arrêt propre.
- [ ] Tests : exception dans une action, Teensy muette, BAU → `FAULT` et `stop` appelé.

### 8.3 Vérifications avant d'armer

- [ ] Checks : Teensy moteur, actionneurs, lidar frais, pose recalée, côté choisi, stratégie valide pour ce côté, tirette en place, V_bat au-dessus du seuil, aucune ressource simulée.
- [ ] Refus d'armer si un check échoue, raison en clair.

---

## 9. Brain — configuration, composition et logs

### 9.1 Configuration — `app/config.py`, `config/robot.json`

- [ ] Schéma msgspec (5.6) : `edition`, `profile`, géométrie du robot (rayon, empreinte, position et hauteur du lidar), numéros de série des Teensy, navigation, évitement, durées de vie, asservissement, actionneurs, réel / simulé / désactivé par sous-système. Décodé vers des dataclasses SI de `domain/`, que reçoivent les services (ADR 0008).
- [ ] Chargement au lancement, jamais à l'import.
- [ ] Validations croisées : profil `match` ⇒ tout réel sauf le calcul déporté, évitement actif.
- [ ] Erreur lisible qui nomme le champ (`navigation.avoidance.wait_s: expected >= 0, got -1`).
- [ ] Valeurs encore inconnues marquées explicitement, refusées en profil `match`.

### 9.2 Composition — `app/main.py`

- [ ] `build_ports(cfg) -> Ports` selon le profil (`match`, `test`, `sim`, `replay`) : seul endroit qui sait quel adaptateur est branché.
- [ ] `run_brain(ports, cfg)` avec `asyncio.TaskGroup`.
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
- [ ] Teensy virtuelle : le code de contrôle du firmware compilé en `native`, sur un pseudo-terminal (`pty`), avec le vrai protocole et le watchdog (12.1).
- [ ] Option « débrancher » la Teensy virtuelle en plein match.

### 11.3 Lidar simulé

- [ ] Lancer de rayons 270°, fréquence et résolution du TiM561, bruit, trous, coupures.
- [ ] Sortie dans le même format UDP que le container lidar.
- [ ] Raccourci `SimLidarTracks` (pistes vraies + bruit) tant que `dvb-lidar` n'existe pas.

### 11.4 Adversaires et actionneurs

- [ ] Adversaires : `Static`, `RandomWalk`, `Blocker`, `Mirror`, `Scripted(path)`, rayon et vitesse réglables.
- [ ] Actionneurs : durées de la config, taux de réussite réglable, effet sur les éléments.

### 11.5 Scénarios de match en CI — `tests/scenarios/`

- [ ] Matrice 2 côtés × 4 adversaires × 5 graines pour chaque stratégie de `strategies/`.
- [ ] Assertions : aucune collision, aucune entrée en `EXCLUSIVE_OPPONENT`, arrêt avant 100 s, fin entièrement dans la salle du trône, sortie de zone + une action réussie (RG I.3.b).
- [ ] Moins de 2 min en CI ; job obligatoire pour les PR qui touchent `domain/`, `services/` ou `editions/`.
- [ ] Rapport par scénario en artefact CI.

---

## 12. usb_com v2 (C++ et Python)

- [ ] Découpage COBS (`0x00` en fin de message) à la place de la signature de 4 octets (6.2).
- [ ] CRC-16 à la place du CRC-8, même variante des deux côtés, documentée.
- [ ] Trame : `[msg_id u8][payload N][len u8][crc16 u16]` puis COBS puis `0x00`.
- [ ] Index de réception sur 16 bits, contrôle de la taille avant copie.
- [ ] Un seul écrivain côté Python (file asyncio).
- [ ] Plages d'ID inchangées : 0–127 Pi → Teensy, 128–255 Teensy → Pi, 127 = NACK.
- [ ] Nouveaux messages du contrat (case 3.4 ci-dessus), dans `messages.h` et `messages.py`.
- [ ] Teensy reconnue par son numéro de série.
- [ ] CI : vérification que `messages.h` et `messages.py` ont les mêmes ID et tailles.
- [ ] Tests aller-retour Python ↔ C++ (codec compilé sur PC), avec trames abîmées, tronquées et concaténées.

---

## 13. Firmware Teensy moteur — `firmware/teensy_motor`

### 13.1 Bibliothèque de contrôle portable

- [ ] Correcteurs, générateur, odométrie et détection de blocage sans accès matériel, compilés en `teensy41` et `native` (7.1).
- [ ] Tests `pio test -e native` de chaque brique.

### 13.2 Mesure et commande

- [ ] Lecture des roues codeuses AMT102-V par les décodeurs de quadrature de la Teensy.
- [ ] Commande PWM + DIR à 30–40 kHz, en tension, compensée par V_bat mesurée.
- [ ] Deux PI de vitesse de roue.
- [ ] P + anticipation sur distance et angle, répartition sur les roues.
- [ ] Générateur de trapèze pour chaque mouvement.
- [ ] Deux positions : parcours depuis le début du mouvement (boucles) et position absolue (recalée par `RESET_POSE`, éventuellement `CORRECT_POSE` plus tard).
- [ ] Détection de blocage remontée dans le statut.
- [ ] Mouvements : tourner (angle ou cap), avancer / reculer, aller à un point, pousser jusqu'au blocage, avec identifiant et statut.

### 13.3 Sûreté

- [ ] Arrêt (décélération) après 200 ms sans `HEARTBEAT`.
- [ ] `STOP` normal par le générateur, `STOP` urgent : commande et intégrateurs à zéro.
- [ ] Robot inerte tant que les réglages n'ont pas été reçus ; drivers à l'arrêt tant que le programme n'a pas démarré (R8).
- [ ] Détection du BAU (R2), commande et intégrateurs à zéro, état remonté dans `MOTION_STATUS`.
- [ ] Identifiant de démarrage (`boot_id`) dans le statut.

### 13.4 Communication et réglage

- [ ] `MOTION_STATUS` à fréquence fixe (≥ 10 Hz), indépendante des tours de `loop()`.
- [ ] `SET_CONTROL_PARAMS` : gains et paramètres du générateur à chaud.
- [ ] `START_TRACE` (échelon de tension en boucle ouverte ou de consigne en boucle fermée), `TRACE_SAMPLE`, `TRACE_END` avec les réglages réellement utilisés.
- [ ] Messages `PRINT` réservés au debug, désactivables.

---

## 14. Firmware Teensy actionneurs — `firmware/teensy_actuators`

- [ ] Commandes génériques seulement : servo à un angle, pas-à-pas à une position, sortie tout-ou-rien, lecture de capteur (10).
- [ ] Servos avec rampes, pas-à-pas non bloquants (AccelStepper ou TeensyStep), aucun `delay()` dans les callbacks.
- [ ] Prise d'origine au démarrage et après un BAU.
- [ ] Butées logicielles, dont la hauteur de 350 mm (RG F.3).
- [ ] Posture par défaut sur perte du heartbeat (`hold` ou `release` par actionneur).
- [ ] État et fins de course remontés à 20 Hz.
- [ ] Heartbeat et `boot_id` comme la Teensy moteur.
- [ ] Tests `native` de la logique de séquencement.

---

## 15. Brain — adaptateurs réels

### 15.1 Teensy moteur — `adapters/teensy/motion.py`

- [ ] Lecture asynchrone (`pyserial-asyncio-fast`) au-dessus d'usb_com v2, un seul écrivain.
- [ ] Port trouvé par numéro de série (`/dev/dvb-motor`), reconnexion automatique ; un lien perdu en match reste un `FAULT`.
- [ ] Conversion SI ↔ unités du fil dans cet adaptateur et nulle part ailleurs.
- [ ] `move()` : `move_id` attribué, `Future` résolu par le `MOTION_STATUS` correspondant.
- [ ] `PRINT` → `brain.log` sous `hardware.teensy`.
- [ ] Tests contre la Teensy virtuelle sur `pty`, trames abîmées et débranchement compris.

### 15.2 Teensy actionneurs — `adapters/teensy/actuators.py`

- [ ] Commandes par nom traduites via `robot.json` (positions nommées, vitesses, limites).
- [ ] Vérification de la hauteur selon la zone avant chaque commande.
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
- [ ] Asservissement : courbes uPlot consigne / mesure, lancement d'essais, gains à chaud puis sauvegardés, export CSV.
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
| Unités sur le fil USB : SI (m, rad, m/s) ou unités Teensy (cm, cm/s) avec conversion dans l'adaptateur | 3.4, 12, 15.1 |
| Types des champs des messages : `float` ou `double` | 3.4, 12 |
| Variante exacte du CRC-16 | 12 |
| Comportement d'un `MOVE` reçu pendant un autre, et vitesse max modifiable ou non en cours de mouvement | 3.4, 6.2 |
| Empreinte réelle du robot (rayon, polygone, actionneurs rentrés) | 2.4, 5.1, 6.1, 7.4 |
| Position, orientation et hauteur du lidar sur le robot | 9.1, 16.2 |
| Séquences des mécanismes (prise de pierres, construction, Graal, lanceur) | 7.1, 14 |
| Poses d'approche de la stratégie `homologation` (carrière `quarry_front_4`, tour `blue_tower_front_outer`), selon l'empreinte du robot et les mécanismes ; sens de `element_id` pour `pick_stones` (une pierre ou toute la carrière) | 7.1, 21.2 |
| GPIO, pull-up et niveau logique de la tirette | 15.3 |
| Câblage du BAU conforme à R1, R2 et R8 du document d'asservissement | 13.3, 8.2 |
| Variante ROS 2 et pilote du TiM561, résolution angulaire réelle | 11.3, 16.1 |
| Horloge commune container lidar / brain pour l'horodatage des balayages | 16.1, 16.2 |
| Format UDP des échanges avec le calcul déporté | 17 |
| Liste exacte des « aires adverses à accès exclusif » (RG H.4) : le règlement 2027 ne la donne pas explicitement, à faire confirmer (FAQ). Le vol de pierres dans le château adverse (RJ E.1) suppose d'approcher ses remparts, que l'on interdit pour l'instant | 2.4, 5.1, 7.2 |
| Début exact de la phase d'attaque : « entre la 85e seconde et la fin du match » (RJ E.4.b) peut se lire t ≥ 84 s (la 85e seconde commence à 84 s) ou t ≥ 85 s. `scoring.json` dit 85 s pour l'instant ; une action faite avant la phase n'est pas comptée. À faire confirmer (FAQ) | 3.1, 7.2 |
| Dates de la pré-coupe et de la CDR 2027 | 21.4 |
