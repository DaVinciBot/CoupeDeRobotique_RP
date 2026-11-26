# ADR 0013 — Carte de navigation et planificateur

- **Statut** : proposé ; amende l'[architecture, sections 8.1 et 8.2](../ARCHITECTURE%20RP%202027.md#81-carte) (les éléments en place sont des obstacles fixes, le jeu s'applique aux bordures)
- **Date** : 2026-11-26
- **Cases** : [TODO 5.1](../TODO.md#51-carte-de-navigation--domainnavmappy), [TODO 5.2](../TODO.md#52-planificateur--domainplannerpy)

## Contexte

L'[architecture, sections 8.1 et 8.2](../ARCHITECTURE%20RP%202027.md#8-navigation-et-évitement) prévoit un graphe de visibilité et un A\*. Les obstacles sont gonflés du rayon du robot plus une marge, si bien que le robot devient un point. La partie fixe du graphe (bordures, zones, nos constructions) n'est calculée qu'au chargement et quand on pose une construction. Plusieurs points restaient à trancher :

- **Les pierres.** En 2027, la table n'a aucun obstacle fixe à part les bordures : murs, tours et douves sont des zones au sol ([ADR 0004](0004-table-2027.md)). Les seuls objets posés sont les 30 pierres, déplaçables, dans 10 carrières, dont deux au milieu de la table. Selon sa hauteur, le lidar peut ne pas voir une pierre de 110 mm (section 8.4).
- **Le rayon du robot.** Il est inconnu (« Points à valider » de la TODO), et le gonflage en a besoin.
- **Le reste** : le gonflage le long des bordures, la précision du gonflage, le coût d'un virage, le résultat quand il n'y a pas de chemin, et quand recalculer la partie fixe.

## Décision

**Le jeu `clearance` = rayon du robot + marge s'applique à tous les obstacles, bordures comprises.** La TODO dit « table réduite du rayon du robot », mais elle range les bordures parmi les obstacles gonflés. La marge (20 mm) couvre la dérive d'odométrie le long d'un mur. Le recalage contre une bordure passe par `push_until_blocked` (5.4), pas par le planificateur.

**Obstacles fixes**, pour notre côté `side` :

- les zones `FORBIDDEN` de `zones_of(FORBIDDEN, side)` ;
- les zones `EXCLUSIVE_OPPONENT` de l'adversaire : y entrer donne un forfait (RG H.4) ;
- toutes les zones `OBSTACLE`, quel que soit leur propriétaire : ce sont les « éléments fixes » de la TODO ;
- **les éléments encore en place**, avec pour empreinte le rectangle de leur `pose` et de leur `size` ;
- nos constructions, avec leur `footprint`.

Les zones `CONSTRUCTION`, `STORAGE`, `START`, `END` et `OTHER` ne bloquent rien.

**Éléments en place, selon notre propre état.** Un élément est un obstacle tant que `our_elements[id].value.present` est vrai, et non d'après la vue fusionnée `element(id)` ([ADR 0012](0012-world-model.md)). Notre état ne change que par nos actions : une vue du calcul déporté qui se périme ne relance donc pas le calcul. Une pierre prise par l'adversaire reste un obstacle, ce qui est prudent. Pour prendre un élément, la stratégie vise une pose d'approche hors de l'obstacle gonflé, puis l'action finit par une courte ligne droite (7.1). Le planificateur n'a pas de liste d'éléments à ignorer.

**Obstacles dynamiques**, passés à chaque planification : un disque de rayon `track.radius + clearance` par piste adverse, et des polygones interdits selon l'état du match, gonflés de `clearance`. Ces polygones viendront de `MatchRules.forbidden_zones(world)`, que la case 7.2 ajoute au socle ; d'ici là, le planificateur se contente de les accepter.

**Gonflage simplifié mais prudent.** Un polygone est gonflé par `buffer(clearance, join_style="mitre", mitre_limit=1)`. Ses côtés reculent d'exactement `clearance`, et chaque coin est coupé par une droite tangente au cercle de rayon `clearance` : le polygone couvre tout le gonflage exact, avec deux sommets par coin au lieu d'un arc. Un disque, comme un adversaire, devient le polygone régulier à 8 côtés qui lui est circonscrit. Sur la table 2027, côté bleu, avec le rayon provisoire, l'espace libre n'est jamais à moins de 232 mm d'un obstacle. Il a 33 nœuds, et ses arêtes fixes se calculent en 1 ms sur PC.

**Nœuds et tangence.** Les nœuds sont les sommets convexes des obstacles gonflés, pris sur les anneaux du polygone d'espace libre lui-même. Une arête est valide si l'espace libre fermé contient le segment (`covers`). Comme nœuds et polygone ont les mêmes coordonnées, les prédicats exacts de GEOS acceptent un segment le long d'une arête ou qui passe par un sommet.

**Coût d'un chemin : longueur + `turn_penalty` × (segments − 1).** Avec l'asservissement polaire, le robot s'arrête à chaque sommet pour tourner. Une pénalité constante par segment ne dépend que de l'arête : l'A\* reste sur les nœuds, sans état (nœud, prédécesseur), et l'heuristique euclidienne reste admissible. La pénalité vaut 100 mm au départ, à régler sur la table.

**Résultat : `Path`, ou `NoPath(reason)`**, comme le `Refused` de l'[ADR 0007](0007-match-state-machine.md). `NoPathReason` vaut :

- `GOAL_IN_OBSTACLE` : l'arrivée est dans un obstacle gonflé, adversaire compris ;
- `UNREACHABLE` : aucun chemin, par exemple quand départ et arrivée sont dans deux morceaux séparés de l'espace libre.

Un départ dans un obstacle gonflé est projeté sur l'espace libre réduit de 0,1 mm, et le chemin commence alors par ce point. Sur le bord exact, le point projeté tombe souvent juste dehors à cause des flottants, et aucune arête n'en part.

**`Path.estimated_duration(speed, accel, rot_speed)`** compte un trapèze de vitesse par segment et |Δθ| / `rot_speed` à chaque sommet intérieur. La rotation initiale et le cap final ne sont pas comptés : la case 5.3 connaît `theta`, et la fin de match (7.4) les ajoutera à son temps de retour.

**Recalcul de la partie fixe.** Le `Planner` garde l'espace libre fixe et les arêtes entre ses nœuds. `Planner.updated(world)` le rend tel quel tant que deux choses ne changent pas : l'identité du mapping `our_constructions`, qui change à chaque `add_construction`, même quand une construction grandit sous le même id ; et l'ensemble des éléments en place. Sinon, il en construit un nouveau. À chaque requête, il ne reteste que les arêtes fixes proches d'un obstacle dynamique, puis ajoute le départ, l'arrivée et les sommets des obstacles dynamiques.

**Configuration** (`config/robot.json`, en mm comme `arena.json` et les stratégies) :

```json
"geometry": { "radius_mm": 212 },
"navigation": { "margin_mm": 20, "turn_penalty_mm": 100 },
"provisional": ["geometry.radius_mm"]
```

Ces sections sont décodées vers `RobotGeometry` (`domain/robot.py`) et `NavigationSettings` (`domain/navmap.py`), en SI ([ADR 0008](0008-brain-layers.md)). La section `geometry` recevra le reste de la géométrie à la case 9.1 (empreinte, lidar), et l'évitement (6.1) en a besoin. **Le rayon de 212 mm est provisoire** : c'est le cercle circonscrit d'un carré de 300 × 300 mm, le plus grand carré qui respecte le périmètre maximal de 1200 mm au départ (RG F). `provisional` liste les champs encore inconnus, et le décodage vérifie que chacun existe. La case 9.1 refusera en profil `match` une config qui en contient.

## Alternatives écartées

- **Ignorer les pierres**, comme le disait l'architecture : le robot traverserait les carrières, dont deux au milieu de la table, et le lidar ne les voit peut-être pas.
- **Donner aux carrières le rôle `obstacle` dans `arena.json`** : aucun code de plus, mais une carrière vide resterait interdite tout le match, et chacune bloque environ 0,8 × 0,6 m une fois gonflée.
- **Éléments en place d'après `element(id)`**, la vue fusionnée : chaque vue du calcul déporté qui se périme relancerait le calcul de la partie fixe.
- **Une pénalité qui dépend de l'angle du virage** : l'A\* devrait chercher sur les couples (nœud, prédécesseur), pour un gain faible tant que la pénalité n'est pas réglée sur table.
- **`buffer` arrondi**, `buffer(clearance, quad_segs=q)` : les sommets sont sur l'arc et les cordes à l'intérieur. Avec q = 2, une corde mangerait 18 mm des 20 mm de marge.
- **`buffer` arrondi circonscrit**, `buffer(clearance / cos(π / 4q), quad_segs=q)` : il est prudent, mais il grossit aussi les côtés droits, de 19 mm pour q = 2. Il donne 66 nœuds au lieu de 33 sur la table 2027.
- **Simplifier le polygone gonflé (`simplify`)** : il peut rentrer dans l'obstacle, de l'ordre de la tolérance.
- **Tout recalculer à chaque requête** : la TODO et l'architecture demandent une partie fixe précalculée, et le benchmark le justifie.

## Conséquences

- **Stratégie `homologation`.** L'étape `quarry` vise (2250, 300) : c'est dans les pierres gonflées de `quarry_front_4`, qui montent jusqu'à y ≈ 360 mm. Le planificateur rendra `GOAL_IN_OBSTACLE`. La pose d'approche, déjà provisoire, est à revoir avec l'empreinte du robot et les mécanismes : voir le point à valider « Poses d'approche… ».
- **Constructions.** Une construction bloque par toute son empreinte. L'action qui construit une porte du château (7.1) ne devra enregistrer que ses piliers, sinon le retour en salle du trône (7.4) devient impossible.
- **Aires exclusives.** Leur liste (RG H.4) reste à faire confirmer : si elle change, seuls les `kinds` de `arena.json` changent, et les obstacles fixes suivent.
- **Temps de calcul.** Le benchmark (`editions/cdr_2027/tests/test_planner_benchmark.py`) mesure la requête avec deux adversaires et le recalcul de la partie fixe, qui revient à chaque pierre prise. S'ils dépassent 10 ms, le `Navigator` (5.4) les appellera par `asyncio.to_thread` : la boucle ne doit jamais prendre 100 ms de retard, sinon le `SafetyMonitor` (8.2) met le robot en `FAULT`. La mesure sur la Pi 5 reste à faire (5.2, 21.1).
