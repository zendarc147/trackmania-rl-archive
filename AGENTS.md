# Règles de travail — TrackMania RL

## Avant toute intervention

- Lire `README.md`, `GOAL.md`, `docs/DECISIONS.md` et les documents du composant concerné.
- Charger le skill `trackmania-rl` s'il est disponible ; sinon lire `skills/trackmania-rl/SKILL.md` dans ce dépôt.
- Vérifier l'état Git, les instructions locales et les fichiers existants avant de modifier quoi que ce soit. Les fichiers non suivis peuvent appartenir à l'utilisateur.
- Distinguer une décision validée, une proposition, une capacité démontrée et une question ouverte. Ne jamais convertir silencieusement une proposition en exigence.

## Exploration du code avec Codebase Memory MCP

- Dans chaque nouvelle discussion sur ce dépôt, si le MCP est disponible et que la tâche concerne la structure du code, charger le skill `codebase-memory` et vérifier `list_projects` ou `index_status` avant toute exploration structurelle. Indexer ce dépôt si absent ; vérifier sa fraîcheur et réindexer après des modifications pertinentes. Ne pas lancer l'indexation pour une simple question sans rapport avec le code.
- Partir d'une question ciblée : `search_graph` ou `search_code` pour localiser, `trace_path` pour les relations, puis `get_code_snippet` ou `read_file` pour vérifier la source. Limiter les résultats et paginer si nécessaire ; éviter les extractions globales qui consomment des tokens.
- Vérifier `check_index_coverage` pour les chemins cités. Si l'index est absent, périmé ou incomplet, utiliser `search_files` et `read_file` ; ne jamais conclure à l'absence d'un élément depuis le seul graphe.
- Les instructions et décisions du projet font autorité dans leurs fichiers, pas dans le graphe. Lire directement `README.md`, `GOAL.md`, `docs/DECISIONS.md` et les documents concernés. L'index actuel exclut notamment `docs/` et `scripts/` : vérifier leur couverture plutôt que supposer leur présence.

## Contraintes produit

- TMNF et TMInterface sous Linux ; exécution locale. Ne pas proposer de migration obligatoire vers Windows.
- Politique de conduite en boucle fermée à partir de la télémétrie. Pas d'images, de LLM au volant ou de séquence TAS précalculée comme pilote final.
- Direction progressive ; accélération et frein. Le reset appartient à l'environnement.
- Les observations demandées sont celles de `docs/OBSERVATIONS.md`. Tout ajout ou retrait destiné au modèle doit être explicite et approuvé.
- La ligne de référence décrit le parcours ; elle n'impose ni les commandes ni une trajectoire optimale.
- Aucun objectif de réalisme humain. Ne pas ajouter par défaut une pénalité de glisse, de braquage, de collision ou d'écart à la ligne.
- Une map par spécialiste ; infrastructure réutilisable. Aucun nombre de checkpoints, chrono ou géométrie d'A01 ne doit être enfoui dans les composants génériques.

## Travail autorisé et limites

- Le mandat de création initial concerne la documentation et le skill, pas le démarrage du développement RL.
- Pour une mission ultérieure, n'agir que dans le périmètre et les permissions de son goal. Les exemples de prompts ne sont pas des autorisations actives.
- Demander accord avant les dépenses, les changements système, une modification de l'installation du jeu, les entraînements longs ou le travail durable hors session.
- Ne pas modifier d'autres profils Hermes. Ne pas lire de secrets. Ne pas commit, push, supprimer des données ou remplacer un modèle de référence sans demande explicite.
- Ne pas lancer le jeu ou prendre ses commandes sans autorisation pour la session de test.
- Entraînements (D37) : l'utilisateur les lance, les observe et les contrôle lui-même. L'agent prépare l'outillage : commandes simples, configurations, tableau de bord, logs et artefacts de diagnostic. Il se limite à de courts essais de fumée pour prouver que tout fonctionne. Il n'attend pas la fin d'un long entraînement pendant un goal. En fin de goal, il indique quoi lancer, comment suivre, arrêter et reprendre, et où trouver les données.
- Le pont `plugins/TrackmaniaRLBridge.as` et sa copie installée peuvent être modifiés quand c'est nécessaire (D36) : sauvegarde préalable, version incrémentée, copies identiques, tests, rapport. Les autres plugins, `TelemetrieVoiture.as`, les binaires, les mods et les réglages TMInterface restent hors de cette autorisation.

## Qualité d'implémentation future

- Utiliser uv pour ce projet ; vérifier les dépendances et leur compatibilité Python avant de choisir une bibliothèque.
- Consulter l'API de la version de TMInterface réellement utilisée. Ne pas inventer les noms de champs, les callbacks ou la disponibilité d'un contrôle pas à pas sous Linux.
- Séparer transport, état brut, observations, géométrie, récompense, environnement, apprentissage et évaluation.
- Écrire des tests hors jeu pour les calculs et protocoles. Réserver les tests d'intégration à un jeu explicitement disponible.
- Marquer les fixtures synthétiques comme telles. Un mock ne valide jamais l'intégration réelle.
- Après déconnexion, timeout ou arrêt, relâcher les commandes et invalider la transition concernée ; ne pas introduire silencieusement des données corrompues dans l'apprentissage.
- Préserver les démonstrateurs existants tant que leur remplacement n'a pas été demandé.

## Validation et transmission

- Ne cocher un critère qu'après une preuve vérifiable : commande et résultat, log, identifiant d'artefact ou mesure réelle.
- Une inspection statique ne constitue pas une validation en jeu. Un checkpoint enregistré ne constitue pas une preuve de performance.
- Évaluer sur des courses complètes, depuis le départ normal, avec politique figée et chronométrage du jeu.
- Ne pas annoncer un rang mondial sans référence datée, map identifiée, protocole comparable et chronos vérifiés.
- Conserver les budgets, seeds, versions, paramètres, statistiques de normalisation et raisons d'arrêt.
- Pour la délégation, un seul propriétaire par fichier ou un espace isolé ; un seul contrôleur actif par instance de jeu.
- Finir par un rapport bref : modifications, preuves, limites, prochain blocage. Mettre à jour les documents concernés, sans cocher le futur.
