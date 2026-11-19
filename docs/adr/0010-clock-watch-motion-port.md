# ADR 0010 — Horloge, `Watch` et port de mouvement

- **Statut** : proposé ; précisé par l'[ADR 0011](0011-ports-and-fake-hardware.md) (`reset_pose` pendant le freinage d'un `move()` annulé) ; mis en accord le 2026-11-19 avec l'[ADR 0003](0003-motion-protocol.md), le contrat avec la Teensy moteur (types de mouvement et de statut, changement de vitesse)
- **Date** : 2026-11-17
- **Cases** : [TODO 3.1, 3.2 et 3.3](../TODO.md#3-brain--ports-et-faux-matériel)

## Contexte

Les cases 3.1 à 3.3 posent l'horloge, `Watch[T]` et le `MotionPort`. Le faux matériel (3.5), le `Navigator` (5.4), l'évitement (6.2), le `MatchManager` (8.1) et le `SafetyMonitor` (8.2) en dépendent. La TODO laissait ouverts ou contradictoires plusieurs points :

- elle range `SystemClock` et `FakeClock` dans `ports/clock.py`, alors que l'[ADR 0008](0008-brain-layers.md) réserve `ports/` aux `Protocol` et à `Watch` ;
- un timeout asyncio compte en temps réel : avec une horloge simulée, un `Watch.wait_for(…, timeout)` ne serait plus reproductible ;
- la case 3.3 met `move_id` dans `MoveCommand`, tandis que la case 15.1 le fait attribuer par l'adaptateur ;
- `MotionResult` n'est défini nulle part ;
- `max_speed` et `max_accel` n'ont pas la même unité pour une rotation (rad/s) et une ligne droite (m/s) ;
- rien ne dit ce que font `stop`, `reset_pose`, l'annulation de `move()` ou un `move()` lancé pendant un autre.

L'ADR 0003 a fixé ensuite les messages avec la Teensy moteur. Cet ADR a été revu pour le suivre : le brain reprend ces messages tels quels, en SI.

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

**Types de mouvement** (`domain/motion.py`). Ils reprennent les messages de l'ADR 0003, en SI. L'adaptateur Teensy (15.1) ne fait que l'encodage : ID, octet de drapeaux, `float` sur 32 bits.

- **`MoveCommand`** est le message `MOVE` : `kind` (`MoveKind` : `ROTATE_BY`, `ROTATE_TO`, `STRAIGHT`, `GOTO`, `PUSH_UNTIL_BLOCKED`), `x`, `y`, `theta`, `distance`, `max_speed`, `max_accel`, et les deux drapeaux en booléens, `reverse` et `has_heading`. `kind` dit quels champs comptent ; les autres sont ignorés.
- **Limites de vitesse.** `max_speed` (m/s) et `max_accel` (m/s²) limitent la translation. Une valeur nulle, ou au-dessus des réglages de la Teensy, prend la limite réglée. Les rotations utilisent les limites angulaires réglées.
- **`PUSH_UNTIL_BLOCKED`** finit `BLOCKED` au contact, et `ARRIVED` s'il a parcouru `distance` sans contact. Le signe de `distance` donne le sens.
- **`MotionStatus`** est le message `MOTION_STATUS`. Il contient `move_id`, `state`, `pose`, `v`, `omega`, `vbat`, `teensy_time`, `boot_id` et `heartbeat`, plus les drapeaux en booléens : `configured`, `emergency_stop`, `heartbeat_lost`, `vbat_missing`, `estop_sensor_missing` et `trace_running`.
- **`MotionState` et `StopMode`** ont les noms et le sens de l'ADR 0003.

**Contrat de `MotionPort`** (`ports/motion.py`). Il vaut pour tous les adaptateurs et suit l'ADR 0003.

- **`move(cmd) -> MotionStatus`**
  - Le port attribue le `move_id` (jamais 0, valeur réservée par l'ADR 0003) et rend le statut qui termine le mouvement (`ARRIVED`, `BLOCKED` ou `STOPPED`) : `MotionResult` n'existe pas.
  - Un seul mouvement à la fois : un second `move()` lève `RuntimeError`. La Teensy accepte un `MOVE` pendant un autre, mais le port ne s'en sert que pour changer la vitesse (`set_max_speed`).
  - Annuler `move()` arrête le robot comme `stop(SMOOTH)` : abandonner l'attente ne le laisse jamais rouler.
  - `move()` ne détecte ni un lien perdu, ni un `MOVE` que la Teensy ignore (Teensy non réglée, heartbeat perdu, BAU, commande invalide : `move_id` ne change pas). L'appelant borne son attente sur la `Clock`. L'`INIT` (8.1) évite le premier cas, le heartbeat perdu et le BAU mènent en `FAULT` (8.2), et une commande invalide (valeur non finie, poussée de distance nulle) est une erreur du brain que ses tests doivent écarter : `FakeMotion` l'ignore comme la Teensy.
- **`stop(mode)`** envoie l'arrêt sans attendre la Teensy et ne lève jamais d'exception. Ainsi, le `SafetyMonitor` et le `finally` de `run_brain` ne restent jamais bloqués sur un lien mort.
  - **`SMOOTH`** freine à `MAX_ACCEL`, le réglage de la Teensy (à `MAX_ANGULAR_ACCEL` pendant une rotation), quel que soit le `max_accel` du mouvement.
    - C'est la décélération qui sert à calculer la zone de sécurité (architecture, section 8.4). Sinon une ligne droite à 0,5 m/s avec `max_accel` = 0,5 m/s² freinerait sur 250 mm, au lieu des 125 mm comptés par la zone à 1 m/s².
    - Une seule valeur de config sert donc à la zone et part à la Teensy comme `MAX_ACCEL` (9.1, 8.1).
    - Pendant une poussée, la Teensy coupe les moteurs tout de suite : la tension y est bornée par `PUSH_VOLTAGE`, le robot va lentement.
  - **`URGENT`** est définitif pour le port : il ne sert que vers un état final (fin de match, `FAULT`, `finally` de `run_brain`).
    - Après lui, plus aucune commande de mouvement ne part. Un `stop(SMOOTH)` ultérieur et l'arrêt d'un `move()` annulé n'envoient rien, pour que rien n'adoucisse l'arrêt urgent (RG H.3, « plus aucune commande » de la case 8.1). `move()` et `reset_pose()` lèvent alors `RuntimeError`, et `set_max_speed()` rend `False`.
    - Le port l'enregistre avant son premier `await`, pour qu'un `move()` annulé pendant l'envoi ne glisse pas un arrêt doux derrière.
    - Le heartbeat (8.2) continue tant que le brain tourne. À la fin de `run_brain`, il s'arrête forcément. Le chien de garde de la Teensy ne freine qu'un mouvement en cours, puis coupe les moteurs : après un arrêt urgent, les moteurs sont déjà libres, et il ne change rien. Un `STOP` normal reçu moteurs libres ne fait rien non plus : c'est ce que fait le firmware, et l'ADR 0003 doit encore l'écrire (écart 2 ci-dessous).
  - **Statut.** Après un arrêt urgent, un BAU, ou un arrêt pendant une poussée, la Teensy passe à `STOPPED` tout de suite, alors que le robot peut encore rouler un peu, moteurs libres. Ce n'est pas gênant : le port est alors verrouillé (arrêt urgent), le brain passe en `FAULT` (BAU), et une poussée va lentement.
- **`set_max_speed(max_speed) -> bool`** renvoie le `GOTO` en cours avec une autre `max_speed`, même point et même `move_id`. C'est le ralentissement de l'évitement (6.2, architecture 8.4).
  - La Teensy ralentit, ou accélère, sans s'arrêter. Ce n'est vrai que pendant la ligne droite, si le point reste à moins de 10° du cap et qu'il y a la place de freiner. Sinon, et pendant les rotations du `GOTO`, la Teensy freine jusqu'à l'arrêt et relance le `GOTO` (ADR 0003), qui finit à la même pose.
  - Chaque `MOVE` accepté remet à zéro la détection de blocage de la Teensy. L'évitement ne renvoie donc le `GOTO` que quand la vitesse plafond change, par paliers, et pas à chaque balayage du lidar : sinon un blocage contre un obstacle que le lidar ne voit pas ne serait jamais détecté (écart 5 ci-dessous).
  - Seulement un `GOTO` : `STRAIGHT` et `ROTATE_BY` sont relatifs, et renvoyés, ils repartiraient de la pose mesurée. Le `Navigator` envoie donc ses déplacements en `GOTO` (5.3).
  - La méthode rend `False` sans rien envoyer quand aucun `GOTO` ne tourne, après un `stop()` pendant ce `GOTO` ou après `stop(URGENT)` : un mouvement arrêté ne repart jamais. Aucun `await` ne sépare cette vérification de l'envoi, pour qu'un renvoi ne parte jamais après un `stop()`.
  - Elle n'attend pas la Teensy et ne lève pas, car l'évitement l'appelle pendant que les mouvements finissent d'eux-mêmes. Seule exception : `ValueError` si `max_speed` n'est pas fini (la Teensy ignorerait le `MOVE`) ou s'il est ≤ 0 (elle le lirait comme sa limite).
  - Un renvoi qui croise la fin du mouvement (statut final pas encore reçu) le relance sur la Teensy, avec le même `move_id`. Après `ARRIVED`, il finit aussitôt. Après `BLOCKED`, le robot repart vers le point alors que `move()` rend `BLOCKED`, jusqu'au mouvement ou au `stop` suivant (écart 4 ci-dessous).
- **`heartbeat()`** envoie un heartbeat sans attendre la Teensy et ne lève jamais d'exception. Le `SafetyMonitor` l'appelle à 20 Hz (8.2, ADR 0003), y compris après `stop(URGENT)`. C'est lui, et non une tâche cachée de l'adaptateur, qui envoie le heartbeat : celui-ci s'arrête donc quand le brain ne tourne plus.
- **`reset_pose(pose)`** exige un robot immobile, comme la Teensy, qui ignore `RESET_POSE` pendant `MOVING`.
  - `RuntimeError` si un `move()` est en cours, si le dernier statut est `MOVING`, ou après `stop(URGENT)`.
  - Juste après un `move()` annulé, le robot freine encore : l'appelant (recalage, 5.4 et 8.1) attend d'abord un statut autre que `MOVING`.
  - `reset_pose` ne rend la main qu'une fois qu'un statut montre la nouvelle pose, et l'appelant borne cette attente sur la `Clock`. La comparaison se fait à la précision du fil près : `float` sur 32 bits, et θ ramené par la Teensy dans [−π, π), alors que le brain l'écrit dans (−π, π] ; θ se compare donc modulo 2π.
- **`link_ok()`** dit seulement si le port est ouvert.
- **Surveillance.** Le silence de la Teensy, son redémarrage (`boot_id`) et le BAU sont surveillés par le `SafetyMonitor` (8.2), pas par les appelants.

## Alternatives écartées

- **Horloge et faux dans `ports/`** : contredit l'ADR 0008.
- **`asyncio.timeout` dans `Watch`** : compte en temps réel, donc les tests avec `FakeClock` ne seraient plus reproductibles.
- **Une boucle asyncio à temps virtuel** (du type `looptime`) : une dépendance, ou d'autres internes d'asyncio, dont la compatibilité avec 3.14 reste à vérifier. Et le `advance(dt)` de la TODO disparaîtrait.
- **Un nombre fixe de tours de boucle dans `advance`** : il casse sans prévenir dès qu'une chaîne de tâches est plus longue.
- **Un type somme `RotateBy | RotateTo | Straight | GoToPoint | PushUntilBlocked`** (première version de cet ADR) : le typage refusait une commande incohérente. Mais le brain et la Teensy parlaient alors deux vocabulaires pour un même protocole, et l'adaptateur devait traduire de l'un à l'autre. Le brain suit l'ADR 0003 tel quel.
- **Quatre limites par commande (translation et rotation)** : deux champs que rien n'utilise encore, et que le `MOVE` de l'ADR 0003 n'a pas.
- **Un `move()` pendant un autre, comme la Teensy le permet** : il faudrait dire ce que rend le premier `move()`, dont le `move_id` ne finirait jamais. Le port garde un mouvement à la fois, et seul `set_max_speed` renvoie le mouvement en cours.

## Conséquences

- **Attentes bornées sur la `Clock`.**
  - `FakeClock` ne fait avancer que ce qui attend sur la `Clock` (directement ou par un `Watch`). `asyncio.timeout`, `asyncio.wait_for` et `asyncio.sleep` comptent en temps réel : dans un test avec `FakeClock`, ils ne se déclenchent jamais. Les services bornent donc leurs attentes sur la `Clock`.
  - L'outil commun (une attente avec échéance, tirée de `Watch._next`) sera ajouté en case 5.4, par le premier service qui en a besoin. Les adaptateurs en auront besoin aussi (`timeout` des actionneurs, 15.2) : comme `adapters` et `services` s'ignorent et que `domain` n'a pas asyncio, il ne pourra se ranger que dans `ports/`, à côté de `Watch`, en amendant l'ADR 0008.
- **Décodage par msgspec.** `MoveCommand` et `MotionStatus` sont des dataclasses à plat : msgspec les transporte telles quelles, si la télémétrie ou les logs en ont besoin.
- **Messages de l'ADR 0003 qui n'entrent pas encore dans le port.** Ils arriveront avec le code qui s'en sert :
  - `SET_CONTROL_PARAMS` avec l'`INIT` du `MatchManager` (8.1), qui envoie les 17 réglages et attend `configured` ;
  - `START_TRACE`, `TRACE_SAMPLE` et `TRACE_END` avec l'écran Asservissement (19.2) ;
  - `RESET_TEENSY` quand un service en aura besoin.

  D'ici là, `FakeMotion` reçoit ses quatre limites à sa construction et se dit réglée.
- **Réponses de l'ADR 0003** aux points que cet ADR laissait à valider côté firmware :
  - les mouvements : `ROTATE_BY`, `ROTATE_TO`, `STRAIGHT`, `GOTO` (en marche arrière, avec un cap final) et `PUSH_UNTIL_BLOCKED` ;
  - une limite de translation par `MOVE`, ramenée aux réglages ;
  - le signe de la poussée sur `distance`, et sa fin `ARRIVED` sans contact ;
  - `RESET_POSE` ignoré pendant `MOVING`, et confirmé par le statut ;
  - `ARRIVED` quand le générateur a fini et que la mesure est dans les tolérances ;
  - le `STOP` normal freiné à `MAX_ACCEL` réglé (écart 1 ci-dessous) ;
  - un `MOVE` reçu pendant un autre, qui le remplace, et la vitesse max changée en renvoyant le `GOTO` ;
  - le chien de garde de 200 ms, fixé dans le firmware, qui freine un mouvement en cours puis coupe les moteurs.
- **Écarts relevés** en relisant le firmware de la branche de l'ADR 0003. Ils sont à corriger là-bas, avant d'approuver l'ADR (12.1) :
  1. Le `STOP` normal freine avec l'accélération du `MOVE` en cours (`Trapezoid::stop()` garde les limites posées au début du mouvement), et non avec l'accélération réglée comme l'écrit l'ADR 0003, qui gagnerait à nommer le réglage (`MAX_ACCEL`). La zone de sécurité serait trop courte dès qu'un mouvement a un `max_accel` plus faible.
  2. L'ADR 0003 n'écrit pas trois comportements que le firmware a déjà, et dont le brain dépend :
     - un `STOP` normal reçu moteurs libres (après un `STOP` urgent, un BAU ou la perte du heartbeat) ne fait rien jusqu'au prochain `MOVE` : rien n'adoucit l'arrêt urgent ;
     - le statut reste `MOVING` pendant le freinage d'un `STOP` normal et passe à `STOPPED` une fois la consigne arrêtée : `reset_pose` et le recalage attendent ce statut ;
     - un `MOVE` reçu pendant ce freinage est lancé une fois le robot arrêté, comme le fait `FakeMotion` (ADR 0011).
  3. L'ADR 0003 renvoyait aux anciennes cases de la TODO (3.4, 12 et 13). Corrigé à la mise à jour de `feat/asservissement-v1` depuis `dev` : 12.1, 12.3 et 13.
  4. Proposition plutôt qu'écart, à trancher avant l'évitement (6.2) : la Teensy pourrait ignorer un `MOVE` qui reprend le `move_id` d'un mouvement déjà fini. Un `set_max_speed` qui croise un `BLOCKED` ne relancerait plus le robot contre ce qui l'a bloqué.
  5. Proposition aussi, à trancher avant l'évitement : chaque `MOVE` accepté remet à zéro le compteur de blocage (`blocked_count`), même quand il continue le mouvement en cours. La Teensy pourrait le garder dans ce cas, pour qu'un ralentissement ne retarde pas la détection d'un blocage.
- **Tests de contrat.** Le contrat ci-dessus est vérifié par des tests communs à `FakeMotion` (3.5), au `SimMotion` (11.2) et à l'adaptateur Teensy (15.1).
- **Dépendance aux internes d'asyncio.** `FakeClock` dépend de `loop._ready`. Si une version de Python le retire, les tests échouent en le disant, et on revient sur ce choix.
