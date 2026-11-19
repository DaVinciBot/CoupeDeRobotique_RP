# ADR 0012 — Modèle du monde

- **Statut** : proposé
- **Date** : 2026-11-19
- **Cases** : [TODO 4](../TODO.md#4-brain--modèle-du-monde)

## Contexte

L'[architecture, section 5.5](../ARCHITECTURE%20RP%202027.md#55-modèle-du-monde) décrit un `WorldModel` seul à écrire, lu par snapshot immuable, où chaque donnée garde sa source, sa date et une durée de vie. L'[ADR 0008](0008-brain-layers.md) le place dans `domain/world.py`, sans lecture d'horloge. Restaient à trancher :

- comment un `snapshot()` en O(1) dit si le lidar et le calcul déporté sont vivants sans lire l'heure ;
- la règle de fusion quand le calcul déporté et notre propre connaissance ne sont pas d'accord sur un élément ;
- ce que le modèle fait des observations du calcul déporté, dont le contenu est encore à valider avec l'autre équipe ([ADR 0011](0011-ports-and-fake-hardware.md), section 17) ;
- ce que rend `pose_at(t)` hors de l'historique ;
- où mettre les durées de vie, alors que le schéma de `config/robot.json` est la case 9.1.

## Décision

- **`snapshot(now)`** reçoit l'heure. Il partage les collections du modèle, que chaque mise à jour remplace sans jamais les modifier (`MappingProxyType` sur un dict neuf, tuples) : O(1), et un snapshot ne change jamais. `lidar_alive` et `remote_alive` se calculent sur `now`.
- **Adversaires : le lidar seul.** `opponents` sont les pistes du dernier balayage, avec sa date. Ils restent dans le snapshot même périmés ; `lidar_alive` le dit, et l'évitement s'arrête ([section 8.5](../ARCHITECTURE%20RP%202027.md#85-lidar-muet)). L'identification des robots par les tags ArUco est `Track.confirmed`, faite par `dvb-lidar` (section 8.3).
- **Éléments : deux états.** Chaque élément a notre état (`CONFIG` au départ, puis `STRATEGY`) et la dernière vue du calcul déporté (`REMOTE`). `WorldSnapshot.element(id)` rend la vue `REMOTE` si elle est fraîche (durée de vie `element_seen`, 2 s) et plus récente que notre état, sinon le nôtre. Le calcul déporté fait foi pour l'état des éléments ; périmée, sa vue ne sert plus à décider et notre état reprend. `carrying` vient de notre état seul : le calcul déporté ne voit pas l'intérieur du robot.
- **Observations du calcul déporté gardées telles quelles** (`WorldSnapshot.remote`). Leur lien avec les éléments (quel tag sur quel élément, à quelle distance) attend leur format (section 17) et reste dans les « Points à valider ».
- **`ElementState`** : `present` (encore à sa place initiale), `taken` (pris par un robot, nous ou l'adversaire), `placed_at` (où nous l'avons posé), `carried_by_us`, `confidence`, `tags` (définis par l'édition).
- **Constructions** : `Construction(id, footprint)`, remplacée par id quand elle grandit. Le mapping `our_constructions` ne change d'identité qu'à `add_construction` : le planificateur (5.2) sait quand recalculer sa partie fixe.
- **`PoseHistory`** à part, pour que `dvb-lidar` (16.2) la réutilise : interpolation linéaire de x et y, de θ par le plus court chemin ; `None` hors de l'historique, jamais d'extrapolation. Une pose plus ancienne que la dernière est un bug de l'appelant (`ValueError`) ; une pose à la même date remplace la dernière.
- **Durées de vie dans `config/robot.json`**, section `world`, décodée par `app/config.py` vers `WorldLifetimes` (SI, `domain`). Le schéma ne contient que cette section ; la case 9.1 y ajoute le reste.

## Alternatives écartées

- **`snapshot()` sans argument**, avec la date de la dernière mise à jour : `lidar_alive` resterait vrai tant que plus rien n'arrive, justement quand le lidar est muet.
- **Vider `opponents` quand le lidar est muet** : on perdrait la dernière position connue, utile au planificateur, sans rien gagner, puisque l'évitement s'arrête de toute façon.
- **Un seul état par élément, le plus récent gagne** : une vue `REMOTE` périmée effacerait notre état sans retour possible.
- **Associer dès maintenant chaque tag d'élément à l'élément le plus proche** : repose sur un format d'observation provisoire et une distance d'association inventée.
- **Extrapoler `pose_at` après le dernier point** : la vitesse de la Teensy n'est pas mesurée au bon instant ; mieux vaut que `dvb-lidar` décide quoi faire d'un balayage trop récent.

## Conséquences

- Les sections 5 à 8 lisent un `WorldSnapshot` ; les règles de l'édition (7.2) le reçoivent dans `domain`, comme prévu par l'[ADR 0006](0006-edition-interface.md).
- Pendant un `RESET_POSE`, l'historique interpole entre l'ancienne et la nouvelle pose sur une période de statut. Le robot est alors à l'arrêt ; à reprendre avec 16.2 si un balayage en souffre.
- Les durées de vie sont celles de la TODO ; à reprendre après les mesures sur table (21.1).
