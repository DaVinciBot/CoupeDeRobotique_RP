# ADR 0010 — Horloge, `Watch` et port de mouvement

- **Statut** : proposé ; précisé par l'[ADR 0011](0011-ports-and-fake-hardware.md) (`reset_pose` pendant le freinage d'un `move()` annulé)
- **Date** : 2026-11-17
- **Cases** : [TODO 3.1, 3.2 et 3.3](../TODO.md#3-brain--ports-faux-matériel-et-contrat-moteur)

## Contexte

Les cases 3.1 à 3.3 posent l'horloge, `Watch[T]` et le `MotionPort`. Le faux matériel (3.5), le `Navigator` (5.4), l'évitement (6.2), le `MatchManager` (8.1) et le `SafetyMonitor` (8.2) en dépendent. La TODO laissait ouverts ou contradictoires plusieurs points :

- elle range `SystemClock` et `FakeClock` dans `ports/clock.py`, alors que l'[ADR 0008](0008-brain-layers.md) réserve `ports/` aux `Protocol` et à `Watch` ;
- un timeout asyncio compte en temps réel : avec une horloge simulée, un `Watch.wait_for(…, timeout)` ne serait plus reproductible ;
- la case 3.3 met `move_id` dans `MoveCommand`, tandis que la case 15.1 le fait attribuer par l'adaptateur ;
- `MotionResult` n'est défini nulle part ;
- `max_speed` et `max_accel` n'ont pas la même unité pour une rotation (rad/s) et une ligne droite (m/s) ;
- rien ne dit ce que font `stop`, `reset_pose`, l'annulation de `move()` ou un `move()` lancé pendant un autre.

## Décision

**Horloge.**

- **Rangement.** `ports/clock.py` ne contient que le `Protocol` `Clock` : `now()`, `sleep(dt)`, `sleep_until(t)`. `SystemClock` (`time.monotonic`, `asyncio.sleep`) est dans `adapters/clock.py`, `FakeClock` dans `adapters/fake/clock.py`.
- **`FakeClock.advance(dt)`** réveille les dormeurs par échéance croissante, premier arrivé premier servi à échéance égale. Elle pose `now()` à chaque échéance et laisse les tâches réveillées tourner jusqu'à ce qu'elles se bloquent de nouveau.
- **Heure exacte.** `FakeClock` compte l'heure en nanosecondes entières. Avec des flottants, une tâche à 20 Hz ne se réveillerait que 19 fois en une seconde, car son 20ᵉ réveil tomberait à 1.0000000000000002 s.
  - Durées et échéances sont arrondies à la nanoseconde la plus proche, si bien qu'un timeout calculé en flottants (`now() + 0.2`) se déclenche dans l'`advance` qui l'atteint.
  - Une attente dans le futur fait toujours avancer l'heure d'au moins une nanoseconde : une boucle « tant que l'échéance n'est pas passée, attendre » se termine.
  - Au réveil, `now()` peut donc rester un cheveu sous l'échéance. C'est aussi le cas de `SystemClock`, qu'asyncio peut réveiller jusqu'à la résolution de l'horloge en avance. Un appelant compare avec une marge, ou boucle jusqu'à ce que son échéance soit passée.
- **Blocage des tâches.** Pour savoir que les tâches sont de nouveau bloquées, on attend que la file des tâches prêtes de la boucle (`loop._ready`) soit vide. Cet attribut est privé, mais présent depuis Python 3.4. On l'a préféré à un nombre fixe de tours, qui laisserait une longue chaîne de tâches lire une heure déjà dépassée, sans erreur. Si l'attribut disparaît, ou si une tâche ne se bloque jamais, `advance` lève une `RuntimeError`.
- **`MatchClock`** est dans `domain/match_clock.py`, comme le prévoit l'ADR 0008. C'est une dataclass figée (`t0`, `duration`, `phase_starts`), créée à la tirette par le `MatchManager` : elle n'a pas de méthode `start()`.
- **Phases et fin.** Une phase dure de son début à la fin du match. `remaining(now)` vaut 0 une fois le match fini.

**`Watch[T]`.**

- **Construction.** `Watch` reçoit la `Clock` et compte ses timeouts dessus.
- **Méthodes.** `wait_next(timeout)` et `wait_for(predicate, timeout)` rendent `None` à l'échéance. Le timeout est obligatoire : rien n'attend sans borne dans le robot. `wait_next` sert à « plus de statut depuis 300 ms » (8.2) et « lidar muet » (6.2).
- **Dernière valeur.** `Watch` garde la dernière valeur seulement. Chaque lecteur en attente reçoit la valeur qui l'a réveillé, même si elle est écrasée avant qu'il ne tourne. Les valeurs posées pendant qu'un lecteur ne tourne pas peuvent être sautées.

**Types de mouvement** (`domain/motion.py`).

- **Type somme.** `MoveCommand` est un type somme, comme `OnTimeout` (ADR 0007) : `RotateBy | RotateTo | Straight | GoToPoint | PushUntilBlocked`. Il n'y a pas de `MoveKind` : la classe donne le type, et une commande incohérente ne peut pas s'écrire. `GoToPoint` évite la collision de nom avec `strategy_model.GoTo`.
- **Limites de vitesse.** Seules les translations (`Straight`, `GoToPoint`, `PushUntilBlocked`) portent `max_speed` (m/s) et `max_accel` (m/s²). Les rotations utilisent les réglages envoyés à la Teensy au démarrage (architecture, section 7.1).
- **`PushUntilBlocked`.** Le mouvement finit `BLOCKED` au contact, et `STOPPED` si `max_distance` est parcourue sans contact.

**Contrat de `MotionPort`** (`ports/motion.py`). Il vaut pour tous les adaptateurs, quel que soit le protocole avec la Teensy (ADR 0003, à écrire en [case 12.1](../TODO.md#121-contrat-brain--teensy-moteur--docsadr0003-motion-protocolmd)).

- **`move(cmd) -> MotionStatus`**
  - Le port attribue le `move_id` et rend le statut qui termine le mouvement (`ARRIVED`, `BLOCKED` ou `STOPPED`) : `MotionResult` n'existe pas.
  - Un seul mouvement à la fois : un second `move()` lève `RuntimeError`.
  - Annuler `move()` arrête le robot comme `stop(SMOOTH)` : abandonner l'attente ne le laisse jamais rouler.
  - `move()` ne détecte pas un lien perdu : l'appelant borne son attente sur la `Clock`.
- **`stop(mode)`** envoie l'arrêt sans attendre la Teensy et ne lève jamais d'exception. Ainsi, le `SafetyMonitor` et le `finally` de `run_brain` ne restent jamais bloqués sur un lien mort.
  - **`SMOOTH`** freine avec la décélération d'arrêt de la config, celle qui sert à calculer la zone de sécurité (architecture, section 8.4), quel que soit le `max_accel` du mouvement. Sinon une `Straight` à 0,5 m/s et `max_accel` = 0,5 m/s² freinerait sur 250 mm, au lieu des 125 mm comptés par la zone à 1 m/s². Une seule valeur de config doit servir à la zone et être envoyée à la Teensy (9.1, 8.1), pour que les deux ne divergent pas.
  - **`URGENT`** est définitif pour le port : il ne sert que vers un état final (fin de match, `FAULT`, `finally` de `run_brain`).
    - Après lui, plus aucune commande de mouvement ne part. Un `stop(SMOOTH)` ultérieur et l'arrêt d'un `move()` annulé n'envoient rien, pour que rien n'adoucisse l'arrêt urgent (RG H.3, « plus aucune commande » de la case 8.1). `move()` et `reset_pose()` lèvent alors `RuntimeError`.
    - Le port l'enregistre avant son premier `await`, pour qu'un `move()` annulé pendant l'envoi ne glisse pas un arrêt doux derrière.
    - Le heartbeat (8.2) continue tant que le brain tourne : s'il s'arrêtait, le chien de garde de la Teensy lancerait de lui-même un arrêt doux (13.3). À la fin de `run_brain`, il s'arrête forcément : le firmware doit alors laisser l'arrêt urgent tel quel (point à valider ci-dessous).
- **`heartbeat()`** envoie un heartbeat sans attendre la Teensy et ne lève jamais d'exception. Le `SafetyMonitor` l'appelle à la cadence du contrat moteur (8.2, ADR 0003), y compris après `stop(URGENT)`. C'est lui, et non une tâche cachée de l'adaptateur, qui envoie le heartbeat : celui-ci s'arrête donc quand le brain ne tourne plus.
- **`reset_pose(pose)`** exige un robot immobile : `RuntimeError` si un `move()` est en cours, si le dernier statut est `MOVING`, ou après `stop(URGENT)`. Juste après un `move()` annulé, le robot freine encore : l'appelant (recalage, 5.4 et 8.1) attend d'abord un statut autre que `MOVING`. `reset_pose` ne rend la main qu'une fois qu'un statut montre la nouvelle pose, et l'appelant borne cette attente sur la `Clock`.
- **`link_ok()`** dit seulement si le port est ouvert.
- **Surveillance.** Le silence de la Teensy, son redémarrage (`boot_id`) et le BAU sont surveillés par le `SafetyMonitor` (8.2), pas par les appelants.

## Alternatives écartées

- **Horloge et faux dans `ports/`** : contredit l'ADR 0008.
- **`asyncio.timeout` dans `Watch`** : compte en temps réel, donc les tests avec `FakeClock` ne seraient plus reproductibles.
- **Une boucle asyncio à temps virtuel** (du type `looptime`) : une dépendance, ou d'autres internes d'asyncio, dont la compatibilité avec 3.14 reste à vérifier. Et le `advance(dt)` de la TODO disparaîtrait.
- **Un nombre fixe de tours de boucle dans `advance`** : il casse sans prévenir dès qu'une chaîne de tâches est plus longue.
- **`MoveCommand` à plat avec `MoveKind`** : des champs vides selon le type, et un `GOTO` sans cible passerait le typage.
- **Une enveloppe `MoveCommand(motion, max_speed, max_accel)`** : les rotations recevraient des limites de translation qu'elles ignorent.
- **Quatre limites par commande (translation et rotation)** : deux champs que rien n'utilise encore.

## Conséquences

- **Attentes bornées sur la `Clock`.**
  - `FakeClock` ne fait avancer que ce qui attend sur la `Clock` (directement ou par un `Watch`). `asyncio.timeout`, `asyncio.wait_for` et `asyncio.sleep` comptent en temps réel : dans un test avec `FakeClock`, ils ne se déclenchent jamais. Les services bornent donc leurs attentes sur la `Clock`.
  - L'outil commun (une attente avec échéance, tirée de `Watch._next`) sera ajouté en case 5.4, par le premier service qui en a besoin. Les adaptateurs en auront besoin aussi (`timeout` des actionneurs, 15.2) : comme `adapters` et `services` s'ignorent et que `domain` n'a pas asyncio, il ne pourra se ranger que dans `ports/`, à côté de `Watch`, en amendant l'ADR 0008.
- **Décodage par msgspec.** msgspec ne sait pas décoder `MoveCommand` tel quel (union de plusieurs dataclasses). Si la télémétrie ou les logs doivent transporter une commande, il faudra un tag, à ajouter à ce moment-là.
- **Question ouverte.** L'évitement (6.2) veut réduire la vitesse max d'un mouvement en cours, mais ce port ne le permet pas : la limite n'existe que dans la commande. La décision dépend du point à valider « vitesse max modifiable ou non en cours de mouvement » (ADR 0003). On ajoutera alors une méthode au port, sans changer les types ci-dessus.
- **À valider avec le firmware moteur (ADR 0003).**
  - la liste des mouvements ;
  - une limite de translation par `MOVE` ;
  - le signe de `PushUntilBlocked` : sur la distance côté brain, alors que le firmware actuel signe la vitesse ; et sa fin `STOPPED` quand `max_distance` est parcourue sans contact ;
  - la confirmation de `RESET_POSE` par le statut ;
  - l'état `MOVING` jusqu'à l'arrêt complet : `ARRIVED`, `BLOCKED` ou `STOPPED` seulement robot immobile. La fin de `move()` et le `reset_pose` qui suit un mouvement annulé en dépendent ;
  - un `STOP` normal freine avec la décélération d'arrêt de la config, pas avec celle du mouvement en cours ;
  - un `STOP` normal reçu après un `STOP` urgent est sans effet jusqu'au prochain `MOVE` ou réglage reçu, en plus de la garde côté brain. Sans cette borne, un match suivant joué sans redémarrer la Teensy ignorerait les arrêts de l'évitement ;
  - l'arrêt du chien de garde (200 ms sans heartbeat) n'adoucit pas non plus un arrêt urgent déjà fait.

  La conversion vers le fil reste dans l'adaptateur (15.1).
- **Tests de contrat.** Le contrat ci-dessus sera vérifié par des tests communs à `FakeMotion` (3.5), au `SimMotion` (11.2) et à l'adaptateur Teensy (15.1).
- **Dépendance aux internes d'asyncio.** `FakeClock` dépend de `loop._ready`. Si une version de Python le retire, les tests échouent en le disant, et on revient sur ce choix.
