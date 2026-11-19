# ADR 0005 — Barème, constantes de match et chargement des stratégies

- **Statut** : proposé
- **Date** : 2026-11-13
- **Cases** : [TODO 2.5](../TODO.md#25-barème-et-constantes-de-match), [TODO 2.6](../TODO.md#26-format-cdrstrategy--domainstrategy_modelpy)

## Contexte

La case 2.5 demande le barème hors du code, et des constantes de match. La TODO plaçait la durée du match (100 s), la phase d'attaque (85 s) et la hauteur maximale (350 mm) dans la config du socle. Or l'[architecture, section 0](../ARCHITECTURE%20RP%202027.md#0-un-code-réutilisable-dune-année-sur-lautre) range la phase d'attaque (RJ E.4) parmi les règles de l'année, donc dans le module d'édition. Seules la durée (RG H.2) et la hauteur (RG F.3) relèvent du règlement général.

La case 2.6 reprend le format `cdr.strategy` de l'[architecture, section 9.1](../ARCHITECTURE%20RP%202027.md#91-format). La section ne dit pas quels champs sont facultatifs, comment représenter `on_timeout`, ni comment vérifier les types d'action avant que le registre (7.1) et l'objet `Edition` (2.7) existent.

## Décision

**Constantes du règlement général.** Elles sont dans `config/match.json`, lu par `dvb_brain.domain.match_constants` : `duration_s` (100 s, RG H.2) et `max_height_mm` (350 mm, RG F.3), converties en SI. Elles valent pour toutes les éditions, et sont écrites dans un fichier plutôt que dans le code, comme toute valeur qui décrit le jeu.

**Barème et phases de l'édition.** Ils sont dans `editions/<édition>/scoring.json`, lu par `dvb_brain.domain.scoring` :

```json
{
  "schema_version": 1,
  "kind": "cdr.scoring",
  "items": [{ "id": "tower_built", "points": 5, "rule": "RJ E.1.c" }],
  "phases": [{ "id": "attack", "start_s": 85, "rule": "RJ E.4.b" }]
}
```

- `items` : un identifiant, des points (entier strictement positif) et l'article du règlement, pour la relecture.
- `phases` : une phase va de `start_s` à la fin du match. En 2027, la phase `attack` commence à 85 s (RJ E.4.b). Elle est dans le barème parce qu'elle décide quelles actions comptent (« les actions faites en dehors de cette phase ne seront pas prises en compte »).
- Le socle lit seulement les points. La façon dont ils se combinent revient à l'édition (`sim.py`, TODO 11.1) : points par pierre, par niveau ou par douve ; 5 **ou** 10 points pour la zone d'arrivée (RJ E.3.c) ; 15 points « supplémentaires » comptés seulement avec les 5 premiers (RG H.4).
- Les pénalités (RG H.4) ne font pas partie du barème.

**Stratégies.** Le format de la section 9.1 ne change pas. On précise :

- `units` doit valoir exactement `{"length": "mm", "angle": "deg", "time": "s", "speed": "m/s"}` : le chargeur ne sait convertir que ces unités.
- Valeurs par défaut : `mode` vaut `forward` et `tolerance` vaut 20 mm et 3° (section 9.1). `theta_deg` et `not_before_s` sont facultatifs. `timeout_s` et `on_timeout` sont obligatoires : chaque étape dit comment elle se termine.
- `metadata` et `score_delta` sont facultatifs : l'éditeur les remplit, et ils ne servent jamais à décider. `metadata` est validé mais n'est pas gardé dans le modèle.
- `timeout_s: 0` (sans limite) devient `timeout = None` dans le modèle.
- `on_timeout` est lu au chargement et devient un type somme : `Skip`, `Abort` ou `GoTo(step_id)`.
- Comme pour `arena.json` ([ADR 0002](0002-arena-format.md)) : un schéma msgspec privé en mm et degrés, et un modèle public en dataclasses SI.

**Deux passes de vérification.**

- `parse_strategy` vérifie ce que le fichier dit seul : schéma, ids d'étape uniques, cible de chaque `goto:`.
- `check_strategy` vérifie ce qui demande un contexte : `arena_id`, `element_id` connus de la table, types d'action de l'édition, `not_before_s` au plus égal à la durée du match.
- Les types d'action sont un paramètre de `check_strategy`. Le registre (7.1) et le chargement de l'édition (2.7) les fourniront ; d'ici là, le test de l'édition 2027 reprend la liste de la TODO 7.1.

**Symétrie.** `mirror_strategy` applique la [section 9.5](../ARCHITECTURE%20RP%202027.md#95-côté-et-symétrie) au modèle SI : x → L − x, θ → π − θ (un θ absent reste absent), chaque `element_id` remplacé par son `mirror_id`, côté inversé. Elle réutilise les fonctions de `dvb_brain.domain.symmetry`.

## Alternatives écartées

- **85 s dans `config/match.json`**, comme l'écrivait la TODO : une règle de 2027 dans le socle, à changer chaque année, contraire à la section 0.
- **Toutes les constantes dans l'édition** : la section 0 place le match de 100 s dans le socle.
- **Les phases dans un fichier à part** (`rules.json`) : un fichier de plus pour une seule valeur, qui sert surtout à dire quels points comptent.
- **La combinaison des points dans `scoring.json`** (par unité, exclusivité, points supplémentaires) : il faudrait un petit langage pour douze lignes de barème. C'est plus simple en Python, dans l'édition.
- **`on_timeout` gardé en texte** : chaque lecteur devrait relire `goto:<id>` et traiter les erreurs.
- **Toutes les vérifications au chargement** : il faudrait l'objet `Edition` (2.7) pour lire un fichier de stratégie.

## Conséquences

- `editions/_template/scoring.json` suit le schéma avec des listes vides (`test_template_scoring_loads`) ; la stratégie d'homologation du modèle passe les vérifications (`test_template_strategy_loads_and_passes_the_checks`).
- `editions/cdr_2027/scoring.json` reprend RJ F ; un test compare chaque valeur au règlement.
- Le garde-fou des tirs (7.2) et l'horloge de match (3.1) liront le début de la phase d'attaque dans `Scoring.phase_starts`.
- La case 2.7 remplacera la liste de types d'action du test de l'édition par le registre.
- Les poses de la stratégie `homologation` 2027 sont provisoires : voir les « Points à valider » de la TODO.
