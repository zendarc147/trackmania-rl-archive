# Feuille de route et critères de validation

## Règle de suivi

Les cases représentent des résultats, pas des intentions. Chaque case terminée doit pointer vers une preuve. Le passage au jalon suivant n'est pas automatique : respecter le budget et le mandat du goal actif.

État initial : documentation créée ; intégration réelle, environnement RL et entraînement non validés. Les chemins de rapports ci-dessous sont des livrables futurs.

## J0 — Cadrage documentaire

Livrables : README, architecture, observations, récompense, décisions, expériences, contrat de goal, instructions des agents et skill.

- [x] Documents cohérents et liens internes contrôlés.
- [x] Choix validés séparés des propositions et questions ouvertes.
- [x] Skill de travail disponible et copie du dépôt synchronisée.
- [x] Code existant préservé ; aucun entraînement lancé.

Preuve de J0 : contrôle documentaire exécuté avec code de sortie 0 ; 10 documents présents et non vides, 12 liens locaux valides, blocs de code correctement fermés et absence d'espaces finaux. Les empreintes SHA-256 des 8 fichiers préexistants protégés sont identiques à celles relevées avant les écritures. Le frontmatter du skill est valide et les copies du dépôt et du profil actif sont identiques. `README.md`, auparavant vide, a été rempli volontairement. Aucun code de conduite ou d'entraînement n'a été exécuté. La validation de J0 ne signifie pas que les décisions ouvertes sont résolues.

## J1 — Faisabilité TMInterface sous Linux

Dépendance : J0, permissions et budget de GOAL complétés.

- [x] Versions et installation réelle recensées.
- [x] Observations demandées associées à des sources vérifiables, sauf écarts et `Progress`, marqués indisponibles jusqu'à J2.
- [x] Direction progressive, accélération et frein exercés réellement.
- [x] Temps de simulation, cadence et délais mesurés.
- [x] Checkpoints, arrivée et reset identifiés.
- [x] Synchronisation action/observation démontrée en mode synchrone ; le mode temps réel dérive.
- [x] Arrêt et déconnexion relâchent les commandes. Sortie de course et arrêt du jeu restent non testés.
- [x] Rapport `docs/reports/J1-integration.md` et traces conservés.

Sortie : contrat de pont réalisable. Si une donnée ou une capacité essentielle manque, demander une décision ; ne pas inventer un substitut.

Preuve de J1 : [rapport](reports/J1-integration.md), traces `runs/j1/20260929-134341` à `20260929-135642`, 7 tests hors jeu OK. Limites ouvertes : chargement automatique de la map, repères angulaires, vitesse de simulation supérieure à 1.

## J2 — Référence et observations

Dépendance : J1.

- [x] Une course humaine complète A01 enregistrée.
- [x] Référence brute et préparée conservées avec identité de map.
- [x] Projection par secteur et progression continue testées.
- [x] Écarts signés et conventions des repères validés.
- [x] Croisements, sauts, reculs, checkpoints et resets couverts par les tests.
- [x] Chaque champ demandé a un type, une unité, un ordre et une règle d'erreur.
- [x] Normalisation versionnée ; aucun ajout implicite aux observations du modèle.
- [x] Rapport `docs/reports/J2-observations.md` avec visualisations ou captures de données.

Sortie : observations numériques fiables, reproductibles et séparées de la logique d'apprentissage.

Preuve de J2 : [rapport](reports/J2-observations.md). Traces `runs/j2/20260929-142031-human` (2 courses valides, 27,11 s et 24,92 s) et `20260929-142538-conventions` ; artefacts `data/maps/a01/` avec hash dans `configs/maps/a01.json` ; 27 tests hors jeu OK. Croisements : A01 n'en a pas ; ce cas n'est couvert que par des tests synthétiques. Le schéma v1 et sa normalisation restent des propositions à approuver ; statistiques issues de 5 207 états humains réels.

## J3 — Environnement et récompense testables

Dépendance : J2.

- [x] Contrats de reset et de transition définis et testés.
- [x] Réussite, échec, troncature et erreur technique distingués.
- [x] Récompense décomposée et versionnée.
- [x] Tests anti-exploitation de REWARDS satisfaits.
- [x] Épisodes courts réels exécutés avec un contrôleur de test clairement identifié, sans prétendre qu'il est appris.
- [x] Données invalides exclues et inputs neutralisés après incident.
- [x] Rapport `docs/reports/J3-environnement.md` avec résultats unitaires et intégration réelle.

Sortie : environnement utilisable par un algorithme, sans dépendance excessive à une bibliothèque RL.

Preuve de J3 : [rapport](reports/J3-environnement.md) et fiche J3-ENV-01 de [EXPERIMENTS](EXPERIMENTS.md) §7. Traces `runs/j3/20260929-155217-env`, `-155315-env`, `-155330-env`, `-155711-env` : 2 arrivées confirmées par le jeu (30,12 s et 30,47 s, contrôleur scripté `reference_pursuit_v1`, non appris), 1 abandon, 1 troncature, 1 retard client et 1 déconnexion avec relâchement et reprise ; 51 tests hors jeu OK (24 J3, fixtures synthétiques). Limite bloquante pour J4 : après une arrivée, `GiveUp` ne relance pas la course (écran de fin), le pont 0.1.0 ne peut pas enchaîner les épisodes seul. Coefficients de récompense v1 et seuils du tracker (J2-09) restent des propositions.

## J4 — Premier apprentissage et boucle d'évaluation

Dépendance : J3, choix de l'algorithme, matériel et budget approuvés.

- [ ] Implémentation SAC (D15) et framework sélectionnés, compatibilité et traitement des commandes binaires comparé (D25) documentés.
- [ ] Mesure du débit (vitesse ×N, K instances) réalisée avant l'entraînement (D22), et budget chiffré approuvé en temps simulé et transitions (D23).
- [x] Compatibilité Python et backend vérifiée par exécution réelle. Preuve : rapport J4 §3 et §7.
- [x] Politique numérique et interface d'action fonctionnelles. Preuve : rapport J4 §3–6.
- [x] Un entraînement borné produit des transitions, métriques et checkpoints réels. Selon D37, l'agent le prouve par un court essai de fumée ; l'entraînement complet est lancé par l'utilisateur. Preuve : rapport J4 §5.
- [x] Sauvegarde, rechargement et reprise testés selon l'état nécessaire à l'algorithme. Preuve : rapport J4 §5.
- [x] Évaluateur distinct, politique figée et normalisation figée. Preuve : rapport J4 §6 bis, 20 tentatives par politique, SHA-256 avant/après inchangés. D28 complet reste limité par le chemin d’arrivée non validé.
- [x] Latence de décision mesurée en conditions temps réel. Preuve : rapport J4 §6.
- [x] Outillage utilisateur (D37) : commandes pour lancer, arrêter proprement, reprendre et évaluer un run à partir d'une configuration ; tableau de bord en direct (TensorBoard ou équivalent) ; données de diagnostic d'un run faciles à retrouver (configuration, versions, métriques, épisodes, incidents, checkpoints). Chaque commande est exécutée au moins une fois en essai de fumée. Preuve : rapport J4 §5, §6 bis et §9 (train, STOP, SIGINT, resume avec RNG, eval sync/temps réel/arrivée officielle, dashboard, compare ; checkpoints publiés atomiquement).
- [x] Guide utilisateur court (commandes, tableau de bord, emplacement des données, dépannage) référencé dans le rapport. Preuve : rapport J4 §2.
- [x] Fiche d'expérience complète ; aucune dépendance à Hermes dans la boucle de conduite. Preuve : rapport J4 §1–2.

Sortie : boucle de recherche opérationnelle et prise en main par l'utilisateur. Une perte d'apprentissage qui diminue n'est pas, seule, un progrès en course.

**État J4 : partiel, non clos**, voir [rapport](reports/J4-apprentissage.md) et [guide](GUIDE-J4.md). Cases ouvertes :

- D25 : framework exécuté, mais argmax4 n’est pas le bras SAC hybride demandé ; comparaison contrôlée absente.
- D22/D23 : mesure antérieure à l’entraînement conservée dans `runs/j4/20260929-170056-throughput/summary.json`. Budget de fumée dépassé avant l’amendement levant les plafonds ; ne pas cocher rétroactivement la conformité de l’ensemble du critère.
- Évaluateur : 20 tentatives par politique et gel vérifiés (rapport §6 bis). D28 complet reste limité par les conditions d’arrivée officielle non validées ; aucune arrivée dans ces essais.
- D25 (mise à jour §9) : bras SAC hybride catégoriel implémenté, testé hors jeu et exercé en jeu (2 600 transitions de fumée, reprise). Commande `compare` livrée. La comparaison contrôlée threshold/hybride, à budget et seeds égaux, reste à produire par les runs de l’utilisateur (D37) ; aucun gagnant désigné.
- D28 (mise à jour §9) : pont 0.4.0 installé ; arrivée non empêchée et écran de fin normal observés avec un contrôleur scripté non appris. L’enregistrement d’un chrono officiel ou d’un replay par le jeu n’est pas démontré. Aucune arrivée de politique apprise.
- D28 (mise à jour J4-15, 1er octobre) : politique hybride apprise figée évaluée sur 20 départs normaux à ×1 : 19 arrivées, meilleure 27,01 s, médiane 27,04 s, 1 incident technique invalidé. Une arrivée supplémentaire à 27,08 s en mode `--official-finish` ouvre l’écran normal de fin. Record personnel persistant et comparabilité à un classement non vérifiés ; voir [rapport J4-15](reports/J4-critic-corrections-20261001.md).
- D37 : case cochée après la reprise §9 (sauvegarde atomique, RNG restaurés, mode arrivée officielle exercé).

Preuves : `runs/j4/20260929-smoke-threshold/` (3 700 transitions), `runs/j4/20260929-smoke-argmax4/` (2 002), checkpoints et incidents de reprise. Aucun chrono appris valide. `runs/j4/20260929-smoke-hybrid4/` (2 600). Tests hors jeu : 69 OK après la reprise §9. Aucun passage à J5.

## J5 — Terminer A01 régulièrement

Dépendance : J4.

- [x] Critère de fiabilité et nombre d'évaluations fixés avant la campagne. Preuve : `runs/j5/protocol.json` (03:53:27, avant la première course à 03:53:35) ; D33, au moins 18/20.
- [x] Courses terminées depuis le départ normal avec checkpoints valides. Preuve : 39 arrivées `finished` (3/3 checkpoints) sur 40 pour `a01-v4-obs2b/00100000`.
- [x] Taux de réussite, meilleur temps et distribution des temps publiés. Preuve : rapport J5, avec 20/20 puis 19/20, meilleur 26,97 s et médiane 27,06 s.
- [x] Échecs conservés dans les statistiques. Preuve : erreur technique 540001, 14 échecs de A et 1 abandon de C au dénominateur.
- [x] Au moins une comparaison contrôlée documentée pour justifier les améliorations retenues. Preuve : trois checkpoints figés, même protocole ; A 6/20, B 20/20, C 19/20. Comparaison d'évaluation, pas d'ablation à facteur unique.
- [x] Résultat confirmé avec le checkpoint sauvegardé. Preuve : seconde campagne rechargée depuis le disque, 19/20, SHA-256 identiques avant et après.

Sortie : pilote appris qui termine la map selon le protocole approuvé. Seuil retenu : D33.

**État J5 : validé le 2 octobre 2026** sur demande explicite de l'utilisateur, alors que J4 reste partiel (D25 et D22/D23 toujours ouverts). Voir le [rapport J5](reports/J5-fiabilite.md). Chronos du jeu non vérifiés comme records officiels ; aucun rang annoncé.

## J6 — Chrono comparable au top 1 000

Dépendance : J5 et référence de classement renseignée.

- [x] Source, date, catégorie, map exacte et seuil documentés. Preuve : `runs/j6/survey/leaderboard_summary.json` (TMX, 2026-10-02 13:32:59 +09:00, piste 2233, UID `BeySZdnfuSh4nHY5xztiXLmlrXe`) : rang 1 000 = 24,23 s, à égalité avec le rang 1 001, donc seuil strict < 24,23 s ; rang 50 = 23,93 s.
- [ ] Conditions physiques et départ comparables.
- [ ] Meilleur chrono valide sous le seuil, accompagné de la fiabilité exigée.
- [ ] Preuves, configuration et modèle conservés.
- [ ] Comparaison confirmée par une évaluation séparée de l'entraînement.

Sortie : performance locale documentée, sans prétendre à une inscription officielle.

**État J6 au 2 octobre 2026 : partiel.** Seuil relevé ; meilleur pilote figé à 26,97 s, soit 2,7 s au-dessus. Run `j6-v6-lap-B` interrompu à 525 k transitions par un redémarrage, sans gain (26,98 s). Voir le [rapport J6](reports/J6-chrono.md).

## J7 — Recherche vers le top 50 et au-delà

Dépendance : J6, nouveaux budgets approuvés.

- [ ] Seuil top 50 daté et protocole de confirmation définis.
- [ ] Facteurs limitants identifiés à partir des traces, pas seulement du score.
- [ ] Expériences comparables et ablations documentées.
- [ ] Extensions du modèle ou des observations soumises à décision avant adoption.
- [ ] Meilleure configuration validée sur des courses complètes répétées.
- [ ] Objectif atteint avec preuves, ou état de recherche rapporté honnêtement sans promesse de réussite.

Pistes conditionnelles : réglages de l'algorithme, historique, récurrence (D18 : première ablation si plateau). Exclues par décision : imitation (D19), départs intermédiaires, entraînement par secteurs et maps modifiées (D24) ; les réintroduire exige une nouvelle décision. Un entraînement par secteurs ne remplace pas une évaluation depuis le départ normal.

## J8 — Réutilisation sur une seconde map

Dépendance : pipeline J4 stable au minimum. Ce jalon peut être intercalé avant J7 si l'utilisateur privilégie la réutilisabilité.

- [ ] Seconde map choisie et référence enregistrée.
- [ ] Nouveau profil de map sans duplication de l'environnement générique.
- [ ] Spécialiste distinct entraîné et évalué.
- [ ] Hypothèses spécifiques à A01 détectées et retirées des composants génériques.
- [ ] Procédure de préparation d'une nouvelle map documentée et reproduite.

Sortie : preuve de réutilisation sur une autre map, pas une garantie de prise en charge universelle.

## Règle de clôture

Pour chaque jalon, conserver : résultat, commande de vérification, artefacts, mesures, limites, budget consommé et décision de poursuite. Si une vérification ne peut pas être effectuée, laisser la case ouverte et expliquer le blocage.
