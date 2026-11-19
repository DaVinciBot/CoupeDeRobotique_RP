# ADR 0011 — Ports du brain hors base roulante, et faux matériel

- **Statut** : proposé
- **Date** : 2026-11-19
- **Cases** : [TODO 3.4 et 3.5](../TODO.md#34-autres-ports)

## Contexte

L'[ADR 0010](0010-clock-watch-motion-port.md) a posé l'horloge, `Watch` et le contrat du `MotionPort`. Les cases 3.4 et 3.5 ajoutent les autres ports (actionneurs, lidar, calcul déporté, tirette, télémétrie), leur regroupement `Ports` et le faux matériel des tests. La TODO donne leurs signatures, mais pas :

- ce que font une commande d'actionneur annulée, deux commandes sur le même actionneur, et le relâchement en fin de match, qui doit bloquer toute commande ultérieure (RG H.3, case 8.1) mais pas pendant la fin de match anticipée, qui rentre ensuite les actionneurs (case 7.4) ;
- où se vérifie la hauteur de 350 mm (RG F.3), puisque la commande ne transporte ni pose ni zone ;
- ce que rend l'attente de la tirette, alors que le match dure 100 s à partir du retrait (RG H.2) ;
- comment distinguer « aucun adversaire vu » de « lidar muet » (section 8.5) ;
- où ranger `Ports`, que les services reçoivent mais que l'[ADR 0008](0008-brain-layers.md) n'a pas prévu dans `ports/` ;
- comment le faux matériel publie ses mesures.

## Décision

**Place des types** (ADR 0008). Les valeurs sont dans `domain/` : `ActuatorResult` et `ActuatorState` dans `domain/actuators.py`, `Track` et `TrackSet` dans `domain/world.py`, les observations et événements du calcul déporté dans `domain/remote_vision.py`. Les `Protocol` sont dans `ports/`.

**`ActuatorPort`** (`ports/actuators.py`).

- **`command(actuator_id, position_name, timeout)`** rend `DONE`, `BLOCKED` ou `TIMEOUT`.
  - Il rend la main au plus tard `timeout` s après l'appel, compté sur la `Clock`, même si la carte se tait : une action n'attend jamais sans borne.
  - Deux `command()` en attente en même temps sur un actionneur lèvent `RuntimeError` : c'est un bug d'action. Deux actionneurs différents bougent en parallèle.
  - Annuler `command()` abandonne seulement l'attente : l'actionneur finit d'aller à sa position, et une nouvelle commande la remplace. C'est l'inverse du `MotionPort`, où annuler arrête le robot. Un robot abandonné roule vers l'adversaire ; un actionneur va à une position nommée de la config, bornée par ses butées. La fin de match anticipée annule l'étape puis rentre les actionneurs : elle ne doit pas buter sur une commande abandonnée.
  - Un actionneur, une position ou un capteur inconnu lève `ValueError`.
- **`release_all(final)`** n'attend pas la carte et ne lève jamais, comme `MotionPort.stop` : le `SafetyMonitor` et le `finally` de `run_brain` ne restent pas bloqués sur un lien mort.
  - `final=True` (fin à 100 s, `FAULT`, `finally` de `run_brain`) est définitif pour le port, comme `stop(URGENT)` : il est enregistré avant le premier `await`, puis `command()` lève `RuntimeError`. Une action pas encore annulée ne peut donc plus rien reprendre après la fin du match (RG H.3).
  - `final=False` sert à la fin de match anticipée (7.4), qui rentre les actionneurs ensuite.
- **`state(actuator_id)`** rend `ActuatorState(position_name, moving)` : la dernière position nommée atteinte, `None` pendant un mouvement, après un échec, un timeout ou un relâchement.
- **`sensor(name)`** rend un `Watch[bool]`.
- **Hauteur de 350 mm** (RG F.3). Le port ne reçoit ni pose ni zone. Une position nommée au-dessus de 350 mm sera refusée au chargement de la config (9.1) ; la règle qui dépend de la zone (élément porté plus haut seulement en zone de construction) est dans `MatchRules` (7.2), vérifiée avant l'appel. La butée de la carte double le tout (section 10).
- `heartbeat()` et `link_ok()` de la carte actionneurs arriveront avec son contrat (12.2) et le `SafetyMonitor` (8.2).

**`LidarPort`** (`ports/lidar.py`). `tracks()` rend un `Watch[TrackSet]`. Le processus lidar publie un `TrackSet` par balayage, **vide quand il ne voit rien** : seul le silence veut dire « lidar muet » (8.5), ce que l'évitement (6.2) lit par `wait_next(0.3)`. `TrackSet.stamp` est l'instant du balayage sur la `Clock` du brain ; `Track` porte `id`, `center`, `radius`, `velocity` et `confirmed` (confirmée par un tag ArUco adverse du calcul déporté, section 8.3).

**`RemoteVisionPort`** (`ports/remote_vision.py`). `observations()` rend un `Watch[RemoteObservations]` : l'instant de l'image et les tags ArUco vus, chacun avec sa pose sur la table (RG G.6, TODO 17). `send(event)` envoie `SideChosen`, `MatchStarted` ou `PoseEstimate` (TODO 17), sans attendre et sans jamais lever. La répétition du départ (× 3) reste à l'appelant (8.1). Les instants sont sur la `Clock` du brain ; l'adaptateur les convertit vers l'horloge commune (17). **Ces types sont provisoires** : le contenu réel des observations est à valider avec le calcul déporté.

**`StartSwitchPort`** (`ports/start_switch.py`).

- `inserted()` dit si la tirette est en place.
- `wait_pulled()` rend la main au prochain front « insérée → retirée » survenu après l'appel : une tirette déjà retirée ne compte pas. Il **rend l'instant du premier front brut** sur la `Clock`, celui qui devient le `t0` de la `MatchClock` (RG H.2). L'anti-rebond (15.3) confirme le front, mais ne le retarde pas : sinon le match finirait 50 ms trop tard.
- `wait_pulled()` n'a pas de timeout : l'attente en `ARMED` n'a pas de borne, et « Désarmer » l'annule. Ne lire la tirette qu'en `ARMED` (RG F.6) est le travail du `MatchManager` (8.1).

**`TelemetryPort`** (`ports/telemetry.py`). `publish(topic, msg)` est synchrone, jette le message si personne n'écoute et ne lève jamais. `msg` est un `object` tant que les messages du bus n'existent pas (10, 18) ; on resserrera le type sans changer les appels.

**BAU.** Pas de port : il est lu dans `MotionStatus.emergency_stop`.

**`Ports`** est une dataclass figée dans `ports/__init__.py` : `clock`, `motion`, `actuators`, `lidar`, `remote_vision`, `start_switch`, `telemetry`. Les services la reçoivent et ne peuvent importer ni `adapters` ni `app` : `ports/` est donc le seul endroit possible. **Cet ADR amende l'ADR 0008** : `ports/` contient les `Protocol`, `Watch` et `Ports`.

**Faux matériel** (`adapters/fake/`).

- **Publication.** Chaque faux reçoit la `Clock`. Ceux qui publient à cadence fixe (base roulante, lidar) ont une coroutine `run()`, que le test lance et annule comme le ferait le lecteur série d'un vrai adaptateur. Sans statut périodique, « Teensy muette » ne se simulerait pas.
- **`FakeMotion`.**
  - Exécution idéale en trapèze (ou triangle) à partir de la vitesse et de l'accélération de chaque translation, et des limites de rotation données au faux. `GoToPoint` tourne puis avance. Les profils restent privés au faux ; ils iront dans `domain/` quand le planificateur (5.2) ou `SimMotion` (11.2) en auront besoin.
  - `move()` attend le statut qui termine son `move_id`, comme le fera l'adaptateur Teensy (15.1).
  - `stop(SMOOTH)` freine avec la décélération d'arrêt donnée au faux (avec l'accélération de rotation pendant une rotation, faute de mieux tant que le contrat moteur n'est pas écrit).
  - Scénarios : blocage après x m, carte muette (plus de statut, commandes perdues), redémarrage (nouveau `boot_id`, pose perdue), BAU.
  - Le faux garde les heartbeats et les arrêts reçus, que le `SafetyMonitor` (8.2) devra prouver même carte muette.
  - Il n'a pas de chien de garde : c'est la Teensy virtuelle qui l'aura (13.5).
- **`FakeActuators`.** Durée fixe par actionneur, taux d'échec réglable et graine fixée. L'état se calcule depuis la `Clock`, si bien qu'une attente abandonnée laisse l'actionneur finir. Le faux ne connaît pas les noms de position : c'est l'adaptateur réel qui les lira dans `robot.json` (15.2).
- **`FakeLidar`** publie à cadence fixe ce que rend une fonction du temps écrite par le test, et rien quand elle rend `None` (lidar muet).
- **`FakeStartSwitch`**, **`FakeRemoteVision`** et **`FakeTelemetry`** sont pilotés ou lus par le test. Les deux derniers ne sont pas listés dans la case 3.5 ; ils sont nécessaires à la fixture `ports`.
- **Tests de contrat du `MotionPort`.** Ils sont écrits une fois (`tests/ports/test_motion_contract.py`) sur une fixture paramétrée : `FakeMotion` aujourd'hui, `SimMotion` (11.2) et l'adaptateur Teensy (15.1) ensuite. La fixture fournit le port, une façon d'avancer le temps (la `FakeClock` ou une attente réelle) et une façon de couper le lien.

## Alternatives écartées

- **Annuler une commande d'actionneur arrête l'actionneur** : un servo ne s'arrête pas proprement à mi-course, et la fin de match anticipée devrait attendre l'arrêt avant de rentrer les actionneurs.
- **`release_all()` sans verrou, la garde des 100 s laissée au `MatchManager`** : une action mal annulée pourrait relancer un actionneur après la fin du match.
- **Vérifier la hauteur dans l'adaptateur des actionneurs** : il faudrait lui passer la pose et la zone à chaque commande.
- **`wait_pulled()` sans valeur rendue** : le `MatchManager` lirait l'heure après l'anti-rebond et le réveil de la boucle, en retard sur le vrai départ.
- **Un faux de base roulante sans tâche, qui publie à chaque changement** : on ne pourrait plus simuler une carte qui se tait.

## Conséquences

- Les cases 4 (modèle du monde), 6.2 (évitement), 7.4 (fin de match), 8.1 (match) et 8.2 (sûreté) codent contre ces ports et se testent avec ces faux et la `FakeClock`.
- La TODO est corrigée : signature de `wait_pulled()` (3.4), anti-rebond renvoyé à l'adaptateur (8.1 → 15.3), vérification de la hauteur renvoyée à la config et aux règles (15.2 → 9.1, 7.2), `release_all(final=False)` en fin de match anticipée (7.4) et `release_all(final=True)` au minuteur de fin (8.1).
- **À valider avec la carte actionneurs (12.2, 14)** : ce que fait la carte sur un timeout (s'arrête-t-elle ?), et qu'elle ne reprenne pas sa posture `hold` à la perte du heartbeat après un relâchement final. C'est le même piège que le chien de garde moteur après un arrêt urgent (ADR 0010).
- **À valider avec le calcul déporté (17)** : le contenu des observations (tags vus, pose sur la table, instant de l'image).
