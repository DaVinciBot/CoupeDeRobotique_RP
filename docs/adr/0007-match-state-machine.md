# ADR 0007 — Table de transitions de la machine à états du match

- **Statut** : proposé
- **Date** : 2026-11-13
- **Cases** : [TODO 2.8](../TODO.md#28-machine-à-états-du-match--domainmatch_fsmpy)

## Contexte

Le diagramme de l'[architecture, section 11.1](../ARCHITECTURE%20RP%202027.md#111-machine-à-états) donne les transitions principales. Il ne dit pas :

- ce que devient un événement imprévu ;
- comment on sort de `FAULT` (« relance manuelle ») et de `FINISHED` ;
- ce qui se passe si `T = 100 s` arrive en `RUNNING` sans que la fin de match ait envoyé `END_BUDGET`.

## Décision

`dvb_brain.domain.match_fsm.transition(state, event)` renvoie le nouvel état, ou `Refused(reason)` quand l'événement ne change rien. La table est explicite :

| État | Événement | Nouvel état |
| --- | --- | --- |
| `IDLE` | `LAUNCH` | `INIT` |
| `INIT` | `CHECKS_OK` | `READY` |
| `READY` | `CALIBRATE` | `CALIBRATING` |
| `CALIBRATING` | `ARM` | `ARMED` |
| `ARMED` | `DISARM` | `READY` |
| `ARMED` | `CORD_PULLED` | `RUNNING` |
| `RUNNING` | `END_BUDGET` | `ENDING` |
| `RUNNING` | `T_END` | `FINISHED` |
| `ENDING` | `T_END` | `FINISHED` |
| tous | `Fault(reason)` | `FAULT` |

- **Tout le reste est refusé**, l'état ne change pas : `Refused("<EVENT> in <STATE>")`. Le `MatchManager` (8.1) décide de journaliser ou non.
- **La tirette ne compte qu'en `ARMED`** (RG F.6). Hors de cet état, `CORD_PULLED` est refusé, ce qui évite un faux départ (RG H.4). Depuis `ARMED`, seuls `DISARM` et `CORD_PULLED` sont acceptés, plus `Fault`.
- **`RUNNING + T_END → FINISHED`**, absent du diagramme. Le minuteur de fin ne dépend pas de la stratégie (RG H.3, invariant de sûreté) : à 100 s, le match se termine même si `END_BUDGET` n'a jamais été envoyé.
- **`FAULT` et `FINISHED` sont terminaux.** Ils refusent tout `MatchEvent`. Un nouveau match, ou une reprise après un `FAULT`, passe par une nouvelle exécution du brain, lancée par le superviseur. C'est cohérent avec `dvb-brain --side --strategy` (TODO 9.2) et avec un dossier de logs par lancement (TODO 9.3). systemd ne relance pas un match (section 11.2).
- **`Fault` est accepté dans tous les états**, `FAULT` et `FINISHED` compris. Le `MatchManager` garde la première raison.
- **`Fault` est une dataclass avec sa raison**, à côté de l'`Enum` `MatchEvent` des événements sans donnée. Un événement est donc de type `MatchEvent | Fault`.
- Les conditions d'un événement (checks verts, tirette en place, pose recalée) ne sont pas vérifiées ici, mais par le `MatchManager` (8.1, 8.3), avant d'appeler `transition`.

## Alternatives écartées

- **`LAUNCH` depuis `FAULT` ou `FINISHED`, qui ramène en `INIT`** : cela crée un chemin de sortie de `FAULT` dans le même processus, alors que la pose, le côté et la stratégie sont fixés au lancement.
- **Garder seulement `ENDING + T_END`** : si la fin de match n'envoie pas `END_BUDGET`, le robot ne s'arrêterait pas à 100 s.
- **Renvoyer l'état courant au lieu de `Refused`** : un événement ignoré et un événement accepté sans effet se confondraient, sans raison à journaliser.

## Conséquences

- Le test parcourt les 81 paires (9 états × 8 `MatchEvent` + `Fault`) contre une table réécrite dans le test.
- Point ouvert pour le `MatchManager` (8.1) : un recalage raté laisse le robot en `CALIBRATING`, où ni `DISARM` ni un nouveau `CALIBRATE` ne sont possibles. Seule une relance du brain permet de recommencer. À revoir avec la mesure du temps de recalage (TODO 21.1).
