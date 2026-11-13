---
name: trackmania-rl
description: "Use when working on the TrackMania RL project."
version: 0.1.0
author: "maître Yoda, Hermes Agent"
platforms: [linux]
metadata:
  hermes:
    tags: [trackmania, reinforcement-learning, telemetry, research]
---

# Procédure de travail — TrackMania RL

## Quand utiliser ce skill

Utiliser ce skill pour concevoir, développer, tester ou analyser le projet TMNF/TMInterface sous Linux de l'utilisateur. Il s'applique à la préparation des goals et aux expérimentations, pas à une soumission automatique de records ou à un bot de jeu en ligne.

La copie `skills/trackmania-rl/SKILL.md` du dépôt fait référence. La copie installée dans le profil Hermes sert au chargement ; synchroniser les deux après une modification approuvée. Ne jamais modifier un autre profil par déduction.

## Prérequis

- Se placer dans le dépôt concerné et identifier sa racine avec `terminal`.
- Lire avec `read_file` : `AGENTS.md`, `GOAL.md`, `docs/DECISIONS.md` et le document du composant concerné.
- Vérifier l'état Git avant toute écriture. Les fichiers non suivis peuvent être des fichiers utilisateur.
- Confirmer le jalon et les permissions. Un exemple de prompt n'est pas une autorisation d'exécution.
- Pour une tâche de structure du code, si Codebase Memory MCP est disponible, charger `codebase-memory`, vérifier `list_projects` ou `index_status`, puis rechercher des symboles ciblés et vérifier leurs sources. Indexer le dépôt si absent ; vérifier fraîcheur et couverture des chemins cités. Limiter et paginer les résultats pour économiser les tokens. En cas d'absence ou de trou de couverture, utiliser `search_files` et `read_file` ; ne jamais déduire une absence du seul graphe. Lire directement les contrats et documents, notamment `docs/` et `scripts/` si exclus de l'index.

## Contraintes à préserver

- TMNF avec TMInterface sous Linux, essais locaux.
- Un pilote spécialisé par map ; procédure d'entraînement réutilisable. A01 est la première map, pas une constante à enfouir dans le code générique.
- Décisions en boucle fermée pendant la course. Pas de séquence TAS précalculée comme pilote final ; pas de LLM dans la boucle de contrôle.
- Observations numériques décrites dans `docs/OBSERVATIONS.md`, sans images. Aucun ajout ou retrait implicite.
- Direction progressive, accélération et frein ; reset géré par l'environnement.
- Aucun objectif de réalisme humain. Ne pas ajouter par défaut une pénalité de glisse, de braquage, de collision ou d'écart à la référence.
- La trajectoire humaine est une référence géométrique, pas une trajectoire obligatoire ni une autorisation implicite d'apprentissage par imitation.
- L'objectif top 1 000 puis top 50 est une comparaison de chronos à documenter, pas une garantie ni une inscription officielle.
- Le pont `plugins/TrackmaniaRLBridge.as` et sa copie installée peuvent être modifiés si nécessaire (D36) : sauvegarde préalable, version incrémentée, copies identiques, tests, rapport. `TelemetrieVoiture.as`, les autres plugins, les binaires, les mods et les réglages TMInterface restent exclus.

## Procédure

1. **Délimiter le mandat.** Relever le jalon, ses preuves attendues, le budget et les conditions d'arrêt. Si une permission bloque une action, demander uniquement cette permission et poursuivre seulement les tâches indépendantes autorisées.
2. **Inspecter avant de concevoir.** Utiliser `search_files` et `read_file` pour retrouver les définitions et usages. Vérifier les dépendances déclarées avant de choisir une bibliothèque. Ne pas modifier les démonstrateurs par simple commodité.
3. **Auditer l'intégration réelle.** Identifier la version de TMInterface et consulter son API. Documenter chaque source de télémétrie, ses unités, ses repères et son rythme. Ne pas inventer un champ manquant ni recopier une glisse globale sur les quatre roues.
4. **Prouver la transition.** Relier état, action, durée simulée et état suivant. Mesurer latence et données périmées. Vérifier les resets, checkpoints et arrivées. Relâcher les inputs après erreur ; invalider les transitions corrompues.
5. **Tester les règles hors jeu.** Couvrir projection, croisements, reculs, sauts, normalisation, progression et statuts terminaux. Les fixtures synthétiques restent explicitement synthétiques.
6. **Calibrer la récompense.** Tester que les allers-retours, resets, checkpoints répétés et abandons ne deviennent pas rentables. Évaluer les retours avec l'actualisation et les règles terminales réellement utilisées. Ne pas sélectionner les modèles sur la seule récompense.
7. **Mener une expérience bornée.** Formuler une hypothèse, conserver configuration et versions, définir un budget et enregistrer tous les essais. Ne pas lancer d'entraînement long, de dépense ou de processus durable sans accord.
   - D37 : l'utilisateur lance et pilote les entraînements. Livrer l'outillage : commandes lancer, arrêter, reprendre et évaluer, tableau de bord en direct, données de run lisibles sans Hermes. Le prouver par de courts essais de fumée. Ne pas attendre la fin d'un long run pendant un goal. Terminer par les commandes à lancer et les endroits où regarder.
8. **Évaluer séparément.** Utiliser politique et normalisation figées, départ normal, courses complètes, temps du jeu et checkpoints valides. Rapporter meilleur temps, distribution, réussite, latence et nombre d'essais.
9. **Clore avec des preuves.** Mettre à jour le jalon et les décisions uniquement selon les résultats observés. Conserver les artefacts et signaler les limites. Ne pas passer au jalon suivant hors mandat.

## Organisation avec Hermes

Proposer initialement un coordinateur et un goal borné. Déléguer seulement les tâches indépendantes ; préciser à chaque assistant les fichiers, contraintes et preuves attendues. Un seul contrôleur par instance de jeu et un seul propriétaire d'écriture par fichier, sauf isolation explicite.

Avant d'utiliser une fonction Hermes nouvelle ou ambiguë, charger `hermes-agent` et vérifier la documentation officielle. Un goal persistant ne constitue pas à lui seul une supervision d'entraînement hors session.

## Pièges connus

- Le démonstrateur initial envoie depuis `Render()` avec un intervalle minimal de 200 ms. Ce n'est pas une preuve de synchronisation RL.
- `Turning Rate` doit être défini ; ne pas le confondre arbitrairement avec la commande de direction.
- Les repères et encodages ne se déduisent pas des barres d'une capture.
- Le schéma de normalisation appartient au checkpoint évalué.
- Une projection au point le plus proche peut choisir un mauvais secteur ; tester la continuité et les checkpoints.
- Le nom « 5700 » ne suffit pas à affirmer une compatibilité GPU ou à installer un backend.
- Le projet initial utilise Python `>=3.13` et ne déclare pas de dépendances RL ; vérifier la compatibilité avant installation.
- Un test mocké, une lecture statique et une expérience dans le vrai jeu apportent des preuves différentes.

## Vérification

- Les critères du goal sont tous satisfaits ou explicitement bloqués.
- Les commandes citées existent et leurs résultats ont été observés.
- Aucun résultat, chrono, disponibilité d'API ou rang n'a été inventé.
- Les composants préexistants restent préservés hors modifications autorisées.
- Les choix nouveaux figurent dans `docs/DECISIONS.md` et les résultats dans une fiche conforme à `docs/EXPERIMENTS.md`.
- Le rapport final distingue modifications, vérifications et travail restant.

## Entretien

Conserver ici les procédures réutilisables et les corrections de méthode. Conserver les métriques, chemins d'expériences et tâches temporaires dans le dépôt, pas dans le skill ou la mémoire globale. Après modification, vérifier le frontmatter et la concordance avec la copie installée.
