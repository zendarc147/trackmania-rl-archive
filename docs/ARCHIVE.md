# Archive du projet — 13 novembre 2026

Archive demandée par l’utilisateur : dépôt GitHub privé, code et documentation dans Git, artefacts sélectionnés dans la release `archive-2026-11-13`. Le dépôt est placé en lecture seule après publication avec la fonction d’archivage GitHub.

## Contenu

- Sources Python, tests, scripts, plugins AngelScript et démonstrateurs existants.
- Documentation, décisions, rapports, configurations, références A01 et verrou uv.
- Fichier TMLoader préexistant, conservé sans modification.
- Dans la pièce jointe `trackmania-artefacts-2026-11-13.tar.gz` : métadonnées, rapports et petites traces des expériences ; dernier checkpoint numérique et meilleur chrono enregistré de chaque run ; checkpoints explicitement référencés par les documents/configurations et politique J5 `a01-v4-obs2b/00100000`.

Les modèles retenus constituent une sauvegarde, pas une nouvelle sélection de performance. Le modèle de référence local reste inchangé.

## Exclusions approuvées

Le répertoire local contient environ 249 Go d’artefacts. Après consultation, l’utilisateur a retenu le code, les rapports et les modèles utiles, en excluant les replays d’entraînement volumineux.

La release exclut les fichiers `.pkl` (buffers et états sérialisés), les checkpoints intermédiaires non retenus, les traces `.jsonl` supérieures à 10 Mo, les autres artefacts supérieurs à 50 Mo et les caches Python. `.venv`, les caches et les secrets ne font pas partie du dépôt. Aucun fichier local n’est supprimé.

`manifest-artefacts.json` fournit les chemins, tailles et SHA-256 des artefacts inclus, ainsi que les chemins, tailles et motifs d’exclusion des autres artefacts. Les données exclues ne sont pas sauvegardées sur GitHub par cette archive. Sans buffers et états RNG, une reprise bit à bit de l’entraînement n’est pas garantie.

## Restauration

Cloner le dépôt, télécharger la pièce jointe de la release puis l’extraire à la racine du clone : elle recrée les chemins `runs/`. Utiliser `uv sync --frozen` pour recréer l’environnement Python. Consulter le guide J4 et les rapports avant toute exécution ; une installation du jeu reste nécessaire pour l’intégration réelle.

## Vérification de l’instantané

Commande hors jeu :

```bash
PYTHONPATH=src:tests uv run --frozen python -m unittest discover -s tests
```

Résultat le 13 novembre 2026 : **145 tests réussis** en 16,790 s. Un `ResourceWarning` de fichier non fermé est apparu dans `test_observation_v3.py` ; la suite est passée. Aucun jeu ni entraînement n’a été lancé pour cette archive. Cette vérification ne valide pas de nouvelles performances en jeu.
