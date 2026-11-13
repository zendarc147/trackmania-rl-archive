# Rapport J4 — Premier apprentissage et boucle d’évaluation

Date : 29 septembre 2026. **Statut : partiel, non clos.** Reprise et compléments : §9. Uniquement A01 et J4. Aucune campagne J5.

## 1. Résultat et limites de validation

La chaîne SAC CPU produit des transitions, des métriques et des checkpoints réels. Arrêt, rechargement, reprise et évaluations courtes ont été exercés. Le tableau de bord a été interrogé par HTTP. La boucle de conduite ne dépend pas de Hermes.

Deux exigences restent non satisfaites :

- **D25** : `argmax4_v1` est une relaxation continue, pas une action hybride à tête catégorielle. Les budgets de fumée diffèrent et ne permettent pas une comparaison d’apprentissage contrôlée. Aucun gagnant n’est désigné. Il faut implémenter et tester le vrai bras hybride, ou obtenir une décision explicite modifiant D25 ; ne pas assimiler silencieusement argmax4 à ce bras.
- **D28** : les premières fumées comprenaient 3, 2 et 1 épisodes ; le complément §6 bis comporte désormais 20 tentatives par politique figée. Le pont empêche la validation officielle de l’arrivée pour permettre les resets (J3-03). L’évaluateur est figé, mais le protocole complet n’est pas validé. Le checkpoint threshold 3 700 n’a pas été évalué : les évaluations threshold concernent 3 200.

Aucune arrivée de politique apprise dans ces fumées. Aucun chrono valide, aucune médiane ou dispersion des temps d’arrivée, aucune preuve de progrès en course. Une courbe de perte n’en constitue pas une.

## 2. Livrables

- `src/trackmania_rl/actions.py` : direction continue, codecs threshold et argmax4.
- `runtime.py` : assemblage générique du profil de map, de la référence et des observations.
- `gym_env.py` : adaptateur Gymnasium, distinction fin/troncature et invalidation technique.
- `training.py` : SAC filtrant les transitions invalides, métriques, checkpoints, arrêt et reprise.
- `evaluation.py` : politique déterministe séparée de l’apprentissage, hash de normalisation contrôlé.
- `scripts/tm.py` : train, status, stop, resume, eval, dashboard.
- `configs/training/a01_sac_{threshold,argmax4,hybrid4}_v1.json` : propositions bornées, seed 1.
- `hybrid_sac.py` (bras SAC hybride D25) et `compare.py` (comparaison à budget commun), ajoutés et documentés en §9.
- `scripts/j4_throughput.py`, `j4_eval_timing.py`, `j4_sigint_smoke.py`, `j4_dashboard_smoke.py`, `j4_speed_restore_probe.py`, `j4_sac_update_bench.py` : sondes et diagnostics.
- [Guide utilisateur](../GUIDE-J4.md), [fiche d’expérience](../EXPERIMENTS.md), [critères](../ROADMAP.md).

## 3. Choix proposés, versions et observations

**Proposition J4-01** : Stable-Baselines3 SAC sur PyTorch CPU. Justification locale : intégration effectivement exécutée sous Python 3.13, sérialisation des états SAC et replay buffer, compatibilité avec l’adaptateur Gymnasium. Éviter de réimplémenter l’optimisation SAC pour cette première intégration. L’autorisation d’installer ce framework n’est pas une validation scientifique de tous ses choix.

Versions réelles dans `runs/j4/20260929-smoke-threshold/versions.json` : Python 3.13.9, PyTorch 2.14.0+cpu, SB3 2.9.0, Gymnasium 1.3.0, NumPy 2.5.3, CUDA indisponible, 4 threads. Installation via uv et index PyTorch CPU explicite ; `uv.lock` conservé. Les tests chargent et entraînent réellement SAC sur fixtures synthétiques ; ce ne sont pas des preuves de performance dans TrackMania.

Observations D31 inchangées : 25 valeurs, normalisation v1 figée, hash `348e9de2076a9071c028aa04f7b6c26ded90503458430b5b91764978cd401ed9`. UID A01 `BeySZdnfuSh4nHY5xztiXLmlrXe`. Les identités de map et référence sont conservées dans `configs/maps/a01.json` et les versions de run.

**Proposition J4-02** : comparer les codecs disponibles comme diagnostic préparatoire, sans prétendre satisfaire D25 : threshold = 3 sorties, gaz et frein seuillés à zéro ; argmax4 = direction et 4 scores continus pour les couples gaz/frein. Pas de lissage supplémentaire. Les deux utilisent des actions latentes continues ; argmax4 n’a pas de distribution catégorielle apprise séparément.

Réseaux [256,256], LR 0,0003, buffer 100 000, batch 256, learning_starts 2 000, tau 0,005, une mise à jour par transition, entropie auto. Récompense v1 : potentiel 100·Progress, coût 1/s, bonus 150, discount 0,98/s, potentiel terminal nul. Coefficients et seuils de projection restent des propositions J3-02 et J2-09. Aucun ajout d’observation ni imitation.

## 4. Débit et pont

Preuve : `runs/j4/20260929-170056-throughput/summary.json`, commande `uv run python scripts/j4_throughput.py --map configs/maps/a01.json --speeds 1 2 4 6 10`.

Contrôleur scripté `reference_pursuit_v1`, explicitement non appris : 610 transitions par course, 30 470 ms au terme. Identité bit à bit des états comparés à ×1 pour ×2, ×4, ×6 et ×10. Débit ×10 : 200,016 transitions/s murales, hors gradients SAC. Une trajectoire identique ne démontre pas l’identité de toute physique pour tous les contrôleurs.

Pont 0.3.0 : commande SPD et restauration de vitesse après perte du client. Sauvegardes : `runs/j4/backup/`. Sonde réelle `runs/j4/logs/speed-restore-probe.json` : vitesse 1 avant, 4 demandée, 1 après reconnexion, `restored=true`. Cette preuve ne couvre pas tous les scénarios de crash ou désactivation.

## 5. Entraînement, arrêt et reprise réels

`runs/j4/20260929-smoke-threshold/` :

- 2 200 transitions initiales ; reprise jusqu’à 2 860 puis STOP ; reprise jusqu’à 3 200 ; dernière reprise jusqu’à 3 700.
- `incidents.jsonl` conserve les événements `resume`, les tailles de buffer et l’arrêt `stop_file`.
- `status.json` : `finished_budget`, 3 700 transitions, zéro transition invalide déclarée.
- Checkpoint final `checkpoints/00003700/` : modèle, état entraîneur et replay buffer de 3 700 transitions.
- `sb3/progress_20260929-174111.csv` contient les pertes acteur/critique et coefficient d’entropie.

`runs/j4/20260929-smoke-argmax4/` :

- 1 500 transitions initiales, reprise 1 800, puis arrêt SIGINT à 2 002 (objectif de cet essai : 2 300).
- `incidents.jsonl` : raison finale `sigint`, reprises et tailles de buffer.
- Checkpoint `checkpoints/00002002/` ; zéro transition invalide déclarée.
- Le seuil d’apprentissage étant 2 000, ce run ne représente quasiment que la collecte initiale ; il ne permet pas de comparer les codecs.

Total d’apprentissage de fumée : **5 702 transitions**, soit 285,1 s simulées à 50 ms. Cela dépassait la proposition initiale de 4 000. L’utilisateur a ensuite levé les plafonds J4 dans GOAL.md ; l’historique du dépassement reste conservé, sans autorisation rétroactive. Les futurs runs de 69 000 transitions restent des propositions bornées, pas des plafonds globaux imposés.

La reprise recharge poids acteur/critique, critiques cibles, optimiseurs, coefficient d’entropie, replay buffer et compteurs. Limites explicites dans `trainer_state.json` : pas de restauration des RNG ni de l’épisode interrompu. Les anciens replay buffers ont été supprimés lors du nettoyage approuvé en session ; les anciens modèles restent présents. Le code ne garde que le dernier buffer. La sauvegarde complète n’est pas atomique face à une interruption pendant ses écritures. *(Constats corrigés en §9 : chaque checkpoint garde son buffer, publication atomique, RNG restaurés.)*

## 6. Évaluations et latence

Artefacts relatifs à `runs/j4/` :

- `20260929-smoke-threshold/evals/20260929-171820-00003200-sync-x1/` : 3 épisodes, 3 abandons, aucune arrivée ; résumés identiques selon statut, temps et nombre de transitions.
- `20260929-smoke-threshold/evals/20260929-172753-00003200-realtime-x1/` : 2 épisodes, 2 abandons, aucune arrivée ; médiane des médianes de décision 1,023 ms, maximum 2,026 ms, 3 frontières tardives. Ce n’est pas une preuve d’absence de retard.
- `20260929-smoke-argmax4/evals/20260929-172944-00002002-sync-x1/` : 1 épisode, abandon, aucune arrivée.

Chaque dossier conserve `eval_summary.json`, `eval_episodes.jsonl` et `eval_transitions.jsonl`. Politique chargée depuis `model.zip`, mode déterministe, pas de mise à jour ni replay buffer d’apprentissage, hash de normalisation vérifié. `comparable_to_leaderboard=false` dans tous les résumés.

## 6 bis. Complément réel — 20 tentatives par politique

Autorisation explicite de l’utilisateur : « Oui, A01 prête, lancer les évaluations ». Aucun apprentissage, politique déterministe, vitesse ×1, mode temps réel, départ normal et règles terminales inchangées.

Commandes exécutées avec code 0 :

```bash
uv run python scripts/tm.py eval --run runs/j4/20260929-smoke-threshold --checkpoint 00003200 --episodes 20 --mode realtime --speed 1 --first-episode 910001
uv run python scripts/tm.py eval --run runs/j4/20260929-smoke-argmax4 --checkpoint 00002002 --episodes 20 --mode realtime --speed 1 --first-episode 920001
```

- Threshold : `runs/j4/20260929-smoke-threshold/evals/20260929-182053-00003200-realtime-x1/`. 20 abandons, zéro arrivée, 1 992 transitions d’évaluation, aucune invalide. Décision : médiane des médianes 1,207 ms, maximum 3,715 ms. 39 frontières tardives, durée maximale de transition 100 ms.
- Argmax4 : `runs/j4/20260929-smoke-argmax4/evals/20260929-182253-00002002-realtime-x1/`. 20 abandons, zéro arrivée, 5 531 transitions d’évaluation, aucune invalide. Décision : médiane des médianes 0,844 ms, maximum 11,596 ms. 132 frontières tardives, durée maximale de transition 100 ms.
- Tous les échecs sont conservés : réussite 0/20 pour chaque politique ; meilleur temps, médiane et dispersion d’arrivée non définis. Les tentatives ne sont pas toutes identiques en temps réel.
- Les deux fichiers `model.zip` et la normalisation ont des SHA-256 identiques avant/après : `runs/j4/eval20-frozen-before.json` et `runs/j4/eval20-verification.json`. Les nombres d’épisodes et transitions sont vérifiés depuis les JSONL, pas seulement depuis les résumés.
- Après évaluation : hello du pont 0.3.0, A01 en course, vitesse revenue à 1 ; client fermé avec relâchement demandé. Aucun poids mis à jour et aucune transition ajoutée aux runs d’entraînement.

Le nombre d’essais et le gel D28 sont désormais exercés. La validation d’une arrivée officielle reste inaccessible avec le mode contrôlé actuel du pont ; ces essais n’atteignent aucune arrivée et ne prouvent donc pas ce chemin. Ce complément ne valide pas D25, ni un progrès d’apprentissage : budgets des deux modèles différents et collecte argmax4 presque entièrement antérieure au seuil d’apprentissage.

## 7. Vérifications hors jeu et tableau de bord

Dernière exécution de consolidation :

```text
PYTHONPATH=src:tests uv run python -m unittest discover -s tests
Ran 63 tests in 4.205s
OK
```

`uv run python scripts/j4_dashboard_smoke.py --port 6008` : code 0, API HTTP répond, deux runs exposés. Courbes threshold : retours, progression, commandes, latence, pertes acteur/critique et entropie. Le run argmax4 ne dispose pas de courbes de pertes dans la preuve actuelle. `uv run python scripts/tm.py status` : threshold 3 700, argmax4 2 002, aucun run déclaré actif.

Corrections effectuées pendant J4 : exclusion du callback de la sérialisation ; CSV distinct par reprise ; filtration des transitions invalides ; acceptation bornée des retards uniquement en mode temps réel ; calcul du débit de fenêtre initialisé au compteur de reprise. L’ancienne valeur 601,823 transitions/s enregistrée dans le CSV de reprise threshold est incorrecte : elle inclut les transitions antérieures au redémarrage dans le numérateur. Ne pas l’utiliser comme mesure SAC. Le correctif est testé hors jeu, non remesuré dans le jeu.

## 8. Transmission et blocages

Utiliser le [guide](../GUIDE-J4.md) pour lancer, suivre, arrêter, reprendre et évaluer. Les commandes d’outillage ont des preuves de fumée ; cela ne valide pas D25 ni D28.

J4 reste ouvert sur D25 et D28. Prochaine décision nécessaire : implémentation du véritable bras SAC hybride ou modification explicite du protocole D25. La relaxation argmax4 ne doit pas être acceptée par simple renommage. Ensuite, exécuter l’évaluation complète avec des conditions d’arrivée conformes au protocole retenu. Aucun classement, remplacement de modèle de référence ou passage à J5 n’est autorisé par ce rapport.

*Mise à jour : les points ci-dessus sont repris en §9.*

## 9. Reprise du 29 septembre 2026, 19:20 — compléments

Audit de départ : dépôt sans commit, `git diff` vide (tout est non suivi). Instantané SHA-256 et copie de 66 fichiers avant écriture : `runs/j4/resume-audit-20260929-192113/`. Déjà présents mais non documentés : bras hybride `hybrid_sac.py`, codec `hybrid4_v1`, configuration `a01_sac_hybrid4_v1.json`, pont 0.4.0 (`official_finish`) dans le dépôt uniquement, option `eval --official-finish`. Tests : 64 OK. Nouvelle autorisation de session de l’utilisateur pour des essais réels courts sur A01.

**Code ajouté (tests écrits d’abord, échec observé, puis correction)** :

- `training.save_checkpoint` : écriture dans `checkpoints/.pending-*`, `fsync`, puis renommage ; `latest.json` mis à jour seulement après. Un échec d’écriture laisse l’ancien checkpoint et son pointeur intacts (test synthétique d’écriture interrompue).
- États RNG Python, NumPy, PyTorch et espace d’action sauvés dans `rng_state.pkl` et restaurés après chargement du modèle. Test : une reprise sans pas supplémentaire reproduit les tirages suivants. Limite conservée : l’épisode interrompu et l’état du jeu ne sont pas restaurés.
- `compare.py` et `tm.py compare` : comparaison D25 sur le budget commun, liste des facteurs qui diffèrent, `controlled=false` tant qu’un bras a moins de deux seeds.
- Test de transport `official_finish` (6ᵉ champ CFG, refus si le pont ne le confirme pas).
- `scripts/j4_official_finish_probe.py` : sonde réelle d’arrivée non empêchée.

Suite hors jeu après modifications : 69 tests OK.

**Pont 0.4.0 installé (D36)** : sauvegarde antérieure `runs/j4/backup/official-finish-20260929-185114/` (pont 0.3.0 installé `a7d33d06…`, `builtin.txt` `31c8da23…`). Copies dépôt et installée identiques : `27abc2e1…fd1`. `builtin.txt` inchangé. Hello réel : `bridge_version 0.4.0`, A01, état 512.

**Sonde d’arrivée officielle** : `runs/j4/20260929-192728-official-finish-probe/`. Contrôleur scripté `reference_pursuit_v1`, **non appris**, temps réel ×1, départ normal. Arrivée 3/3 à 30 580 ms, 610 transitions, zéro invalide ; événement `finish_unprevented`, puis écran de fin normal (`game_state 1024`). Aucune modification du dossier `Replays/Autosaves` ; seul `Profiles/steamuser.Profile.Gbx` a changé. Conclusion : le jeu termine normalement la course ; l’enregistrement d’un chrono officiel ou d’un replay reste **non démontré**. L’utilisateur a relancé la course manuellement.

**Fumée hybride réelle** : `runs/j4/20260929-smoke-hybrid4/`, seed 1, ×10. 2 300 transitions (`finished_budget`), puis reprise jusqu’à 2 600 ; `rng_state_available=true`, buffer 2 300 rechargé ; zéro transition invalide ; courbes `train/*` de la tête hybride dans le tableau de bord (`runs/j4/logs/dashboard-smoke-resume.log`, 3 runs exposés). Deux épisodes d’entraînement : une troncature, un abandon ; aucune arrivée. 2 600 transitions de fumée supplémentaires, soit 8 302 au total J4.

**Évaluation figée hybride, mode arrivée officielle** : commande `uv run python scripts/tm.py eval --run runs/j4/20260929-smoke-hybrid4 --checkpoint 00002600 --episodes 20 --mode realtime --speed 1 --official-finish --first-episode 930001`, code 0. Artefacts `runs/j4/20260929-smoke-hybrid4/evals/20260929-193018-00002600-realtime-x1/` (20 épisodes, 15 396 transitions vérifiées dans les JSONL). Résultat : **0/20 arrivées** ; 13 limites de temps, 6 abandons, 1 erreur. L’erreur (épisode 930006, première action) est un état en retard de 130 ms au lieu de 50 ms en temps réel : transition invalidée, gardée au dénominateur. Décision : médiane 1,429 ms, maximum 8,882 ms ; 398 frontières tardives. SHA-256 du modèle et de la normalisation identiques avant/après (`runs/j4/eval20-hybrid-frozen-before.txt`, `sha256sum -c` OK). Après évaluation : pont 0.4.0, A01 en course, vitesse 1. Aucune arrivée : le chemin officiel n’est donc pas exercé par une politique apprise.

**Comparaison** : `runs/j4/logs/compare-smoke-threshold-argmax4.json` (budget commun 2 002 ; seul le codec diffère ; `controlled=false`). Elle illustre l’outil, pas un résultat : avec `learning_starts=2000`, le budget commun est presque entièrement de la collecte aléatoire ; un seul seed par bras.

**Restant pour clore J4** :

1. D25 : runs utilisateur threshold et hybride à budget égal, au moins deux seeds par bras, puis `tm.py compare` et une évaluation figée par bras. Commandes au guide.
2. D28 : arrivée d’une politique apprise en mode `--official-finish`, et preuve que TMNF enregistre le chrono (record local ou replay). L’absence d’autosave dans la sonde scriptée est une question ouverte : l’autosave peut dépendre d’un record battu ou d’un réglage du jeu, non vérifié.
3. Aucune performance, classement ni passage à J5.

## 10. Complément J4-07 — 30 septembre 2026 : diagnostic du run de nuit et corrections

Accord de l’utilisateur pour corriger l’entropie hybride et la récompense (citation dans DECISIONS J4-07). Aucun essai dans le vrai jeu pendant cette reprise.

**Diagnostic** (`runs/j4/20260930-005112-a01_sac_hybrid4_q4_async_r05_night`, commande `uv run python scripts/tm.py trend --run …`) : par cinquième du run, médiane de `progress_max` 0,134–0,161, part maximale d’une commande 0,27–0,32, |direction| 0,50–0,51 : conduite aléatoire du début à la fin. `train/ent_coef` jusqu’à 12,8, `actor_loss` jusqu’à −13 000. Deux causes : cible d’entropie hybride inatteignable en pratique (J4-02) et récompense v1 qui, sans arrivée, ne valorise que la brièveté de l’épisode (`threshold_v1_seed2` : médiane de progression 0 en fin de run, retour −4,8).

**Modifications** (sauvegarde préalable `runs/j4/backup-reward-entropy-20260930/`) :

- `src/trackmania_rl/hybrid_sac.py` : deux températures d’entropie (direction −1, commande 0,3 ln 4), cibles validées, refus d’entraîner un checkpoint à température unique, nouveaux journaux `train/ent_coef_steer|cmd`, `train/entropy_steer|cmd` ;
- `src/trackmania_rl/reward.py` : `progress_mode = "delta"` (reward/2), `break_even_pace` ; reward/1 inchangée (hash `7db1d3d8…` identique à celui des runs J4) ;
- `src/trackmania_rl/training.py` : validation de `sac.hybrid_target_entropy` ;
- `src/trackmania_rl/compare.py` et `scripts/tm.py` : commande `trend` ;
- `configs/training/a01_sac_hybrid4_v2_test30.json` : configuration de contrôle.

**Preuves hors jeu** :

- `PYTHONPATH=src:tests uv run python -m unittest discover -s tests` : 92 tests OK (9 nouveaux : `RewardV2Delta`, `HybridEntropyPerHead`, `Trend`).
- Fumée synthétique de la configuration de contrôle (Trainer réel, jeu 1-D synthétique) : 6 000 transitions, reprise jusqu’à 8 000, `reward/2`, γ par pas 0,99502.
- Contrôle d’apprentissage **sur jeu synthétique** (voiture 1-D des tests, ligne droite de 300 m, pas TMNF), 40 000 transitions chacune, `runs/j4/logs/j4-07-synthetic-learning-check.log` : configuration v2 177 arrivées, meilleur 8,66 s, gaz 84–94 % dès la deuxième tranche ; configuration du run de nuit 135 arrivées, meilleur 8,88 s, gaz 70–77 % à partir de la troisième tranche. **Limite** : ce jeu est trop simple pour reproduire l’échec réel (une conduite aléatoire y atteint l’arrivée, et la direction n’y compte pas). Il montre que la chaîne v2 apprend, et plus vite, mais ne prouve pas la correction sur A01.

**Reste à faire** : test de contrôle de 30 min lancé par l’utilisateur (GUIDE-J4, « Test de contrôle v2 »), lecture par `tm.py trend`. D25 et D28 restent ouverts ; aucune performance annoncée.

**Premier test v2 en jeu et correction** (utilisateur, D37) : `runs/j4/20260930-095814-a01_sac_hybrid4_v2_test30`. `tm.py trend` à 60 380 transitions : médiane de progression 0,059 → 0,382, meilleur 0,54, commande dominante 0,69 (gaz), retour médian +3,3 ; entropies sur leurs cibles (direction −1,05, commande 0,37–0,41), α 0,001–0,013. Puis effondrement à ~63 400 : braquage à fond et gaz 100 %, 137 transitions par épisode, `critic_loss = inf`. Cause et correction : DECISIONS J4-07d (log-densité de la direction saturée). Tests : 95 OK (`SaturatedSteer`, `Divergence` ajoutés). Ce run est inutilisable après ~63 000 transitions ; un nouveau run avec la même configuration est nécessaire.

## 11. Arrivées perdues et freinage final — 30 septembre 2026

Analyse hors jeu du run utilisateur `runs/j4/20260930-104918-a01_sac_hybrid4_v2_ent05` : checkpoint final `00953949`, 953 949 transitions, 1 453 épisodes consignés, 381 arrivées, 238 erreurs. Parmi les erreurs, 108 portent `state: finish tick delta 0 outside (0, 50]` à une progression proche de 1. Le dernier état valide et l’état d’arrivée ont le même `race_ms` ; le callback d’arrivée peut donc suivre une frontière d’action au même tick. En temps réel, l’arrivée peut aussi précéder l’application de l’action suivante : l’évaluation existante contient des erreurs `transport: inputs released by game: finish` près de la ligne. Ces cas font perdre le bonus terminal et faussent le taux d’arrivée mesuré ; on ne reclasse pas rétrospectivement les épisodes invalides en arrivées vérifiées.

Correctif J4-10 dans `env.py` et `reward.py` : accepter une arrivée confirmée sans tick supplémentaire avec séquence, chrono et checkpoints cohérents ; aucun temps ou progrès supplémentaire n’est payé, le bonus terminal est conservé. Accepter aussi l’état d’arrivée portant l’identifiant de l’action précédente lorsqu’il arrive entre deux commandes en mode temps réel, et relâcher les commandes après toute fin. Les transitions nouvelles consignent `dt_ms`, `same_tick_finish` et `finish_before_action`. Le pont installé n’a pas été modifié. Tests synthétiques : deux erreurs reproduites avant correction ; arrivée avec petit déplacement au même tick acceptée ; téléportation au même tick rejetée.

Le checkpoint 953949 a terminé 3/5 courses figées à ×1, meilleur 29,53 s et médiane des trois arrivées 29,59 s (`evals/20260930-155548-00953949-realtime-x1/`). Les deux échecs portent `inputs released by game: finish`. Ce n’est pas une preuve D28 ni un chrono officiellement enregistré.

Dans les traces de ces évaluations, le frein est demandé sur 81–90 % des décisions entre `Progress=0,80` et `0,90`, souvent avec le gaz. Sur une course de 29,52 s, la politique passe 0,80 à 23,60 s, 0,90 à 26,05 s, 0,95 à 27,60 s et 0,99 à 29,15 s. La référence humaine de 27,11 s passe ces seuils à 22,74, 24,90, 26,03 et 26,91 s. L’écart croît donc dans le dernier secteur, surtout après 0,95. La référence est une course humaine distincte de la course personnelle annoncée à 25 s. Les anciennes traces d’évaluation n’enregistrent pas la vitesse ni les contacts par roue : elles montrent le freinage, pas sa cause. Les futures traces ajoutent ces diagnostics. Aucune modification de récompense, de politique, d’observation ou du freinage n’est déduite de ce seul constat.

**Premier essai réel du correctif, autorisé par l’utilisateur** : cinq courses figées à ×1, même checkpoint, trace `evals/20260930-162930-00953949-realtime-x1/`. Résultat : 3/5 arrivées, meilleur 29,50 s ; 2 erreurs `same-tick finish is not the state after the last boundary`. La trace du pont confirme à l’épisode 910003 un état frontière et un état arrivée tous deux à 29 540 ms, `action_id=578`, séquences 662796 puis 662797, `source_seq=662795` inchangé, checkpoints 2 puis 3, mais position déplacée de ~0,55 m. Même scénario à l’épisode 910005. Le premier garde-fou exigeait une position identique : il était trop strict. Correctif ajusté : autoriser un déplacement au plus égal à `max_speed_mps × tick_ms`, calculer l’observation finale depuis la position réellement rapportée et ne pas payer une seconde fois la progression tant que le temps reste à 0 ms. Un saut de 100 m reste invalide en test synthétique. Confirmation réelle de cet ajustement encore requise.

Les nouveaux diagnostics confirment que la politique demande le frein et que TMNF l’applique : zéro divergence entre la commande et `applied_inputs` dans le dernier secteur de ces cinq courses. Entre `Progress=0,80` et `0,90`, frein sur 88,75 % des 240 décisions, toujours avec le gaz ; quatre roues en l’air sur 208/240 décisions, vitesse affichée médiane proche de 300. Entre 0,95 et 0,99, frein sur 0/151 décisions mais vitesse affichée médiane ~204. Le freinage observé pendant le saut peut avoir un effet différé à l’atterrissage ; ces traces seules ne prouvent pas sa causalité. Un essai contrôlé serait nécessaire avant d’ajuster la récompense ou la politique.

`uv run` a révélé un second défaut d’outillage : `legacy_controller` identifiait le parent `uv` comme pilote et refusait son propre processus Python. `controller_guard.py` vérifie désormais que le processus candidat est bien Python. Test synthétique rouge avant correction, vert après. Suite complète hors jeu après tous les correctifs : `UV_CACHE_DIR=/tmp/trackmania-uv-cache PYTHONPATH=src:tests uv run --offline --no-sync python -m unittest discover -s tests`, **116 tests OK**. Aucun entraînement lancé ni poids modifié.
