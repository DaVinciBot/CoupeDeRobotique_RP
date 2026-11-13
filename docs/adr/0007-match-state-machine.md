# ADR 0007 — Table de transitions de la machine à états du match

- **Statut** : proposé
- **Date** : 2026-11-13
- **Cases** : [TODO 2.8](../TODO.md#28-machine-à-états-du-match--domainmatch_fsmpy)

## Contexte

Le diagramme de l'[architecture, section 11.1](../ARCHITECTURE%20RP%202027.md#111-machine-à-états) donne les transitions principales. Il ne dit pas :

- ce que devient un événement imprévu ;
- comment on sort de `FAULT` (« relance manuelle ») et de `FINISHED` ;
- ce qui se passe si `T = 100 s` arrive en `RUNNING` sans que la fin de match ait envoyé `END_BUDGET` ;
- comment recommencer un recalage raté.

## Décision

`dvb_brain.domain.match_fsm.transition(state, event)` renvoie le nouvel état, ou `Refused(reason)` quand l'événement ne change rien. La table est explicite :

| État | Événement | Nouvel état |
| --- | --- | --- |
| `IDLE` | `LAUNCH` | `INIT` |
| `INIT` | `CHECKS_OK` | `READY` |
| `READY` | `CALIBRATE` | `CALIBRATING` |
| `CALIBRATING` | `CALIBRATE` | `CALIBRATING` |
| `CALIBRATING` | `ARM` | `ARMED` |
| `ARMED` | `DISARM` | `READY` |
| `ARMED` | `CORD_PULLED` | `RUNNING` |
| `RUNNING` | `END_BUDGET` | `ENDING` |
| `RUNNING` | `T_END` | `FINISHED` |
| `ENDING` | `T_END` | `FINISHED` |
| tout état sauf `FINISHED` et `FAULT` | `Fault(reason)` | `FAULT` |

- **Tout le reste est refusé**, l'état ne change pas. Le `MatchManager` (8.1) décide de journaliser ou non.
- **La tirette ne compte qu'en `ARMED`** (RG F.6). Hors de cet état, `CORD_PULLED` est refusé, ce qui évite un faux départ (RG H.4). Depuis `ARMED`, seuls `DISARM`, `CORD_PULLED` et `Fault` sont acceptés.
- **`RUNNING + T_END → FINISHED`**, absent du diagramme. Le minuteur de fin ne dépend pas de la stratégie (RG H.3, invariant de sûreté) : à 100 s, le match se termine même si `END_BUDGET` n'a jamais été envoyé.
- **`CALIBRATING + CALIBRATE → CALIBRATING`** : le bouton « Recaler » relance un recalage raté ou douteux, sans relancer le brain pendant les 3 minutes de préparation (RG H.1). Le `MatchManager` recommence le recalage quand la transition est acceptée.
- **`FAULT` et `FINISHED` sont terminaux et refusent tout**, `Fault` compris :
  - après la fin du match, plus aucune commande ne part (RG H.3), même sur une panne ou un BAU de ramassage ; le match reste `FINISHED` dans les logs ;
  - en `FAULT`, une deuxième panne n'est pas une nouvelle transition : la réaction (arrêt, posture par défaut) ne se répète pas et la première raison reste ;
  - un nouveau match, ou une reprise après un `FAULT`, passe par une nouvelle exécution du brain, lancée par le superviseur. C'est cohérent avec `dvb-brain --side --strategy` (TODO 9.2) et avec un dossier de logs par lancement (TODO 9.3). systemd ne relance pas un match (section 11.2).
- **`Fault` est une dataclass avec sa raison**, à côté de `MatchEvent`, les événements sans donnée. Un événement est donc de type `MatchEvent | Fault`.
- **`MatchState` et `MatchEvent` sont des `StrEnum`** (`"running"`, `"cord_pulled"`), comme `ZoneKind` et `MoveMode` : les logs et le dashboard gardent des valeurs lisibles, qui ne changent pas si on ajoute un état.
- Les conditions d'un événement (checks verts, tirette en place, pose recalée) ne sont pas vérifiées ici, mais par le `MatchManager` (8.1, 8.3), avant d'appeler `transition`.

## Alternatives écartées

- **`LAUNCH` depuis `FAULT` ou `FINISHED`, qui ramène en `INIT`** : cela crée un chemin de sortie de `FAULT` dans le même processus, alors que la pose, le côté et la stratégie sont fixés au lancement.
- **`Fault` accepté dans tous les états, comme l'écrivait la TODO** : un BAU après le match ferait réagir le robot après 100 s et afficherait un match terminé en `FAULT`, et une panne répétée relancerait la réaction à chaque fois.
- **Garder seulement `ENDING + T_END`** : si la fin de match n'envoie pas `END_BUDGET`, le robot ne s'arrêterait pas à 100 s.
- **`DISARM` depuis `CALIBRATING`** : il n'y a rien à désarmer ; « Recaler » dit mieux ce que l'on fait.
- **Renvoyer l'état courant au lieu de `Refused`** : un événement ignoré et un événement accepté sans effet se confondraient, sans raison à journaliser.
- **`Enum` avec des valeurs entières** : ajouter un état au milieu renumérote les logs déjà écrits.

## Conséquences

- Le test parcourt les 81 paires (9 états × 8 `MatchEvent` + `Fault`) contre une table réécrite dans le test.
- Le diagramme de la section 11.1 de l'architecture est mis à jour avec ces transitions.
