# ADR 0002 — Format de la table (`arena.json`)

- **Statut** : proposé
- **Date** : 2026-11-11
- **Cases** : [TODO 2.2](../TODO.md#22-modèle-générique-de-la-table--domainarenapy)

## Contexte

Chaque édition décrit sa table dans `editions/<édition>/arena.json` : dimensions, bordures, zones, éléments de jeu, symétries et tags ArUco ([architecture, section 0](../ARCHITECTURE%20RP%202027.md#0-un-code-réutilisable-dune-année-sur-lautre)). Le socle charge ce fichier dans un modèle générique, `dvb_brain.domain.arena`, qu'utilisent ensuite la symétrie (TODO 2.3), la carte de navigation (5.1) et la fin de match (7.4).

L'architecture ne fixe ni les unités du fichier ni la façon de décrire une zone qui a plusieurs rôles. Or en 2027, une salle du trône est à la fois l'aire de départ et l'aire d'arrivée de son équipe (RJ D.3). L'architecture la classe aussi parmi les aires à accès exclusif, interdites à l'adversaire (section 8.1, RG H.4). Cette liste reste à faire confirmer : voir les « Points à valider » de la TODO.

## Décision

**Unités.** Le fichier est en mm et en degrés. Chaque champ porte son unité dans son nom (`width_mm`, `polygon_mm`, `theta_deg`), comme les stratégies ([architecture, section 9.1](../ARCHITECTURE%20RP%202027.md#91-format)). On recopie ainsi directement les cotes du plan du règlement, et la relecture est plus simple. Le chargeur convertit en SI : le reste du code ne voit que des mètres et des radians.

**Une zone a un ensemble de rôles.** `kinds` est une liste non vide de `ZoneKind` (`start`, `end`, `forbidden`, `exclusive_opponent`, `construction`, `storage`, `obstacle`, `other`). Une aire physique s'écrit une seule fois, avec un seul polygone, quel que soit le nombre de ses rôles.

**Propriétaire.** `owner` vaut `blue`, `yellow` ou `null` (zone commune aux deux équipes). Le champ est obligatoire : une zone n'est jamais commune par oubli. `Arena.zones_of(kind, side)` rend les zones de ce rôle qui appartiennent à `side` ou à personne.

**Accès exclusif.** Une zone `exclusive_opponent` est une aire à accès exclusif de son `owner`. Le robot de l'autre équipe ne doit jamais y entrer, sous peine de forfait (RG H.4). Ce rôle exige un `owner`. Les aires interdites au robot bleu s'obtiennent donc avec `zones_of(EXCLUSIVE_OPPONENT, YELLOW)`.

**Symétrie.** Chaque zone et chaque élément a un `mirror_id` obligatoire : l'id de son symétrique dans la même liste, ou son propre id s'il est sur l'axe. Le lien est réciproque. La symétrie géométrique (polygones et poses symétriques) est vérifiée par la case 2.3.

**Erreurs.** Une erreur de chargement nomme le champ, avec son chemin JSON, et la valeur fautive. Par exemple : `editions/cdr_2027/arena.json: $.zones[2].id: duplicate id, got 'blue_start'`. Les champs inconnus sont refusés. Le même décodage (`dvb_brain.domain.json_schema`) servira aux stratégies (2.6) et à la config (9.1).

Exemple de zone :

```json
{
  "id": "blue_start",
  "kinds": ["start", "end", "exclusive_opponent"],
  "owner": "blue",
  "polygon_mm": [[0, 0], [400, 0], [400, 400], [0, 400]],
  "height_mm": 0,
  "tags": [],
  "mirror_id": "yellow_start"
}
```

## Alternatives écartées

- **Fichier en SI** (m, rad) : les cotes du règlement seraient à convertir à la main (0.022, 1.5708…), avec un risque d'erreur à la relecture de la case 2.4.
- **Un seul `kind` par zone**, comme le prévoyait d'abord la TODO 2.2 : une salle du trône serait déclarée trois fois avec le même polygone et trois `mirror_id`. Ces copies peuvent diverger à la relecture.
- **`owner` facultatif, `null` par défaut** : une zone d'équipe dont on oublie le propriétaire deviendrait commune sans aucune erreur.

## Conséquences

- Le modèle `editions/_template/arena.json` suit ce format et doit rester chargeable (test `test_template_arena_loads`).
- La case 2.4 remplit `editions/cdr_2027/arena.json` dans ce format. Elle décide aussi où ranger le tag ArUco 13 des éléments et si tout doit être sur le plateau : la plateforme du calcul déporté peut en dépasser (RG G).
- Le dashboard (19.1) dessine la table à partir de ce même fichier.
