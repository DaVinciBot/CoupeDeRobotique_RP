# Modèle d'édition

Point de départ d'un nouveau thème : ce dossier contient tous les fichiers d'un module d'édition, vides. L'objectif est une table jouable en simulation quelques jours après la sortie du règlement ([architecture, section 0](../../docs/ARCHITECTURE%20RP%202027.md#0-un-code-réutilisable-dune-année-sur-lautre)).

Tout ce qui dépend du thème de l'année va dans le module d'édition, et seulement là. Le socle ne l'importe jamais : c'est la config qui choisit l'édition (`"edition": "cdr_2027"`).

## Contenu

| Fichier | Rôle | Défini par |
| --- | --- | --- |
| `__init__.py` | Point d'entrée : l'objet `Edition` du module | TODO 2.7 |
| `arena.json` | Table : dimensions, bordures, zones, éléments de jeu, symétries, tags ArUco | TODO 2.2, 2.4 |
| `scoring.json` | Barème : points de chaque action. Aucun point dans le code | TODO 2.5 |
| `actions.py` | Actions de jeu, enregistrées par nom dans le registre du socle | TODO 7.1 |
| `rules.py` | Garde-fous des règles de jeu : actions autorisées, zones interdites, zones d'arrivée | TODO 2.7, 7.2 |
| `sim.py` | Comportement des éléments de jeu en simulation, score estimé | TODO 2.7, 11.1 |
| `strategies/homologation.strategy.json` | Stratégie d'homologation : sortir de la zone de départ, une action, revenir (RG I.3.b) | TODO 2.6 |

## État du modèle

Le modèle se remplit en même temps que le socle (sections 2 et 7 de [docs/TODO.md](../../docs/TODO.md)). Tant que les types du socle n'existent pas :

- les modules Python ne contiennent qu'une docstring ;
- `arena.json` suit le schéma de la case 2.2 ([ADR 0002](../../docs/adr/0002-arena-format.md)). Il ne décrit que la table habituelle (3000 × 2000 mm, bordures de 22 mm sur 70 mm, tags ArUco 1–5 et 6–10 de RG G.6), sans zone ni élément ;
- `scoring.json` est un objet vide : son schéma arrive avec la case 2.5 ;
- `homologation.strategy.json` suit déjà le format `cdr.strategy` ([architecture, section 9.1](../../docs/ARCHITECTURE%20RP%202027.md#91-format)), sans étape.

La PR qui ajoute un type ou un schéma au socle met à jour le fichier correspondant ici, pour que le modèle reste chargeable.

## Démarrer une édition

1. Copier le dossier : `cp -r editions/_template editions/cdr_<année>`.
2. Remplacer `_template` par l'identifiant de l'édition (`arena_id` de la stratégie, `id` de l'édition).
3. Remplir `arena.json` (en mm et en degrés) avec le plan de l'annexe du règlement, côté bleu puis symétriques. Vérifier les dimensions de la table. Faire relire les coordonnées par une deuxième personne.
4. Remplir `scoring.json` avec le barème.
5. Écrire les actions, puis les garde-fous dans `rules.py`, en citant l'article du règlement pour chacun.
6. Décrire les éléments de jeu en simulation dans `sim.py`.
7. Écrire la stratégie d'homologation.
8. Ajouter les mots du nouveau thème à `THEME_WORDS` dans `tools/core_check/theme_words.py`, pour que la CI les refuse dans le socle.
9. Choisir l'édition dans `config/robot.json`.

Les anciens modules d'édition restent dans le dépôt, pour pouvoir rejouer leurs logs et leurs stratégies.
