# Contrat de mission pour Hermes

## Statut

### Contrat actif J6 — 2 octobre 2026

- Mandat : demande utilisateur du 2 octobre 2026 : « je veux que tu execute l'etape J6 et que tu t'arrete pas tant que tout est validé ». Le contrôle de la voiture est autorisé ; A01 était chargée par l'utilisateur. Ce qui est déjà fait n'est pas modifié.
- Fait : relevé D30 daté (TMX, seuil top 1 000 = 24,23 s, à battre strictement). Configuration `a01_sac_hybrid4_v6_lap_fromB`, avec récompense v3 et départ du checkpoint J5, sans changement d'observations ni de pont. Run `runs/j4/j6-v6-lap-B` lancé par l'agent sous ce mandat : 525 k transitions, meilleur temps 26,98 s.
- Complément du 4 octobre 2026 (demande utilisateur : trouver pourquoi v11 perd environ 1 s sur la rampe finale et corriger sans tricher) : diagnostic mesuré, puis correctif D41 (proposition) et configurations v12 et v12s. Seul un essai de fumée a été fait. J6 reste non validé. Voir le [rapport J6](docs/reports/J6-chrono.md#rampe-finale--diagnostic-du-4-octobre-et-correctif-v12).
- Résultat : **J6 partiel, non validé**. La machine a redémarré à 14:40 et le jeu est fermé ; A01 doit être rouverte par l'utilisateur. Il manque environ 2,7 s. Les leviers suivants demandent un accord : observations v3 (D18) et replays TMX rapides pour le diagnostic. Voir le [rapport J6](docs/reports/J6-chrono.md).

### Contrat J5 (clos) — 2 octobre 2026

- Mandat : demande utilisateur du 2 octobre 2026 : « je veux que tu execute l'etape J5 et que tu t'arrete pas tant que tout est validé ». Le contrôle de la voiture est autorisé pour cette session ; A01 est déjà chargée par l'utilisateur. Cette demande ouvre J5 bien que J4 reste partiel ; les cases J4 ouvertes (D25 entraînement contrôlé, D22/D23) ne sont pas cochées rétroactivement.
- Périmètre : évaluation figée de checkpoints existants, comparaison contrôlée, rapport et documents. Aucun nouvel entraînement long (D37), aucune modification d'observations, de récompense ou du pont, aucun modèle de référence remplacé ou supprimé, aucun commit.
- Protocole enregistré **avant la campagne** : `runs/j5/protocol.json` (03:53:27 +09:00, campagne B démarrée à 03:53:35), empreintes `runs/j5/hashes-before.txt`. Critère D33 : au moins 18 arrivées sur 20 tentatives, ×1 temps réel, politique déterministe figée, départ normal, échecs et erreurs techniques au dénominateur. Trois candidats évalués avec le même protocole ; le candidat retenu est confirmé par une seconde campagne de 20 tentatives rechargée depuis le disque.
- Résultat : **J5 validé**. `a01-v4-obs2b/00100000` donne 20/20, puis 19/20 en confirmation (39/40), avec un meilleur temps de 26,97 s et une médiane de 27,06 s. Les empreintes avant et après sont identiques. Voir le [rapport J5](docs/reports/J5-fiabilite.md).

### Historique J4

Mission J4 demandée par l’utilisateur le 29 septembre 2026. J1, J2 et J3 sont clos (contrats conservés ci-dessous pour l’historique). Aucun passage à J5 n’est autorisé. Les critères restent ouverts tant que leurs preuves ne sont pas acquises.

### Contrat J4 (partiel, conservé)

#### Reprise du jalon — demande actuelle

- Mandat : achever uniquement J4 sur A01 ; ne pas lancer J5 ni revendiquer une performance non mesurée. Les preuves J4 antérieures restent historiques, et les critères ouverts de `docs/ROADMAP.md` ne sont cochés qu'après vérification.
- Autorisations J4 déjà données le **29 septembre 2026** (détaillées ci-dessous) : PyTorch CPU, Stable-Baselines3, Gymnasium et TensorBoard via uv, après vérification Python 3.13 ; toute autre dépendance demande accord. Simulation jusqu'à ×10, **une instance** ; mesure D22 et contrôle de fidélité avant accélération. Budget initial : 2 h simulées / 144 000 transitions à 50 ms ; mesure puis proposition chiffrée avant entraînement. Mission 3 h, jeu 1 h sous contrôle, stockage 5 Gio dans `runs/j4/`. Ces plafonds sont **historiques**, levés pour J4 par l'amendement utilisateur ci-après ; ne pas les rétablir implicitement. Chaque run garde une borne et une trace de consommation ; les entraînements longs restent lancés et suivis par l'utilisateur (D37).
- Machine, plugin, modèles et ouverture manuelle d'A01 : règles J3 reprises, sauf extensions J4 déjà autorisées et D36 pour le pont. CPU local Linux, uv, aucun autre profil ou service payant ; sauvegarde et version du pont avant modification, copies identiques, autres plugins exclus. A01 est ouverte par l'utilisateur depuis le menu ; aucun chargement automatique. **La permission historique de piloter le jeu était limitée à sa session** : attendre une confirmation pour toute nouvelle session de test réel avant d'envoyer des commandes au jeu ou de le lancer.
- Périmètre de cette reprise : résoudre la comparaison avec une vraie action hybride D25, la validation d'arrivée en évaluation D28 et les limites de l'outillage D37. Essais hors jeu permis ; essais réels courts seulement avec autorisation de session. Ne pas remplacer les modèles de référence, supprimer des données, committer ou pousser.
- Arrêt : permission nécessaire absente, dépendance incompatible ou capacité essentielle inaccessible ; signaler exactement les critères encore ouverts.

#### Correction du critique — accord du 1er octobre 2026 (J4-15)

Après le diagnostic J4-14, l'utilisateur demande « fait toute les correction que tu me recommande ». Périmètre accepté : corriger le warmup de `init_from`, ajouter les deux observations du contexte d'abandon proposées (temps restant et écart au record), migrer explicitement les réseaux v1 vers v2, préparer une configuration de reprise auditée et des diagnostics reproductibles. Cette extension limitée de D31 remplace l'exclusion des modifications d'observations dans le contrat historique ci-dessous. Les autres observations et les règles de récompense/terminaison restent inchangées. Les modèles et buffers existants sont préservés ; la migration crée un nouveau run avec un replay et des optimiseurs neufs. D37 reste applicable : tests hors jeu par l'agent, entraînement et validation réelle par l'utilisateur. Voir le [rapport de correction](docs/reports/J4-critic-corrections-20261001.md).

#### Amendement utilisateur du 29 septembre 2026 — suppression des plafonds

L’utilisateur a explicitement indiqué : « il n'y a pas de buget on s'en fous fait ce que tu veux. met ca dans la doc ».

Pour J4 uniquement, les plafonds chiffrés de mission, de jeu, de stockage et d’entraînement ci-dessous sont levés, y compris la limite proposée de 4 000 transitions de fumée. Les budgets initiaux restent consignés ci-dessous comme historique, et non comme conditions d’arrêt actives. Le dépassement constaté avant cet amendement reste documenté : 5 702 transitions de fumée, dont 3 700 pour threshold et 2 002 pour argmax4. Cet amendement ne constitue pas une autorisation rétroactive.

La poursuite de J4 est autorisée. Les exécutions gardent des compteurs ; les budgets de transitions restent le défaut. D37 reste applicable : l’utilisateur lance les entraînements longs, l’agent prépare et vérifie l’outillage par de courts essais. Les limites non budgétaires restent inchangées : A01, J4 seulement, CPU local, une instance, vitesse au plus ×10, dépendances autorisées, protection des fichiers et plugins, aucun service payant ni processus après fermeture du chat. Les conditions d’arrêt pour permission manquante, incompatibilité ou capacité essentielle inaccessible restent actives. Le 30 septembre 2026, l’utilisateur a demandé explicitement de pouvoir poursuivre son run `20260930-104918-a01_sac_hybrid4_v2_ent05` sans plafond de transitions jusqu’à son ordre d’arrêt ; l’option `resume --until-stopped` répond à cette demande, sans lancer l’entraînement depuis l’agent.

#### Résultat intermédiaire documenté

J4 reste **partiel** : [rapport](docs/reports/J4-apprentissage.md), [guide utilisateur](docs/GUIDE-J4.md), fiche J4-SMOKE-01 dans `docs/EXPERIMENTS.md`. Tests hors jeu : 63 réussis à la consolidation. Reprise et outillage exercés ; 5 702 transitions réelles de fumée. D25 n’est pas satisfait par la relaxation argmax4. Complément D28 : 20 tentatives par politique figée à ×1 en temps réel, zéro arrivée chacune, hashes modèle/normalisation inchangés (rapport §6 bis). Le chemin d’arrivée officielle reste non validé. Aucune performance ni clôture J4 annoncée. Les cases de ROADMAP distinguent preuves acquises et exigences ouvertes.

Reprise du 29 septembre 2026 (19:20), autorisation de session pour essais réels courts : sauvegarde atomique et RNG à la reprise, commande `compare`, pont 0.4.0 installé (D36), sonde d’arrivée non empêchée, fumée hybride réelle 2 600 transitions, évaluation figée hybride en mode arrivée officielle ; 69 tests hors jeu OK. D37 coché. Restent ouverts : comparaison contrôlée D25 (runs utilisateur à budget et seeds égaux), chrono officiel enregistré et arrivée d’une politique apprise (D28). Rapport §9.

Complément du 30 septembre 2026 (J4-07) : run de nuit utilisateur sans apprentissage ; corrections approuvées par l’utilisateur (entropie hybride par tête, récompense v2 pondérée, actualisation 0,905/s, outil `trend`). Hors jeu seulement ; test de contrôle de 30 min à lancer par l’utilisateur. Rapport §10.

#### Contrat initial et propositions historiques

- Jalon : uniquement J4 « Premier apprentissage et boucle d’évaluation » de `docs/ROADMAP.md`, pour A01 (UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, 3 checkpoints arrivée incluse). Valeurs propres à A01 dans `configs/maps/a01.json` et dans les configurations de run ; aucune dans les composants génériques.
- Autorisations données par l’utilisateur le 2026-09-29 vers 16:45 +09:00 :
  - **Dépendances** : PyTorch CPU, Stable-Baselines3 (avec gymnasium) et TensorBoard, ajoutées avec uv après vérification de leur compatibilité avec Python 3.13. Toute autre dépendance, ou une variante GPU, exige une demande préalable.
  - **Mesure du débit (D22)** : vitesse de simulation jusqu’à ×10 ; **1 instance** du jeu au maximum. Vérifier l’identité de la physique en accéléré (même contrôleur déterministe, mêmes états) avant d’utiliser une vitesse > 1.
  - **Budget d’entraînement (D23)** : plafond **2 h simulées, soit 144 000 transitions** de 50 ms (D26). Après la mesure du débit, proposer un budget chiffré dans ce plafond et le noter dans ce contrat et dans la configuration avant tout lancement. Selon D37, l’agent ne lance que de courts essais de fumée ; l’entraînement complet est lancé par l’utilisateur.
  - **Budgets de mission** : mission 3 h, jeu 1 h cumulée sous contrôle, stockage 5 Gio dans `runs/j4/`. Début de suivi : 2026-09-29 16:41 +09:00 ; fin au plus tard 19:41 +09:00.
- Machine : laptop local Linux (D21), calcul CPU uniquement ; Python 3.13, uv. Aucun pilote, backend GPU ou changement système.
- Plugin : modification du pont `plugins/TrackmaniaRLBridge.as` et de sa copie installée autorisée si nécessaire, aux conditions de D36 (sauvegarde sous `runs/j4/`, version incrémentée, copies identiques, tests, rapport). `TelemetrieVoiture.as`, les autres plugins, les binaires, les mods et les réglages TMInterface restent exclus.
- Jeu local autorisé pendant cette session : mode synchrone pour la collecte (D20), mode temps réel pour mesurer la latence de décision ; épisodes courts de mesure, de fumée et d’évaluation ; resets par l’environnement. L’utilisateur lance A01 depuis le menu ; le chargement automatique de map n’est pas tenté.
- Modèles : modèle courant uniquement ; aucun assistant, service payant ou processus après fermeture du chat.
- Périmètre : intégration SAC (D15, D16), interface d’action et comparaison du traitement des commandes binaires (D25), entraîneur, sauvegarde et reprise, évaluateur figé, mesures de débit et de latence, outillage utilisateur (D37 : commandes, configurations `configs/training/`, tableau de bord, guide), tests, rapport `docs/reports/J4-apprentissage.md` et fiche d’expérience ; mise à jour de `GOAL.md`, `README.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/EXPERIMENTS.md`, `docs/ARCHITECTURE.md` selon les preuves. Préserver les démonstrateurs, le pont et les modules J1 à J3 hors modifications nécessaires et documentées.
- Données : runs sous `runs/j4/` (ignoré par Git). Transitions d’essai de fumée marquées comme telles ; les fixtures synthétiques restent marquées synthétiques. Aucune performance annoncée sans évaluation D28.
- Points non tranchés, à signaler sans les convertir en décisions : coefficients de récompense v1 (J3-02) et seuils du tracker (J2-09) restent des **propositions** ; les runs J4 les utilisent en le déclarant dans leur configuration.
- Hors périmètre : entraînement long lancé ou attendu par l’agent, plusieurs instances, vitesse > ×10, GPU ou serveur, modification des observations (D31), imitation (D19), départs intermédiaires ou maps modifiées (D24), campagne J5.
- **Budget chiffré proposé (D23), noté le 2026-09-29 à 17:25 après la mesure du débit**, dans le plafond de 144 000 transitions :
  - mesure (`runs/j4/20260929-170056-throughput`) : 5 courses complètes du contrôleur scripté à ×1, ×2, ×4, ×6, ×10, **physique identique bit à bit** à ×1 (positions, vitesses, checkpoints, 610 transitions chacune) ; ×10 = 200 transitions par seconde murale, 10 s simulées par seconde, sans calcul d’apprentissage ;
  - essais de fumée de l’agent : au plus 4 000 transitions au total ;
  - entraînement utilisateur : **2 runs de 70 000 transitions** (58,3 min simulées chacun), un par traitement des commandes binaires (D25 : `threshold_v1`, `argmax4_v1`), seed 1, vitesse ×10. Plafond par run inscrit dans la configuration (`cap_transitions = 72 000`) ;
  - total prévu ≤ 144 000 transitions (2 h simulées). Tout dépassement exige un nouvel accord.
- Arrêt : budget atteint, permission manquante, dépendance incompatible, modification système nécessaire ou capacité essentielle inaccessible ; documenter alors un résultat partiel ou bloqué.

### Contrat J3 (clos)

- Jalon : uniquement J3 « Environnement et récompense testables » de `docs/ROADMAP.md`, pour A01 (UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, 3 checkpoints arrivée incluse). Valeurs propres à A01 dans `configs/maps/a01.json` uniquement.
- Décisions de l’utilisateur du 2026-09-29, à reporter dans `docs/DECISIONS.md` :
  - J2-08 approuvé : schéma d’observation v1 (25 valeurs) en décision validée ;
  - `rear_gear` non ajouté aux observations du modèle ;
  - J2-09 (seuils du tracker) reste une **proposition**, à mesurer pendant J3.
- Machine : laptop local Linux ; Python 3.13, uv. Python : bibliothèque standard uniquement, aucune dépendance ajoutée.
- Périmètre : code, tests, configurations et rapport J3 dans ce dépôt (environnement, transitions, récompense, contrôleur de test) ; mise à jour de `GOAL.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/REWARDS.md`, `docs/OBSERVATIONS.md` selon les preuves. Préserver les démonstrateurs, le pont J1 et les modules J2.
- Plugin installé : **NON**, comme en J2. Le pont 0.1.0 installé est utilisé tel quel. *Remplacé le 2026-09-29 par D36 : modification du pont autorisée si nécessaire (pont 0.2.1 installé).*
- Jeu local autorisé pendant cette session : mode synchrone uniquement, épisodes courts pilotés par un contrôleur de test scripté, nommé et marqué comme **non appris** ; resets par l’environnement (`GiveUp`). L’utilisateur lance A01 depuis le menu ; le chargement automatique de map n’est pas tenté.
- Budgets : mission 2 h, jeu 30 min cumulées, traces 500 Mio dans `runs/j3/`. Début de suivi : 2026-09-29 15:37 +09:00 ; fin au plus tard 17:37 +09:00.
- Modèles : modèle courant uniquement ; aucun assistant, service payant ou processus après fermeture du chat.
- Données : les traces vont dans `runs/j3/` (ignoré par Git). Les fixtures synthétiques sont marquées comme telles ; aucune transition du contrôleur de test n’est présentée comme apprentissage.
- Hors périmètre : algorithme, framework, entraînement, choix des hyperparamètres SAC, vitesse de simulation supérieure à 1, plusieurs instances.
- Arrêt : budget atteint, permission manquante, modification système nécessaire ou capacité essentielle inaccessible ; documenter alors un résultat partiel ou bloqué.

Résultat J3 : critères de `docs/ROADMAP.md` cochés avec preuves, voir [le rapport J3](docs/reports/J3-environnement.md) et la fiche J3-ENV-01 de `docs/EXPERIMENTS.md`. Budget consommé : environ 28 min de mission, environ 6 min de jeu sous contrôle, 3,9 Mio de traces. Limite J3-03 (pas de reset après une arrivée avec le pont 0.1.0) levée ensuite par le pont 0.2.1, modification du plugin autorisée par l'utilisateur ; voir le rapport J3 §6 bis. Les coefficients de récompense v1 (J3-02) et les seuils du tracker (J2-09) restent des propositions.

### Contrat J2 (clos)

- Jalon : uniquement J2 « Référence et observations » de `docs/ROADMAP.md`, pour A01 (UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, 3 checkpoints arrivée incluse).
- Machine : laptop local Linux ; Python 3.13, uv. Python : bibliothèque standard uniquement, aucune dépendance ajoutée.
- Périmètre : code, tests, configurations et rapports J2 dans ce dépôt ; mise à jour de `GOAL.md`, `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/OBSERVATIONS.md` selon les preuves. Préserver les démonstrateurs et le pont J1.
- Jeu local autorisé pendant cette session :
  - pont passif (`CFG 0 … 1`, aucun input ni reset envoyé) pendant la conduite humaine d’A01 ;
  - contrôle automatique court, seulement pour valider les conventions (sens de x, repère de `angular_velocity`, orientation).
- L’utilisateur lance A01 depuis le menu ; le chargement automatique de map n’est pas tenté.
- Course de référence : complète, sans respawn, départ normal, arrivée confirmée par le jeu. Toute course invalide est rejetée et refaite.
- Plugin installé : **NON**, validé par l’utilisateur le 2026-09-29 vers 14:11 +09:00. Le pont 0.1.0 installé est utilisé tel quel.
- Budgets : mission 2 h, jeu ouvert 30 min cumulées, traces 500 Mio. Début de suivi : 2026-09-29 14:04 +09:00 ; fin au plus tard 16:04 +09:00.
- Modèles : modèle courant uniquement ; aucun assistant, service payant ou processus après fermeture du chat.
- Données : les traces vont dans `runs/j2/` (ignoré par Git). Les fixtures synthétiques sont marquées comme telles ; les statistiques de normalisation viennent de courses réelles marquées comme telles.
- Arrêt : budget atteint, permission manquante, modification système nécessaire ou capacité essentielle inaccessible ; documenter alors un résultat partiel ou bloqué.

Résultat J2 : critères de `docs/ROADMAP.md` cochés avec preuves, voir [le rapport J2](docs/reports/J2-observations.md). Budget consommé : environ 41 min de mission, environ 14 min d’interactions en jeu, 46 Mio de traces et artefacts. Le schéma d’observation v1 a ensuite été approuvé (D31).

### Contrat J1 (clos)

- Machine : laptop local Linux, AMD Ryzen AI 7 350 (8 cœurs, 16 threads), 30 Gio de RAM ; Python 3.13.9, uv 0.9.5.
- Périmètre : pont, tests et rapports J1 dans ce dépôt ; mise à jour des documents concernés. Préserver les démonstrateurs.
- Jeu : lancement de TMNF/TMInterface, sélection d’A01, contrôle automatique local, resets et tests d’arrêt/déconnexion autorisés pendant cette session.
- Installation : ajout d’un plugin J1 distinct dans le dossier `Documents/TMInterface/Plugins` du préfixe Steam `11020`. Sauvegarder les fichiers touchés ; restaurer les réglages temporaires. Ne pas remplacer `TelemetrieVoiture.as`, modifier les binaires, ni mettre à jour les mods.
- Python : bibliothèque standard uniquement, aucune dépendance supplémentaire.
- Budgets après accord : 2 h de mission, 20 min cumulées d’essais en jeu, 250 Mio de traces numériques. Début de suivi : 2026-09-29 13:24:33 +09:00 ; fin au plus tard 15:24:33 +09:00. Le temps de préparation avec jeu ouvert compte dans le budget en jeu par prudence.
- Modèles : modèle courant uniquement pendant cette durée ; aucun assistant, service payant supplémentaire ou processus après fermeture du chat.
- Frontière J1/J2 confirmée : auditer les données brutes ; conserver explicitement comme indisponibles les écarts à la référence et la progression géométrique tant que J2 n’a pas produit de référence. Ne retirer ni remplacer silencieusement aucun champ demandé.
- Arrêt : budget atteint, permission manquante, modification système nécessaire ou capacité essentielle inaccessible ; documenter alors un résultat partiel ou bloqué.

Inventaire statique : TMNF dans `~/.local/share/Steam/steamapps/common/TrackMania Nations Forever`, lanceur `~/.local/bin/launch-tmloader-steam` (Proton Hotfix, préfixe `11020`). DLL TMInterface 2.1.0 et 2.2.1 trouvées dans le stockage TMLoader ; version chargée à vérifier en exécution. Map : `GameData/Tracks/Campaigns/Nations/White/A01-Race.Challenge.Gbx`, SHA-256 `f0a870809be99da2cb36ad5df43a2cf63d8f74fe4ac3470ecac68b9e97625dc3`.

**Ambition de recherche :** un pilote spécialisé A01, jouant en temps réel à partir de télémétrie, avec un chrono local comparable au top 1 000 puis au top 50 mondial. Les seuils, la catégorie et la map exacte restent à identifier.

**Prochain objectif proposé : J1 — prouver la faisabilité de la boucle de contrôle TMInterface sous Linux.** Ne pas confier immédiatement « atteindre le top 50 » comme unique critère à un goal sans budget ni étapes.

## 1. Informations à compléter avant de lancer J1

Les champs non résolus qui empêchent une action doivent déclencher une question, pas une supposition. Un champ non nécessaire au jalon peut être reporté explicitement.

- [ ] Machine choisie : **À COMPLÉTER**.
- [ ] Version de TMInterface et chemin de lancement du jeu : **À RELEVER**.
- [ ] Fichier ou identifiant exact d'A01 : **À RELEVER**.
- [ ] Autorisation de contrôler brièvement le jeu local : **OUI / NON**.
- [ ] Autorisation de créer un prototype de pont et des tests dans le dépôt : **OUI / NON**.
- [ ] Autorisation de modifier le plugin installé : **OUI / NON**, avec sauvegarde et périmètre.
- [ ] Dépendances Python supplémentaires autorisées : **À COMPLÉTER**.
- [ ] Durée maximale de la mission et des essais en jeu : **À COMPLÉTER**.
- [ ] Budget d'utilisation des modèles Hermes : **À COMPLÉTER**.
- [ ] Espace de stockage maximal pour les captures : **À COMPLÉTER**.
- [ ] Nombre maximal d'assistants simultanés : **À COMPLÉTER** ; proposition initiale : aucun sauf sous-tâche indépendante justifiée.
- [ ] Travail autorisé après fermeture du chat : **NON par défaut**, à approuver séparément.

Interdictions maintenues : dépenses non approuvées, changements système, migration Windows, jeu en ligne, commit ou push sans demande, suppression des fichiers existants, entraînement long pendant J1.

## 2. Résultat attendu de J1

Démontrer, avec une courte exécution réelle et traçable, la lecture d'un état de voiture et l'application d'une commande contrôlée. Identifier ce qui manque pour construire une transition RL fiable.

### Critères à cocher uniquement avec preuves

- [x] Installation et versions réelles recensées sans lire de secrets.
- [x] Champs de la capture associés à leurs sources, ou marqués indisponibles avec une justification.
- [x] `Turning Rate`, ordre des roues et unités clarifiés. Repère de la vitesse angulaire et sens de l'axe x enregistrés comme points ouverts pour J2.
- [x] Direction progressive appliquée et effet observé en jeu.
- [x] Accélération et frein testés ; leur nature binaire ou analogique documentée.
- [x] Temps de simulation distingué du temps mural.
- [x] Cadence, ordre des messages et latence mesurés.
- [x] Checkpoints, arrivée, reset et état hors course identifiés dans l'interface réelle.
- [x] Stratégie de synchronisation décrite et sa faisabilité testée.
- [x] Arrêt et déconnexion testés avec relâchement des inputs. L'arrêt du jeu n'a pas été testé.
- [x] Démonstrateurs existants préservés, avec empreintes identiques.
- [x] Rapport `docs/reports/J1-integration.md` produit avec commandes, mesures, traces et limites.
- [x] `docs/DECISIONS.md` et `docs/ROADMAP.md` mis à jour selon les preuves.

Preuves : voir [le rapport J1](docs/reports/J1-integration.md). Budget consommé : environ 41 min de mission, environ 15 min en jeu et 1,1 Mio de traces.

Le chemin du rapport est un livrable futur, pas un fichier déjà présent. Si un critère essentiel échoue, le jalon est bloqué ou partiel, jamais terminé par simple rédaction d'un rapport.

## 3. Prompt conseillé pour J1

À utiliser seulement après avoir rempli les permissions nécessaires. Les préfixes du contrat restent en anglais pour correspondre à la syntaxe documentée ; le contenu est en français.

```text
/goal Réaliser uniquement le jalon J1 de docs/ROADMAP.md selon le contrat de GOAL.md. Lire AGENTS.md, docs/DECISIONS.md et charger le skill trackmania-rl, ou lire sa copie dans skills/trackmania-rl/SKILL.md.
verify: Fournir les preuves réelles de chaque critère J1, les tests exécutés, les mesures et le rapport docs/reports/J1-integration.md. Aucun mock ne prouve une connexion au jeu. Aucun critère bloqué ne peut être coché.
constraints: Linux, TMNF, TMInterface, télémétrie uniquement, conduite en boucle fermée, direction progressive, accélération et frein. Préserver les fichiers existants. Aucun entraînement long, dépense, commit, push ou changement système non autorisé.
boundaries: Uniquement J1, les fichiers nécessaires dans le dépôt et les interactions en jeu expressément autorisées dans GOAL.md. Ne pas passer à J2 automatiquement.
stop when: Une permission ou un budget nécessaire manque, le jeu est indisponible, une donnée essentielle est inaccessible, une modification système est nécessaire ou le budget approuvé est atteint. Rapporter alors les preuves acquises et le blocage sans annoncer le jalon terminé.
```

Vérifier les commandes disponibles dans l'installation Hermes utilisée. La documentation officielle des goals est référencée à la fin de ce fichier. Le texte du prompt ne remplace pas les autorisations de l'utilisateur.

## 4. Modèle réutilisable pour chaque jalon suivant

- [ ] **Jalon :** identifiant et dépendances validées.
- [ ] **Résultat unique :** état observable attendu.
- [ ] **Périmètre :** fichiers, composants, outils et machine autorisés.
- [ ] **Hors périmètre :** fonctionnalités à ne pas ajouter.
- [ ] **Budget :** temps, épisodes ou transitions, stockage, coût des modèles.
- [ ] **Permissions :** installations, contrôle du jeu, processus hors session.
- [ ] **Livrables :** chemins et formats attendus.
- [ ] **Vérification :** commandes réellement disponibles et preuves en jeu nécessaires.
- [ ] **Critères de réussite :** cases binaires et seuils mesurables.
- [ ] **Conditions d'arrêt :** problème nécessitant une décision, budget atteint, erreur répétée.
- [ ] **Transmission :** décisions, limites et prochaine action documentées.

Ne pas écrire de commande de test fictive dans une quality gate. Ajouter une gate seulement quand sa commande existe et a été exécutée avec succès sur la portée visée.

## 5. Champs à compléter avant le premier entraînement

- [ ] Algorithme et framework, avec justification : algorithme **SAC** décidé (D15) ; framework **À DÉCIDER**.
- [ ] Machine, RAM, GPU exact, VRAM et backend utilisable : **À VÉRIFIER**.
- [ ] Schéma d'observation et normalisation : **À VALIDER**.
- [ ] Espace d'action, cadence et durée de maintien : **À VALIDER**.
- [x] Référence A01 enregistrée et projection testée : voir [rapport J2](docs/reports/J2-observations.md).
- [ ] Récompense, coefficients, discount et horizon : proposition v1 testée en J3 (J3-02), **À APPROUVER**.
- [ ] Timeout, absence de progression et règles terminales : seuils décidés (D27) ; abandon terminal et limite en troncature testés en J3, **À APPROUVER**.
- [ ] Nombre de seeds et budget de collecte : **À DÉCIDER**.
- [ ] Fréquence des sauvegardes et test de reprise : **À DÉCIDER**.
- [ ] Nombre de courses d'évaluation et fiabilité minimale : **À DÉCIDER**.
- [ ] Politique de conservation des données : **À DÉCIDER**.

## 6. Définition des objectifs de performance

### Palier top 1 000

- [ ] Map exacte et conditions comparables identifiées.
- [ ] Source de classement et catégorie : **À COMPLÉTER**.
- [ ] Date du relevé : **À COMPLÉTER**.
- [ ] Seuil de chrono : **À COMPLÉTER**, sans inventer une valeur.
- [ ] Protocole local et fiabilité exigée : **À COMPLÉTER**.
- [ ] Courses complètes valides sous le seuil, avec preuves enregistrées.

### Palier top 50

- [ ] Même identification de map et de catégorie, ou changement documenté.
- [ ] Source, date et seuil top 50 : **À COMPLÉTER**.
- [ ] Protocole de confirmation et nombre d'essais : **À COMPLÉTER**.
- [ ] Résultats reproduits avec politique figée, depuis le départ normal.
- [ ] Limites de comparaison expliquées ; aucune revendication d'inscription officielle.

## 7. Organisation avec Hermes

Proposition : un coordinateur et un goal par jalon. Les assistants ponctuels peuvent prendre en charge une recherche, une revue ou des tests indépendants. Ils ne contrôlent pas simultanément le jeu et ne se partagent pas des écritures non coordonnées.

La commande `/goal` organise une poursuite d'objectif dans une session ; elle ne crée pas automatiquement une équipe de bots. Une exécution d'entraînement durable doit avoir sa propre supervision et son propre budget.

La documentation officielle décrit les contrats de fin, les sous-objectifs et les quality gates. Leur disponibilité doit être vérifiée dans la version locale avant usage :

```text
https://hermes-agent.nousresearch.com/docs/user-guide/features/goals
```
