# Expériences, évaluation et preuves

## 1. Séparer trois activités

- **Test unitaire** : vérifier un calcul, un protocole ou une règle sur des données contrôlées.
- **Test d'intégration réel** : vérifier le jeu, TMInterface et le contrôleur ensemble.
- **Expérience RL** : mesurer l'effet d'une hypothèse sur un modèle entraîné.

Ne jamais présenter la réussite de l'une comme une preuve suffisante pour les deux autres.

## 2. Métadonnées minimales

Chaque expérience aura un identifiant unique et un répertoire d'artefacts propre. Le mécanisme exact sera implémenté plus tard.

Conserver :

- Question de recherche et différence avec l'expérience de référence.
- Identité et empreinte de la map, de la ligne de référence et des profils utilisés.
- Versions du jeu, de TMInterface, du plugin et des dépendances Python.
- Révision du code et état des modifications non commitées ; ne pas exiger un commit non autorisé.
- Machine, CPU, RAM, GPU exact et backend réellement utilisé.
- Schémas de transport, observations, actions et récompense.
- Cadence de décision, durée des actions, conditions de simulation et latences mesurées.
- Algorithme, hyperparamètres, seeds et politique d'exploration.
- Budget prévu et consommation réelle : temps mural, temps simulé, transitions, épisodes et espace disque.
- Raisons d'arrêt, incidents, pertes de connexion et transitions rejetées.
- Modèle, état de l'optimiseur, statistiques de normalisation et autres états nécessaires à la reprise selon l'algorithme.
- Résultats d'évaluation avec tous les échecs, pas seulement les meilleurs essais.

Ne pas enregistrer de secrets, jetons ou informations de compte dans les artefacts.

## 3. Protocole d'évaluation

Définir le protocole avant la comparaison :

1. Charger une politique figée et la normalisation associée.
2. Fixer la méthode de sélection des actions pour l'évaluation.
3. Partir du départ normal de la map, avec des conditions physiques comparables.
4. Exécuter des courses complètes ; ne pas confondre un départ intermédiaire d'entraînement avec une course valide.
5. Vérifier les checkpoints et l'arrivée via le jeu.
6. Mesurer le temps du jeu et les contraintes temps réel de la politique.
7. Enregistrer chaque tentative et sa raison de fin.
8. Rapporter meilleur temps valide, médiane et dispersion des temps valides, taux de réussite et nombre d'essais.

Le nombre d'essais et la fiabilité cible sont à compléter dans GOAL. Une évaluation déterministe répétée ne remplace pas plusieurs seeds d'entraînement lorsqu'on compare la robustesse d'un algorithme.

Pour attribuer un progrès à une modification, comparer des budgets de collecte cohérents et changer un facteur principal à la fois. Si plusieurs facteurs changent, le signaler au lieu de conclure sur leur cause individuelle.

## 4. Comparaison avec les classements

Avant une revendication top 1 000 ou top 50, conserver : source du classement, date du relevé, catégorie, identité exacte de map, seuil, règles, chronos locaux et preuves de validité.

Formulation autorisée avec preuves : « chrono local inférieur au seuil de référence relevé pour cette catégorie ». Ne pas annoncer une inscription ou un rang officiel sans validation officielle distincte.

Les réglages qui changent la physique, un état initial avantageux ou un chrono non comparable doivent exclure l'essai de cette comparaison. Ils peuvent rester des outils d'entraînement explicitement marqués.

## 5. Fiche à compléter

```text
Expérience :
Statut : préparée / en cours / terminée / interrompue / invalide
Hypothèse :
Expérience de référence :
Facteur principal modifié :
Map et référence :
Machine et backend :
Versions et état du code :
Schéma d'observation :
Schéma d'action et cadence :
Récompense et horizon :
Algorithme et paramètres :
Seeds :
Budget approuvé :
Conditions d'arrêt :
Commande réellement exécutée :
Chemins des logs et checkpoints :
Résultats d'entraînement :
Protocole et nombre d'évaluations :
Meilleur chrono valide :
Médiane et dispersion :
Réussites / tentatives :
Latence et pas manqués :
Incidents et données invalidées :
Comparaison avec la référence :
Conclusion et incertitudes :
Décision : conserver / rejeter / approfondir
Expérience suivante proposée :
```

## 6. Conservation et reprise

Avant de produire de gros volumes, décider quels artefacts conserver, leur quota, leur emplacement et leur sauvegarde. Préserver au moins la configuration, les métriques, les versions et les preuves associées à un modèle retenu.

La reprise doit être testée : charger un checkpoint ne prouve pas la restauration correcte de l'optimiseur, du replay buffer éventuel, de la normalisation ou des compteurs. Lister les éléments restaurés et ceux qui ne le sont pas.

Un entraînement qui continue hors session exige une autorisation et une supervision propres. Prévoir arrêt propre, quota et récupération après incident ; ne pas compter sur le seul texte d'un `/goal`.

Runs lancés par l'utilisateur (D37) : chaque run écrit seul, sans Hermes, sa configuration, ses versions, ses métriques, ses épisodes, ses incidents et ses checkpoints dans `runs/<id>/`. Ces données suffisent à remplir la fiche §5 plus tard. La fiche d'un run de l'utilisateur est complétée lors de la mission d'analyse suivante, à partir de ces fichiers. Elle n'est jamais complétée de mémoire.

## 7. Fiches

### J4-SMOKE-01 — Chaîne SAC CPU et outillage

- **Statut** : essais de fumée terminés ; jalon J4 partiel. Ce n’est pas une comparaison de performance contrôlée.
- **Hypothèse** : la chaîne réelle peut collecter, apprendre, sauvegarder, reprendre et évaluer sans Hermes dans la conduite.
- **Référence et facteur modifié** : environnement J3 ; introduction de SAC. Deux codecs explorés avec budgets différents, donc aucun effet causal attribué au codec.
- **Map et référence** : A01 UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, profil `configs/maps/a01.json`, référence et normalisation v1 inchangées. Hashes dans les versions de run.
- **Machine et backend** : laptop Linux local, CPU, quatre threads. Python 3.13.9, PyTorch 2.14.0+cpu, SB3 2.9.0, Gymnasium 1.3.0. Pont 0.3.0 ; installation jeu héritée de J3. Empreintes du code dans `versions.json` et `versions_resume_*.json`, pas de commit créé.
- **Observation et action** : D31, 25 valeurs ; 50 ms simulées par action ; threshold à 3 sorties ou argmax4 à 5 sorties. Argmax4 n’est pas un SAC hybride catégoriel.
- **Récompense et horizon** : proposition J3-02 (100, 1/s, 150, 0,98/s, potentiel terminal nul) ; limite 54 220 ms, abandon après 5 000 ms sans progression.
- **Algorithme, paramètres, seed** : SAC, [256,256], LR 0,0003, buffer 100 000, batch 256, learning_starts 2 000, tau 0,005, entropie auto, seed 1. Configuration exacte enregistrée dans chaque run.
- **Budget et consommation** : proposition initiale de 4 000 transitions de fumée dépassée ; 5 702 exécutées (285,1 s simulées). Plafonds J4 levés ensuite par amendement utilisateur dans GOAL.md. Les durées murales d’entraînement sont dans `status.json` ; elles ne couvrent pas toute la mission. Pas de mesure exhaustive consolidée du temps de jeu sous contrôle.
- **Conditions et raisons d’arrêt** : budget de run, STOP, SIGINT. Zéro transition invalide déclaré dans les deux statuts finaux. Reprise depuis le départ normal, pas de restauration RNG ni de l’épisode partiel.
- **Commandes exécutées** : `tm.py train --budget 2200`, reprises threshold jusqu’à 3 700 ; `tm.py train --budget 1500`, reprises argmax4 et SIGINT à 2 002. Préfixe `uv run python scripts/` ; configurations, commandes complètes et versions dans les artefacts. `tm.py status` et `j4_dashboard_smoke.py --port 6008` réexécutés avec code 0 à la consolidation.
- **Logs et checkpoints** : `runs/j4/20260929-smoke-threshold/` et `runs/j4/20260929-smoke-argmax4/` ; checkpoints finaux `00003700` et `00002002`. `episodes.jsonl`, `transitions.jsonl`, `incidents.jsonl`, `sb3/` conservés. Reprise réelle attestée par les incidents et tailles de replay buffer.
- **Résultats d’entraînement** : 3 700 et 2 002 transitions ; aucune arrivée. Les pertes threshold sont visibles dans TensorBoard ; argmax4 dépasse à peine le seuil d’apprentissage.
- **Protocole et nombre d’évaluations** : politique déterministe figée, normalisation vérifiée ; threshold 3 épisodes synchrones et 2 temps réel au checkpoint 3 200 ; argmax4 1 épisode synchrone au checkpoint 2 002. **D28 non validé** : pas de série de 20 et arrivée officielle empêchée par le pont.
- **Chronos et réussite** : aucun chrono valide, médiane et dispersion non définies ; 0/3, 0/2 et 0/1 arrivées, échecs conservés au dénominateur.
- **Latence** : threshold temps réel, médiane des médianes de décision 1,023 ms, maximum 2,026 ms ; 3 frontières tardives. Résumés et transitions dans les dossiers `evals/` cités au rapport.
- **Comparaison et conclusion** : chaîne technique démontrée partiellement ; aucun progrès en course, aucune conclusion sur le meilleur codec. Le débit ×10 de 200,016 transitions/s provient d’un contrôleur scripté sans gradients, pas de SAC.
- **Décision proposée** : conserver l’outillage pour poursuivre J4, pas clore le jalon. Traiter D25 avec un vrai bras hybride ou une décision explicite ; compléter D28. Pas de J5.
- **Preuves et transmission** : [rapport J4](reports/J4-apprentissage.md), [guide](GUIDE-J4.md). Suite hors jeu : 63 tests OK, 4,205 s lors de la consolidation.


### J4-EVAL-20 — Complément sans apprentissage

Statut : évaluations terminées, J4 toujours partiel. Autorisation interactive explicite de l’utilisateur. Même map, normalisation, récompense et versions que J4-SMOKE-01 ; checkpoints threshold 3 200 et argmax4 2 002, politique déterministe, temps réel à ×1. Commandes complètes et chemins : [rapport J4 §6 bis](reports/J4-apprentissage.md).

20 tentatives par politique depuis le départ normal, tous les échecs conservés : **0/20 arrivées chacune**, 20 abandons chacune. Pas de chrono d’arrivée, médiane et dispersion non définies. Threshold : 1 992 transitions d’évaluation, zéro invalide, 39 frontières tardives ; argmax4 : 5 531, zéro invalide, 132 tardives. Médiane des médianes de décision : 1,207 ms et 0,844 ms ; maxima 3,715 ms et 11,596 ms. Les tentatives temps réel ne sont pas toutes identiques.

Les fichiers modèle et normalisation sont inchangés avant/après ; vérification des comptes depuis les JSONL dans `runs/j4/eval20-verification.json`. Temps simulé d’évaluation : 100 230 ms et 278 170 ms. Aucun entraînement supplémentaire. Retour à vitesse ×1 vérifié après les essais. Arrêt : règles d’abandon puis nombre d’essais atteint. Aucun résultat comparé à un classement.

Conclusion : nombre d’essais D28 et gel désormais prouvés, sans arrivée officielle testée. D25 reste ouvert et ces budgets d’apprentissage inégaux ne permettent aucune conclusion causale sur les codecs. Proposition : conserver les artefacts, traiter le bras hybride et la validation d’arrivée ; aucune campagne J5.

### J4-RESUME-01 — Bras hybride, sauvegarde et arrivée officielle

Statut : essais de fumée terminés ; J4 partiel. Autorisation de session de l’utilisateur (essais réels courts). Hypothèses : (1) le SAC hybride `hybrid4_v1` collecte, apprend, sauvegarde et reprend dans le vrai jeu ; (2) le pont 0.4.0 laisse le jeu terminer normalement une course contrôlée. Facteur modifié : codec d’action (hybride) et mode d’arrivée. Map, normalisation v1, récompense v1 (proposition J3-02), réseaux 2×256 identiques à J4-SMOKE-01 ; seed 1 ; ×10 à l’entraînement, ×1 temps réel à l’évaluation.

Résultats : run `runs/j4/20260929-smoke-hybrid4/`, 2 600 transitions (2 300 + reprise), zéro invalide, 2 épisodes sans arrivée. Évaluation figée 20 tentatives, mode officiel : 0/20 arrivées (13 limites, 6 abandons, 1 erreur de retard temps réel), hashes inchangés. Sonde scriptée non apprise : arrivée 30 580 ms et écran de fin normal, aucun autosave observé.

Conclusion : hypothèses (1) et (2) vérifiées au niveau outillage. Aucune conclusion de performance ni de choix D25 : budgets de fumée, un seed, collecte presque entièrement aléatoire. Détails : [rapport J4 §9](reports/J4-apprentissage.md). Suite proposée : runs utilisateur D25 à seeds multiples.

### J3-ENV-01 — Intégration réelle de l'environnement et de la récompense v1

Cette fiche décrit un **test d'intégration réel** (§1), pas une expérience RL : aucun modèle, aucun apprentissage.

```text
Expérience : J3-ENV-01
Statut : terminée
Hypothèse : l'environnement trackmania_rl.env/1 produit, dans le vrai jeu en mode synchrone,
  des transitions valides chaînées et distingue arrivée, abandon, troncature et erreur ;
  la récompense v1 classe arrivée rapide > arrivée lente > abandon, sans gain de progression
  sur épisode terminé.
Expérience de référence : aucune (première intégration de l'environnement).
Facteur principal modifié : sans objet.
Map et référence : A01-Race, UID BeySZdnfuSh4nHY5xztiXLmlrXe, fichier f0a87080…25dc3 ;
  référence préparée 940143ce…702e ; normalisation v1 348e9de2…1ed9 (configs/maps/a01.json).
Machine et backend : laptop local, Ryzen AI 7 350, 30 Gio ; CPU, aucun backend RL.
Versions et état du code : TmForever 2.12.0, TMInterface 2.2.1, CoreMod 1.0.11, pont 0.1.0
  (b821d44a…) ; Python 3.13.9, uv 0.9.5, bibliothèque standard. Dépôt sans commit (tous
  fichiers non suivis) ; empreintes : env.py 7c784f05…, reward.py 89700291…,
  scripted_controllers.py 7edb12d6…, j3_live_env.py bf729518…, a01.json 9df10414….
Schéma d'observation : trackmania_rl.observation/1 (25 valeurs, D31).
Schéma d'action et cadence : direction [−1, 1] → ±65536, accélération et frein binaires ;
  5 ticks = 50 ms simulées (D26), mode synchrone (D20), délai d'action du plugin 1 000 ms.
Récompense et horizon : trackmania_rl.reward/1 (hash 7db1d3d8…88f3) : Φ = 100·Progress,
  Φ(terminal) = 0, coût 1,0/s, bonus 150, γ = 0,98 par seconde. Limite 54 220 ms (troncature),
  abandon après 5 000 ms sans progrès (terminal), D27. Coefficients : PROPOSITION.
Algorithme et paramètres : aucun. Contrôleurs de test scriptés NON APPRIS :
  reference_pursuit_v1 (poursuite de la référence, avance 12 m + 0,35 s·v, gain 2,5, plein gaz),
  idle_v1, full_gas_straight_v1.
Seeds : sans objet (contrôleurs déterministes ; le jeu n'a pas été reseedé).
Budget approuvé : mission 2 h, jeu 30 min, traces 500 Mio (GOAL, contrat J3).
Conditions d'arrêt : fin de scénario, erreur de pont, budget.
Commande réellement exécutée : voir docs/reports/J3-environnement.md §2.
Chemins des logs et checkpoints : runs/j3/20260929-155217-env, -155315-env, -155330-env,
  -155711-env, -reset-probe, 20260929-160244-reward-sensitivity.json. Aucun checkpoint de modèle.
Résultats d'entraînement : aucun (pas d'entraînement).
Protocole et nombre d'évaluations : sans objet. Épisodes : 2 pursuit (arrivée), 1 idle, 1 troncature
  (limite de test 3 s), 1 retard client, 1 déconnexion, 2 reprises.
Meilleur chrono valide : 30,12 s, contrôleur scripté. Ce n'est PAS une performance d'agent.
Médiane et dispersion : sans objet (2 arrivées d'un contrôleur de test).
Réussites / tentatives : 2 arrivées sur 2 épisodes pursuit.
Latence et pas manqués : action → état suivant, médiane 49,2 à 49,5 ms, p95 ≤ 55,4 ms,
  maximum 64,9 ms ; 0 pas manqué ; Δtick = 50 ms sur toutes les transitions boundary.
Incidents et données invalidées : 1 transition invalide volontaire (retard client,
  released/action_timeout) ; reset impossible après arrivée (écran de fin, J3-03), relance
  manuelle par l'utilisateur ; lancement 155254 refusé par le script avant tout envoi.
Comparaison avec la référence : sans objet.
Conclusion et incertitudes : contrat de transition et statuts vérifiés en jeu ; retour de
  progression actualisé = 0 sur les épisodes terminés ; ordre des retours 59,08 > 58,31 > −4,89.
  Incertitudes : seuils du tracker jamais déclenchés (J2-09) ; limite de 54,22 s non atteinte
  en jeu ; coefficients non comparés en apprentissage ; A01 sans croisement.
Décision : conserver l'environnement ; coefficients et traitement terminal à approuver ;
  reset après arrivée à trancher (J3-03).
Expérience suivante proposée : hors J3. Après décision J3-03, vérifier l'enchaînement automatique
  de plusieurs arrivées avant toute mesure de débit (D22).
```

## J4-15 — Reprise et contexte d'abandon, 1er octobre 2026

Statut : corrections approuvées et testées hors jeu, efficacité en jeu ouverte. Source réelle : v3 `00660037`. Migration 25 vers 27 entrées ; sorties initiales de l'acteur et des critiques inchangées sur 1 024 observations, températures conservées. Replay et optimiseurs neufs. 130 tests hors jeu passent, dont 11 nouveaux tests avec environnement synthétique. Aucun contrôle de TMNF ni entraînement réel dans cette expérience. Configuration suivante : `a01_sac_hybrid4_v4_obs2.json`, première fenêtre utilisateur de 100 000 transitions. Sources, seeds, versions, résultats des audits et limites : [rapport J4-15](reports/J4-critic-corrections-20261001.md). Aucun critère de performance coché.

Complément terrain J4-15 : le run utilisateur `a01-v4-obs2b` termine 100 000 transitions avec 137/163 arrivées, 0 transition invalide et 50/50 arrivées sur les derniers épisodes. Erreur du critique en baisse sur les sondes fixes ; abandon difficile encore présent (TD max 18 sur le replay final). Évaluation figée à ×1 et stabilité plus longue ouvertes. Détails et preuves : [rapport J4-15](reports/J4-critic-corrections-20261001.md).

Évaluation utilisateur J4-15 du checkpoint v4 `00100000` : 20 départs normaux, politique figée, temps réel ×1, 19 arrivées, meilleure 27,01 s, médiane 27,04 s. Un incident technique de tick 110 ms invalidé ; 80 frontières tardives sur 10 273 transitions. Écran/record officiel non vérifié. Artefacts et limites : [complément d'évaluation J4-15](reports/J4-critic-corrections-20261001.md).

Essai officiel J4-15 : une arrivée de la politique apprise à 27,08 s, politique figée, ×1, 541 actions valides ; écran normal de fin confirmé par TMInterface 0.4.2. Enregistrement du record personnel dans le jeu encore à vérifier. Artefacts et limite D28 : [rapport J4-15](reports/J4-critic-corrections-20261001.md).

## J5-EVAL-01 — Fiabilité sur A01, 2 octobre 2026

Statut : terminée. Hypothèse : au moins une politique figée existante respecte D33 (au moins 18/20) à ×1 depuis le départ normal. Protocole et candidats préenregistrés dans `runs/j5/protocol.json`. Trois checkpoints figés ont été évalués, avec 20 tentatives chacun et pont 0.4.2 : v3 `00660037` donne 6/20, médiane 28,44 s ; v4 `00100000` donne 20/20, meilleur 26,98 s et médiane 27,05 s ; v4 `best-027110ms-02432296` donne 19/20, meilleur 26,26 s et médiane 28,96 s. Décision : conserver v4 `00100000`, selon la règle de la médiane la plus basse parmi les candidats conformes. La confirmation rechargée donne 19/20, meilleur 26,97 s et médiane 27,07 s ; 1 erreur technique de tick 150 ms est comptée. Les SHA-256 sont identiques avant et après. Comparaison entre checkpoints, multifacteur entre A et B : aucune cause isolée. Chronos du jeu non comparables à un classement. Artefacts et limites : [rapport J5](reports/J5-fiabilite.md).
