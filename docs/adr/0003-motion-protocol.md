# ADR 0003 — Contrat brain ↔ Teensy moteur

- **Statut** : proposé (à relire par les auteurs du firmware moteur et du brain, TODO 3.4)
- **Date** : 2026-11-19
- **Cases** : [TODO 3.4](../TODO.md#34-contrat-brain--teensy-moteur--docsadr0003-motion-protocolmd), [TODO 12](../TODO.md#12-usb_com-v2-c-et-python), [TODO 13](../TODO.md#13-firmware-teensy-moteur--firmwareteensy_motor)

## Contexte

L'architecture liste les messages entre le brain et la Teensy moteur (`HEARTBEAT`, `MOVE`, `STOP`, `RESET_POSE`, `MOTION_STATUS`, `SET_CONTROL_PARAMS`, `START_TRACE`, `TRACE_SAMPLE`, `TRACE_END`) mais laisse leur contenu à définir ([section 6.2](../ARCHITECTURE%20RP%202027.md#62-la-bibliothèque-usb_com)). La TODO pose aussi quatre questions ouvertes : unités sur le fil, `float` ou `double`, variante du CRC-16, et comportement d'un `MOVE` reçu pendant un autre.

Le firmware 2026 envoyait des positions en cm, des `double`, une signature de 4 octets et un CRC-8, avec un statut cadencé sur les tours de `loop()`.

## Décision

### Trame

```text
[msg_id u8][payload N][len u8][crc16 u16 LE]  -> COBS -> 0x00
```

- `len` = taille du message, ID compris (1 + N), au plus 255.
- CRC-16/CCITT-FALSE : polynôme 0x1021, valeur initiale 0xFFFF, sans réflexion, sans XOR final. Calculé sur `msg_id`, `payload` et `len`, écrit en petit-boutiste. En Python, c'est `binascii.crc_hqx(data, 0xFFFF)`.
- Une trame dont la taille ou le CRC est faux est jetée, et la Teensy répond `NACK` (127). À la réception d'un `NACK`, la Teensy renvoie son dernier message.
- Structures en `#pragma pack(push, 1)`, petit-boutiste, nombres réels en `float` (32 bits).

### Unités

**SI sur le fil** : m, rad, s, m/s, rad/s, V. Le firmware calcule aussi en SI. Sur une table de 3 m, un `float` garde une résolution de l'ordre du µm : le `double` n'apporte rien sur le fil. Le repère est celui de l'architecture ([section 3.1](../ARCHITECTURE%20RP%202027.md#31-unités-et-repère)) : θ trigonométrique, normalisé dans [−π, π).

### ID

| ID | Nom | Sens |
| --- | --- | --- |
| 0 | `MOVE` | Pi → Teensy |
| 1 | `SET_CONTROL_PARAMS` | Pi → Teensy |
| 2 | `RESET_POSE` | Pi → Teensy |
| 3–8 | actionneurs (inchangés) | Pi → Teensy |
| 9 | `STOP` | Pi → Teensy |
| 10 | `START_TRACE` | Pi → Teensy |
| 125 | `HEARTBEAT` | Pi → Teensy (commun aux deux Teensy) |
| 126 | `RESET_TEENSY` | Pi → Teensy |
| 127 | `NACK` | les deux |
| 128 | `MOTION_STATUS` | Teensy → Pi |
| 129 | `SWITCH_STATE_RETURN` (actionneurs, inchangé) | Teensy → Pi |
| 130 | `TRACE_SAMPLE` | Teensy → Pi |
| 131 | `TRACE_END` | Teensy → Pi |
| 254 | `PRINT` | Teensy → Pi |
| 255 | `UNKNOWN_MSG_TYPE` | Teensy → Pi |

`SET_TARGET_POSITION`, `SET_PID`, `SET_ODOMETRIE`, `SET_MOTORS_VOLTAGE`, `SET_WHEELS_SPEED`, `PUSH_UNTIL_BLOCKED`, `UPDATE_ROLLING_BASIS` et `UPDATE_SPEEDS` disparaissent.

### Messages Pi → Teensy

**`HEARTBEAT`** : `counter u16`. Envoyé à 20 Hz. Le dernier compteur reçu revient dans `MOTION_STATUS`.

**`MOVE`** (29 octets) : `move_id u16`, `kind u8`, `flags u8`, `x`, `y`, `theta`, `distance`, `max_speed`, `max_accel` (`float`).

| `kind` | Champs utilisés | Mouvement |
| --- | --- | --- |
| 0 `ROTATE_BY` | `theta` (rad) | Rotation sur place d'un angle |
| 1 `ROTATE_TO` | `theta` (rad) | Rotation sur place vers un cap absolu |
| 2 `STRAIGHT` | `distance` (m, négatif = recul) | Ligne droite |
| 3 `GOTO` | `x`, `y` (m), `theta` si `flags.HAS_HEADING` | Tourner vers le point, ligne droite, puis cap final si demandé |
| 4 `PUSH_UNTIL_BLOCKED` | `distance` (m, signe = sens, valeur = distance max) | Ligne droite à tension bornée jusqu'au blocage des deux roues |

- `flags` : bit 0 `REVERSE` (`GOTO` en marche arrière : le robot présente son arrière au point puis recule), bit 1 `HAS_HEADING` (`GOTO` avec cap final). Le mode `auto` des stratégies est résolu par le brain, qui connaît la table ([section 9.4](../ARCHITECTURE%20RP%202027.md#94-modes-et-timeouts)).
- `max_speed` (m/s) et `max_accel` (m/s²) limitent la translation. Une valeur nulle, négative ou au-dessus des limites réglées est ramenée aux limites réglées. Les rotations utilisent les limites angulaires réglées.
- `move_id` est choisi par le brain ; 0 est réservé (aucun mouvement depuis le démarrage).

**`STOP`** : `mode u8`. 0 `SMOOTH` : décélération par le générateur à l'accélération réglée, puis maintien de la position. 1 `URGENT` : commande et intégrateurs à zéro tout de suite, moteurs libres. Pendant une poussée ou un essai, les deux arrêts coupent les moteurs (vitesses faibles).

**`RESET_POSE`** (13 octets) : `x`, `y` (m), `theta` (rad). Impose la position absolue. Ignoré si le statut est `MOVING`. Le brain vérifie dans le statut suivant que la pose est appliquée. Les boucles ne voient jamais ce saut (D6 du document d'asservissement).

**`SET_CONTROL_PARAMS`** (6 octets) : `param u8`, `value float`. Un réglage par message.

| `param` | Réglage | Unité |
| --- | --- | --- |
| 0, 1 | `LEFT_SPEED_KP`, `LEFT_SPEED_KI` | V/(m/s), V/m |
| 2, 3 | `RIGHT_SPEED_KP`, `RIGHT_SPEED_KI` | V/(m/s), V/m |
| 4 | `DISTANCE_KP` | 1/s |
| 5 | `HEADING_KP` | 1/s |
| 6, 7 | `MAX_SPEED`, `MAX_ACCEL` | m/s, m/s² |
| 8, 9 | `MAX_ANGULAR_SPEED`, `MAX_ANGULAR_ACCEL` | rad/s, rad/s² |
| 10, 11 | `POSITION_TOLERANCE`, `ANGLE_TOLERANCE` | m, rad |
| 12, 13, 14 | `BLOCK_VOLTAGE`, `BLOCK_SPEED`, `BLOCK_TIME` | V, m/s, s |
| 15 | `PUSH_VOLTAGE` | V |
| 16 | `LOOP_PERIOD` | s, entre 1 et 20 ms, refusé si le statut est `MOVING` |

Une valeur non finie ou hors domaine (gain négatif, limite nulle…) est ignorée. **La Teensy est inerte tant qu'elle n'a pas reçu chacun des 17 réglages au moins une fois** : `MOVE` et `START_TRACE` sont ignorés, et le bit `CONFIGURED` du statut est à 0. Le brain les envoie tous à chaque démarrage ([section 5.6](../ARCHITECTURE%20RP%202027.md#56-configuration)). Un changement à chaud ne remet pas l'intégrale à zéro, car elle est déjà multipliée par `ki`.

**`START_TRACE`** (19 octets) : `kind u8`, `loop u8`, `initial`, `final`, `step_time`, `duration` (`float`).

- `kind` 0 `OPEN_LOOP_STEP` : les deux moteurs reçoivent `initial` V, puis `final` V à partir de `step_time`. C'est l'essai d'identification du document d'asservissement (section 8 : partir d'une vitesse stabilisée `u_1`, passer à `u_2`). `loop` (`LEFT_SPEED` ou `RIGHT_SPEED`) choisit la roue mesurée.
- `kind` 1 `CLOSED_LOOP_STEP` : échelon de consigne sur la boucle `loop` (0 `LEFT_SPEED`, 1 `RIGHT_SPEED`, 2 `DISTANCE`, 3 `HEADING`). Pour une boucle de vitesse, les deux roues reçoivent la même consigne (m/s). Pour la distance (m) et le cap (rad), la consigne est relative à la position du début de l'essai, sans trapèze ni anticipation.
- `duration` est bornée par le firmware (10 s). L'essai est refusé si le robot bouge, s'il n'est pas réglé, sans heartbeat ou pendant un BAU. La détection de blocage, le heartbeat et `STOP` restent actifs.

### Messages Teensy → Pi

**`MOTION_STATUS`** (39 octets), toutes les 50 ms (20 Hz), à cadence fixe donnée par le timer de l'asservissement :

| Champ | Type | Contenu |
| --- | --- | --- |
| `move_id` | u16 | Dernier `MOVE` accepté |
| `state` | u8 | 0 `MOVING`, 1 `ARRIVED`, 2 `BLOCKED`, 3 `STOPPED` |
| `flags` | u8 | bit 0 `CONFIGURED`, 1 `EMERGENCY_STOP`, 2 `HEARTBEAT_LOST`, 3 `VBAT_MISSING`, 4 `ESTOP_SENSOR_MISSING`, 5 `TRACE_RUNNING` |
| `x`, `y`, `theta` | float | Pose absolue (m, rad) |
| `v`, `omega` | float | Vitesses mesurées du robot (m/s, rad/s) |
| `vbat` | float | Tension batterie utilisée pour la compensation (V) |
| `time_ms` | u32 | Heure de la Teensy, ms depuis son démarrage |
| `boot_id` | u32 | Tiré au hasard au démarrage : s'il change, la Teensy a redémarré et la pose est perdue |
| `heartbeat` | u16 | Dernier compteur de `HEARTBEAT` reçu |

- Un `MOVE` refusé ne change pas `move_id` : le brain le voit au statut suivant.
- `PUSH_UNTIL_BLOCKED` finit en `BLOCKED` s'il a touché (cas voulu), en `ARRIVED` s'il a parcouru sa distance max sans rien toucher.
- `VBAT_MISSING` et `ESTOP_SENSOR_MISSING` signalent un capteur non câblé dans le firmware : la compensation utilise alors une tension par défaut, et le BAU n'est pas détecté. Le brain refuse d'armer en profil `match` dans ce cas (TODO 8.3).

**`TRACE_SAMPLE`** (25 octets), à chaque période pendant un essai : `time_ms u32` (depuis le début de l'essai), `setpoint`, `measurement`, `u_left`, `u_right`, `vbat` (`float`). La mesure suit la boucle choisie (vitesse de roue, distance ou cap).

**`TRACE_END`** (16 octets) : `sample_count u16`, `state u8` (comme `MOTION_STATUS`), `ts`, `kp`, `ki` (`float`) : réglages réellement utilisés pour la boucle de l'essai (0 en boucle ouverte).

### Comportement

- **Heartbeat** : au-delà de 200 ms sans `HEARTBEAT`, un mouvement en cours passe en `STOP` normal (le robot freine et s'arrête) et le bit `HEARTBEAT_LOST` passe à 1. Une fois le robot arrêté, les moteurs sont coupés : sans brain, rien ne reste alimenté. Tant que ce bit est à 1, `MOVE` et `START_TRACE` sont ignorés. Le délai ne se règle pas : il est fixé dans le firmware (invariant de sûreté).
- **BAU** : tant qu'il est détecté, commande et intégrateurs restent à zéro, `MOVE` et `START_TRACE` sont ignorés. Au réarmement, rien ne bouge sans nouveau `MOVE` (R2). L'odométrie continue de compter.
- **`MOVE` pendant un autre `MOVE`** : le nouveau remplace l'ancien, et le générateur repart de la consigne courante (position et vitesse), sans saut :
  - un `STRAIGHT`, ou un `GOTO` dont le point reste à moins de 10° du cap courant, reçu pendant une ligne droite dans le même sens, continue la ligne droite sans s'arrêter. Le petit écart de cap est corrigé pendant la ligne droite ;
  - un `ROTATE_BY` ou `ROTATE_TO` reçu pendant une rotation dans le même sens continue la rotation ;
  - sinon, le robot freine jusqu'à l'arrêt, puis exécute le nouveau mouvement.
- **Vitesse max modifiée en cours de mouvement** : on renvoie le même `GOTO` (même point) avec une autre `max_speed`. Comme il continue le mouvement en cours, le robot ralentit (ou accélère) jusqu'à la nouvelle vitesse sans s'arrêter. C'est ce que fait le ralentissement de l'évitement ([section 8.4](../ARCHITECTURE%20RP%202027.md#84-évitement)). `STRAIGHT` et `ROTATE_BY` sont relatifs : renvoyés, ils repartent de la position mesurée à la réception.
- **Fin de mouvement** : `ARRIVED` quand le générateur a fini et que la mesure est dans les tolérances. Le robot reste ensuite asservi sur la dernière consigne.
- **Blocage** : une roue force (tension au-dessus de `BLOCK_VOLTAGE`) sans tourner (vitesse sous `BLOCK_SPEED`) pendant `BLOCK_TIME` : commande et intégrateurs à zéro, `BLOCKED`. En poussée, il faut les deux roues, avec un seuil à 90 % de `PUSH_VOLTAGE`.
- **`RESET_TEENSY`** : redémarrage logiciel (`SCB_AIRCR`). Le `boot_id` change.

## Alternatives écartées

- **Unités Teensy (cm) avec conversion dans l'adaptateur** : deux systèmes d'unités dans le dépôt, et l'architecture demande le SI partout dans le code.
- **`double` sur le fil** : messages deux fois plus gros pour une précision inutile.
- **Un message `SET_CONTROL_PARAMS` avec tous les réglages** : une structure à changer à chaque nouveau réglage, et l'impossibilité d'en régler un seul depuis l'écran Asservissement. Un réglage par message coûte 17 messages au démarrage, soit moins de 200 octets.
- **Un message dédié pour changer la vitesse max** : renvoyer le `MOVE` suffit, puisqu'il continue le mouvement en cours.
- **Mode `auto` résolu par la Teensy** : il dépend de seuils et de la table, qui sont côté brain.
- **Accusé de réception pour chaque commande** : le statut à 20 Hz porte `move_id` et la pose, ce qui suffit pour vérifier qu'un `MOVE` ou un `RESET_POSE` est appliqué.

## Conséquences

- `messages.h` et `messages.py` suivent ce document. La CI compile `messages.h` sur PC et vérifie que les ID et les tailles sont les mêmes qu'en Python.
- Le `MotionPort` du brain (TODO 3.3) reprend ces types : `MoveKind`, `MotionState`, `StopMode`, `MotionStatus`.
- Les points « Unités sur le fil », « Types des champs », « Variante exacte du CRC-16 » et « Comportement d'un `MOVE` reçu pendant un autre » de la TODO sont tranchés ici, sous réserve de la relecture.
- Restent à valider avec l'élec : broches de V_bat et du BAU (bits `VBAT_MISSING` et `ESTOP_SENSOR_MISSING` à 1 en attendant).
