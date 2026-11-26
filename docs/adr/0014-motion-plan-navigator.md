# ADR 0014 — Découpage des mouvements et Navigator

- **Statut** : proposé ; amende l'[ADR 0006](0006-edition-interface.md) (`forbidden_zones` prend le côté), l'[ADR 0008](0008-brain-layers.md) (`ports/` contient aussi l'attente avec échéance) et l'[architecture, sections 5.3, 5.5 et 9.4](../ARCHITECTURE%20RP%202027.md#94-modes-et-timeouts)
- **Date** : 2026-11-26
- **Cases** : [TODO 5.3](../TODO.md#53-chemin--mouvements--domainmotion_planpy), [TODO 5.4](../TODO.md#54-service-navigator--servicesnavigatorpy)

## Contexte

Le planificateur (5.2, [ADR 0013](0013-navmap-planner.md)) rend une suite de points. Il reste à en faire des mouvements de la Teensy (5.3), puis un service qui les envoie, borne ses attentes sur la `Clock` et vérifie l'arrivée (5.4). La TODO et l'[architecture, section 9.4](../ARCHITECTURE%20RP%202027.md#94-modes-et-timeouts) laissaient ouverts :

- le mode `auto` : comment comparer les rotations, et sur quels segments ;
- le mode `reverse` sur un chemin à plusieurs segments, alors que le lidar ne voit pas derrière (270°, [architecture 8.4](../ARCHITECTURE%20RP%202027.md#84-évitement)) ;
- ce que fait le `Navigator` quand la Teensy dit `ARRIVED` hors de la tolérance de l'étape ;
- où ranger l'attente avec échéance que l'[ADR 0010](0010-clock-watch-motion-port.md) prévoit de tirer de `Watch._next` ;
- le recalage contre une bordure : quelle face pousse, et la pose à imposer ;
- `MatchRules.forbidden_zones`, branchée en 5.4 mais créée en 7.2.

## Décision

### Chemin → mouvements (`domain/motion_plan.py`)

**Un `GOTO` par point du chemin après le départ**, toujours en coordonnées absolues : `set_max_speed` (évitement, 6.2) ne peut renvoyer qu'un `GOTO` (ADR 0010), et une replanification repart de la cible absolue. `HAS_HEADING` et `theta` vont au dernier `GOTO` si l'étape donne un cap. Un chemin réduit au départ ne donne pas de `GOTO` vers sa propre position, dont la direction serait indéfinie : un `ROTATE_TO theta` si un cap est donné, sinon rien.

**Recul borné.** Aucun `GOTO` en recul ne dépasse `reverse_max_distance`, quel que soit le mode, et aucun ne va plus vite que `reverse_max_speed` :

- **`forward`** : tout en marche avant.
- **`reverse`** : seul le dernier segment se fait en recul ; les précédents en marche avant. Si le dernier segment dépasse `reverse_max_distance`, il est coupé au point situé à `reverse_max_distance` de la cible : le robot y va en marche avant, fait demi-tour, et recule jusqu'à la cible. Une étape `reverse` veut présenter l'arrière à la cible ; elle n'a pas à reculer à l'aveugle sur tout un détour.
- **`auto`** : segment par segment. Le cap au début d'un segment est celui qu'a laissé le précédent (le cap mesuré pour le premier). Pour chaque sens, on additionne la rotation avant le segment et la rotation de fin : vers le segment suivant, supposé en marche avant, ou vers `theta` au dernier segment (aucune sans cap). Le robot recule si le segment fait au plus `reverse_max_distance` **et** si le recul évite plus de `reverse_min_gain` de rotation. Compter la rotation de fin évite de reculer pour arriver dos au segment suivant et faire demi-tour.

**Vitesse.** `max_speed` de l'étape, ou `min(max_speed, reverse_max_speed)` en recul. Une `max_speed` qui n'est pas > 0 lève `ValueError` : 0 voudrait dire « limite de la Teensy » (ADR 0003), donc pleine vitesse. **Contrat pour 6.2** : un renvoi par `set_max_speed` ne remonte jamais au-dessus de la `max_speed` du `GOTO` en cours, sinon un recul repartirait au-dessus de `reverse_max_speed`.

**Arrivée.** `reached(pose, move)` : distance à la cible ≤ `tolerance.position` et, si un cap est donné, écart d'angle ≤ `tolerance.angle`, comparé modulo 2π ; `position_reached` ne regarde que la distance.

### Navigator (`services/navigator.py`)

**`go_to(target: Move, deadline) -> NavResult`.** `deadline` est en secondes sur la `Clock`, obligatoire et finie : pour une étape sans `timeout_s`, l'exécuteur (7.3) passe la fin du match. Il n'y a pas de borne par mouvement en plus : une Teensy muette, non réglée ou en BAU relève du `SafetyMonitor` (8.2). Le `Navigator` fait au plus deux passages, le plan puis une correction :

1. Il attend un statut autre que `MOVING`, borné par l'échéance : après une étape annulée, le robot freine encore et sa pose n'est pas celle de départ.
2. `reached` : `ARRIVED`.
3. Si seule la position est dans la tolérance, un `ROTATE_TO` suffit. Sinon il appelle `Planner.updated(snapshot)`, puis `plan(pose, cible, pistes adverses du snapshot, rules.forbidden_zones(side, snapshot))` ; `NoPath` rend `NO_PATH`.
4. Il envoie les mouvements un par un ; chaque `move()` est borné par l'échéance. Une échéance passée rend `TIMEOUT` (le `move()` annulé arrête le robot, ADR 0010) ; un mouvement qui finit `BLOCKED` ou `STOPPED` rend `MOTION_FAULT`.

Si la pose est encore hors tolérance après la correction : `MOTION_FAULT`. La correction repart de la pose mesurée vers la **cible absolue**. Une seule suffit : la Teensy rend `ARRIVED` dans ses propres tolérances (`POSITION_TOLERANCE`, `ANGLE_TOLERANCE`, ADR 0003) ; si l'étape demande plus serré, corriger encore tournerait en rond (voir les Points à valider).

**Pose lue dans le `MotionPort`**, pas dans le `WorldModel` : la tâche qui remplit celui-ci n'arrive qu'en 9.2, et elle n'en est qu'une copie. La pose de départ est celle du statut immobile, puis celle du statut que rend chaque `move()`. Le snapshot du `WorldModel` donne les adversaires, nos constructions et les éléments en place.

**`NavResult`** : `ARRIVED`, `BLOCKED_BY_OPPONENT`, `NO_PATH`, `TIMEOUT`, `MOTION_FAULT`. `BLOCKED_BY_OPPONENT` n'est rendu qu'à partir de 6.3, qui reconnaîtra un `STOPPED` dû à l'évitement (`ObstacleStop`), attendra, puis replanifiera. Le `RuntimeError` du port après `stop(URGENT)` n'est pas attrapé : la fin de match et le `FAULT` (8.1, 8.2) annulent l'exécuteur avant d'envoyer `stop(URGENT)`.

**`push_until_blocked(distance, deadline) -> MotionStatus | None`** : une distance signée (négative = recul), comme le `MOVE` de l'ADR 0003, plutôt qu'un sens et une distance. Une distance nulle ou non finie lève `ValueError` : la Teensy l'ignorerait, et l'attente irait jusqu'à l'échéance. En recul, la poussée suit la règle de tout recul : `ValueError` au-delà de `reverse_max_distance`, et `max_speed` = `reverse_max_speed`. En avant, `max_speed` = 0, la limite de la Teensy : une poussée est déjà bornée par `PUSH_VOLTAGE` (ADR 0010). Rend le statut final (`BLOCKED` au contact, `ARRIVED` sans contact) ou `None` à l'échéance.

**`recalibrate(border, max_distance, deadline) -> NavResult`** (architecture 7.2) : le robot se recale **par l'arrière**.

1. `ROTATE_TO` le cap qui présente l'arrière à la bordure.
2. Poussée en recul sur au plus `max_distance`, qui doit être > 0 et au plus `reverse_max_distance` (`ValueError` sinon) : seul `BLOCKED` (contact) continue, sinon `MOTION_FAULT`.
3. Attente d'un statut autre que `MOVING` (ADR 0010).
4. `reset_pose`, borné par l'échéance : la coordonnée vaut `rear` (ou largeur − `rear`, profondeur − `rear`), le cap la normale à la bordure, l'autre coordonnée reste celle de l'odométrie.

`Border` vaut `X_MIN`, `X_MAX`, `Y_MIN` ou `Y_MAX`, les bordures de l'aire de jeu ([ADR 0002](0002-arena-format.md)). `rear` est la distance du centre du robot à sa face arrière (`geometry.rear_mm`).

### Attente avec échéance (`ports/deadline.py`)

`until(clock, awaitable, deadline) -> T | None` rend le résultat, ou `None` quand la `Clock` atteint l'échéance. La tâche est lancée tout de suite. À l'échéance, **ou si l'appelant est lui-même annulé**, elle est annulée puis attendue jusqu'au bout : quand `until` rend la main, l'arrêt d'un `move()` annulé est parti et le port accepte un nouveau mouvement. L'annulation de l'appelant continue de remonter ; une exception de l'attente aussi. `Watch._next` s'en sert.

Elle va dans `ports/`, à côté de `Watch` : les services et les adaptateurs (timeout des actionneurs, 15.2) en ont besoin, ils s'ignorent, et `domain` n'a pas asyncio (ADR 0010). **Amende l'ADR 0008** : `ports/` contient les `Protocol`, `Watch` et cette attente.

### Zones interdites selon le match

`MatchRules.forbidden_zones(side, world) -> tuple[Polygon, ...]` entre maintenant au socle, vide dans les deux éditions ; la case 7.2 y écrit les règles. Elle prend le côté, comme `end_zones(side)` : les règles d'une édition ne dépendent pas du côté, et une zone interdite peut en dépendre. **Amende l'ADR 0006**, qui écrivait `forbidden_zones(world)`.

### Configuration

```json
"geometry": { "radius_mm": 212, "rear_mm": 150 },
"navigation": {
  "margin_mm": 20, "turn_penalty_mm": 100,
  "reverse_max_distance_mm": 300, "reverse_min_gain_deg": 45, "reverse_max_speed_mps": 0.2
},
"provisional": ["geometry.radius_mm", "geometry.rear_mm", "navigation.reverse_max_distance_mm",
                "navigation.reverse_min_gain_deg", "navigation.reverse_max_speed_mps"]
```

Toutes ces valeurs sont **provisoires**. `rear_mm` dépend de la méca : 150 mm est la moitié d'un carré de 300 mm (ADR 0013). Les seuils de recul sont à régler sur table (21.1). La case 9.1 refuse une config qui en contient en profil `match`.

## Alternatives écartées

- **`ROTATE_BY` puis `STRAIGHT`** : relatifs, ils ne se renvoient pas par `set_max_speed` (ADR 0010), et une replanification ne repart pas d'une cible absolue.
- **Tout le chemin en recul en mode `reverse`** : sur un détour, plusieurs segments à l'aveugle, sans zone de sécurité utile (8.4).
- **`auto` sans regarder le segment suivant** : il peut reculer pour 180° gagnés puis refaire demi-tour vers le segment suivant.
- **`auto` sur tout le chemin à la fois** (programmation dynamique) : peu de gain pour des chemins de quelques segments.
- **Corriger jusqu'à l'échéance** : tourne en rond si la tolérance de l'étape est plus serrée que celle de la Teensy.
- **Échec dès un `ARRIVED` hors tolérance** : une petite dérive ferait échouer l'étape.
- **`asyncio.timeout` ou `asyncio.wait_for`** : ils comptent en temps réel, que `FakeClock` ne fait pas avancer (ADR 0010).
- **Pose lue dans le `WorldModel`** : rempli seulement en 9.2, et toujours un statut en retard sur le `MotionPort`.

## Conséquences

- **6.2** respecte le contrat de vitesse ci-dessus ; **6.3** intercepte `STOPPED` sur `ObstacleStop` avant `MOTION_FAULT`.
- **7.4** aura besoin du planificateur du `Navigator` pour le temps de retour : une propriété s'ajoutera avec 7.4.
- **8.1** recale avec `recalibrate` contre deux bordures.
- **Points à valider** : `rear_mm` et les seuils de recul ; tolérances des étapes au moins égales à `POSITION_TOLERANCE` et `ANGLE_TOLERANCE` de la Teensy, sinon la correction échoue toujours.
