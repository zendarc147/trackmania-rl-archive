# Architecture cible

Depuis J4-15, `env.py` peut ajouter le contexte d’abandon au schéma v2 (27 entrées). `checkpoint_migration.py` étend les entrées des réseaux sans changer leurs sorties initiales ; le replay et les optimiseurs sont neufs. `critic_diagnostics.py` mesure des erreurs sur des sondes fixes et audite les checkpoints hors jeu. Contrat et limites : [OBSERVATIONS](OBSERVATIONS.md), [rapport J4-15](reports/J4-critic-corrections-20261001.md).

## 1. Statut et intention

Ce document conserve l’architecture cible. Les contraintes approuvées sont recensées dans [DECISIONS](DECISIONS.md). Depuis J1–J4, le transport, les observations, l’environnement et une première chaîne SAC sont implémentés. Leur validation reste limitée aux preuves des rapports ; J4 est partiel.

Chaîne actuelle : `bridge.py` / `protocol.py` → `env.py` avec `geometry.py`, `observation.py` et `reward.py` → `gym_env.py` / `actions.py` → `training.py`. `runtime.py` assemble les profils de map ; `evaluation.py` charge une politique figée séparément. `scripts/tm.py` fournit la CLI et TensorBoard ; `webui.py` fournit une interface HTTP locale qui invoque cette même CLI et lit les artefacts de run, avec un verrou de contrôleur partagé. Voir [guide J4](GUIDE-J4.md) et [rapport J4](reports/J4-apprentissage.md). `hybrid_sac.py` fournit le SAC hybride D25 ; `compare.py` compare des runs à budget commun. La relaxation argmax4 n’est pas ce bras hybride. La comparaison contrôlée D25 et D28 complet restent ouverts.

Le système doit apprendre une politique spécialisée sur une map, choisir ses commandes pendant la course et minimiser le temps d'une arrivée valide. L'entraînement doit pouvoir être reconfiguré pour une autre map sans réécrire l'environnement générique.

Le mode « sans contraintes humaines » autorise les mouvements efficaces, pas la modification de la physique ou du chronomètre pour fabriquer une performance comparable.

## 2. Deux systèmes distincts

### Système de conduite et d'apprentissage

- Le jeu produit un état de simulation.
- Le pont TMInterface expose cet état et reçoit les commandes.
- Le constructeur d'observations combine la télémétrie et la position relative au parcours.
- La politique choisit la direction, l'accélération et le frein.
- L'environnement applique l'action, attend une transition définie et calcule récompense et statut de l'épisode.
- L'entraîneur met à jour les paramètres sur des transitions validées.
- L'évaluateur utilise une politique figée, sans apprentissage pendant l'évaluation.

### Système de développement Hermes

Hermes recherche, développe, teste et analyse. Il ne choisit pas les commandes à chaque pas de jeu. Son indisponibilité ne doit pas empêcher un pilote déjà lancé de fonctionner.

Proposition de départ : un coordinateur avec un goal borné. Déléguer éventuellement une revue, des tests de géométrie ou une comparaison bibliographique. Ne pas laisser deux agents commander le même jeu ni modifier simultanément les mêmes fichiers.

Les expériences longues devront être exécutées par des processus supervisés, avec reprise et budget explicites. Leur survie à une fermeture du chat sera vérifiée séparément ; elle ne découle pas de la présence d'un goal.

Partage des rôles (D37) : Hermes construit et vérifie l'outillage ; l'utilisateur lance et pilote les entraînements. L'outillage attendu :

- une commande par action (lancer, arrêter proprement, reprendre, évaluer), pilotée par un fichier de `configs/training/` ;
- un tableau de bord en direct (TensorBoard ou équivalent ; petit site local si utile) : récompense et ses termes, Progress, statuts de fin, chronos, pertes SAC, débit, latence, incidents ;
- un répertoire `runs/<id>/` autonome par run, lisible sans Hermes, pour le dépannage ;
- un guide court qui décrit ces commandes et où regarder.

## 3. Composants et responsabilités

| Composant proposé | Responsabilité | Ne doit pas faire |
| --- | --- | --- |
| Pont TMInterface | Lecture, commandes, contrôle du cycle de course, santé de connexion | Calculer une stratégie de conduite |
| Transport | Messages versionnés, ordre, identifiants et erreurs | Masquer une perte de synchronisation |
| État brut | Conserver les valeurs et conventions du jeu | Imposer l'encodage neuronal |
| Référence de parcours | Enregistrement, préparation, projection, checkpoints | Forcer l'agent à copier la conduite humaine |
| Observations | Repères, normalisation, ordre des entrées, validation | Ajouter des informations futures non autorisées |
| Actions | Bornes, traduction et maintien des commandes | Ajouter des commandes de respawn au modèle |
| Récompense | Composantes séparées et règles testées | Décider seule du meilleur modèle |
| Environnement | Reset, transition, réussite, échec, troncature | Dépendre d'un algorithme particulier |
| Entraînement | Optimisation et sauvegarde reproductible | Faire passer une simulation synthétique pour le jeu |
| Évaluation | Courses complètes, chrono et fiabilité | Modifier le modèle évalué |
| Expériences | Configurations, métriques, artefacts et budgets | Écraser un résultat antérieur |

## 4. Synchronisation : premier risque à lever

La démonstration actuelle publie depuis `Render()` avec un intervalle minimal de 200 ms. Elle n'établit pas un protocole de transition RL. Ne pas la réutiliser telle quelle comme preuve d'une boucle de contrôle fiable.

Chaque transition devra pouvoir relier :

- un identifiant d'épisode et un identifiant d'action ;
- un état avant action, une commande appliquée et un état après action ;
- le temps de simulation écoulé, indépendamment du temps mural ;
- les événements de checkpoint, d'arrivée, de reset et d'erreur.

À vérifier dans l'installation réelle : callbacks disponibles, fréquence physique, application et maintien des inputs, horodatage, fin de course, reset, commandes analogiques, et éventuel contrôle de l'avancement de simulation.

Deux modes sont à étudier, sans présumer leur disponibilité : boucle synchronisée par pas de simulation, ou contrôle temps réel avec cadence et délais mesurés. Le choix doit rester compatible avec l'exigence de décisions pendant la course. Un entraînement accéléré ne sera accepté qu'après vérification de la physique et avec évaluation finale en conditions temps réel.

Prévoir une règle explicite en cas de calcul trop lent : ne pas varier silencieusement la durée des actions. Mesurer latence médiane, latence haute, âge des observations et pas manqués. Sur perte de connexion, libérer les commandes et invalider l'épisode.

## 5. Modèle et algorithme : SAC retenu, détails en J4

L'algorithme retenu est **SAC** (Soft Actor-Critic), décision D15 de l'utilisateur. Il est off-policy, donc réutilise les transitions via un replay buffer, ce qui compte avec un débit de collecte limité, et gère nativement la direction continue. L'ancienne comparaison PPO/SAC (P02) est remplacée.

Restent à décider en J4 : framework et compatibilité Python 3.13, traitement de l'accélération et du frein binaires (D25 : comparer seuillage de sorties continues et action hybride), hyperparamètres, taille et conservation du replay buffer, et sa restauration à la reprise. Aucune dépendance n'est encore ajoutée.

Questions de comparaison :

- Combien de transitions le jeu permet-il réellement de collecter ?
- Quel coût de calcul le matériel peut-il soutenir sans perturber le contrôle ?
- Accélération et frein sont-ils binaires ou analogiques dans l'interface retenue ?
- Quel budget d'essais permet une comparaison honnête ?
- Les observations instantanées suffisent-elles, ou faut-il tester un historique ou une politique récurrente ?

Décidé (D16) : un petit MLP 2×256 pour données numériques, sans traitement d'images. Tester les extensions seulement sur mesure. L'historique, la récurrence et les points de parcours à venir ne sont pas utilisés au départ (D18) ; l'imitation est rejetée (D19).

La trajectoire humaine est d'abord une référence géométrique. Elle n'autorise pas automatiquement un apprentissage par imitation.

## 6. Matériel

Informations déclarées par l'utilisateur, non auditées :

- Laptop : `AMD Ryzen AI 7 350 (16) @ 2.00 GHz`.
- Serveur : un Ryzen 5 plus ancien et une « 5700 » comme GPU.

Ne pas interpréter `(16)` comme un nombre de cœurs physiques vérifié, ni « 5700 » comme une référence complète. RAM, VRAM, pilote, disponibilité du serveur et compatibilité du framework restent inconnus. Ne pas présumer CUDA, ROCm ou l'utilisation du NPU.

Proposition : établir une exécution CPU fonctionnelle pour les tests et mesurer avant de choisir une accélération matérielle. La décision laptop/serveur repose sur le débit de transitions, la latence de politique, la charge du jeu et la compatibilité réelle. Ne pas installer de pilote ou déplacer le jeu sans accord.

## 7. Arborescence future proposée

Ces chemins sont des responsabilités prévues, **pas des imports existants**. Ne créer un module qu'au moment de lui donner un comportement testable.

```text
src/trackmania_rl/
  bridge/          # transport et adaptateur TMInterface
  telemetry/       # état brut et validation
  reference/       # enregistrement et géométrie du parcours
  observations/    # encodage et normalisation
  actions/         # commandes et traduction
  rewards/         # composantes et règles terminales
  env/             # cycle des épisodes
  training/        # intégration de l'algorithme retenu
  evaluation/      # courses complètes et métriques
  experiments/     # métadonnées et artefacts
  cli/             # commandes à définir après les contrats
plugins/           # futur pont du jeu ; démonstrateur actuel préservé
configs/
  maps/            # identité de map, référence, checkpoints
  training/        # hyperparamètres et budget
  evaluation/      # protocole figé
  machines/        # paramètres locaux non secrets
scripts/           # utilitaires justifiés et testés
tests/
  unit/
  integration/
  live/            # tests nécessitant le jeu, opt-in
data/              # références et captures, hors Git par défaut
runs/              # résultats immuables par expérience
models/            # checkpoints associés à leur schéma
```

Avant les premiers artefacts lourds, définir la politique `.gitignore`, conservation, sauvegarde et quotas. Aucun de ces répertoires n'est créé artificiellement par cette phase documentaire.

## 8. Réutilisation sur une autre map

Le profil de map devra fournir son identifiant, sa version ou empreinte, sa référence, ses checkpoints et les limites d'épisode. Les unités et la logique générique restent communes. La normalisation et les réglages d'entraînement sont versionnés, pas supposés universels.

Valider la réutilisation sur une seconde map avant de prétendre supporter n'importe quelle map. Les croisements, boucles, surfaces inclinées et sauts constituent des cas de test, pas des problèmes réputés résolus.

## 9. Portes de validation

1. Télémétrie et contrôle réels démontrés avant l'entraînement.
2. Projection et récompense testées avant les longs essais.
3. Choix de l'algorithme documenté avant une recherche d'hyperparamètres.
4. Budget approuvé avant tout entraînement long.
5. Évaluation temps réel depuis le départ normal avant toute revendication de performance.

Le détail des preuves est dans [ROADMAP](ROADMAP.md).
