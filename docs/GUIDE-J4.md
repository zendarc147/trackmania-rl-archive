# Guide J4 — lancer et diagnostiquer un run A01

## Statut et prérequis

L’outillage a produit des transitions et checkpoints réels. J4 reste partiel : la comparaison avec un véritable SAC hybride (D25) et l’évaluation complète D28 ne sont pas validées. Des arrivées apprises ont été observées ; la fiabilité et la stabilité restent insuffisamment validées. Voir [le rapport](reports/J4-apprentissage.md).

Depuis la racine du dépôt, utiliser `uv`. Ouvrir A01 manuellement dans TMNF/TMInterface avec le pont 0.4.0 installé (0.3.0 suffit hors `--official-finish`). Ne pas toucher aux commandes pendant un run. Un seul processus `train`, `resume` ou `eval` contrôle le jeu à la fois. Aucun Hermes ni LLM n’intervient dans la conduite.

Les plafonds globaux J4 ont été levés par l’utilisateur dans GOAL.md. Les runs gardent un budget par défaut ; l’option explicite `--until-stopped` permet désormais de poursuivre sans limite de transitions. Les entraînements longs sont lancés et suivis par l’utilisateur (D37).

## Interface web locale (J4, 30 septembre 2026)

Depuis la racine du dépôt, ouvrir l'atelier avec une commande courte :

```bash
./scripts/atelier
```

Elle ouvre le navigateur si le serveur tourne déjà, sinon démarre le serveur puis ouvre le navigateur. Lors d'un nouveau démarrage, laisser le terminal ouvert ; Ctrl+C ferme seulement le serveur. Pour démarrer manuellement, utiliser `PYTHONPATH=src uv run python -m trackmania_rl.webui`.

Ouvrir `http://127.0.0.1:8765` dans le navigateur. Serveur lié à `127.0.0.1` uniquement ; ne pas publier ce port ni l'utiliser derrière un proxy public. Le navigateur n'exécute pas d'entraînement tout seul. Les commandes lancées par l'utilisateur depuis l'interface sont des processus séparés ; fermer l'onglet ou arrêter le serveur ne les arrête pas. Utiliser « Arrêter » pour demander un checkpoint propre. Le journal de la dernière commande est visible tant que le serveur reste ouvert ; les fichiers permanents restent dans `runs/j4/`.

- **Vue d'ensemble** : runs, état, progression des derniers épisodes, tendance indicative et incidents ; actualisation toutes les 5 s.
- **Entraînement** : choisir une configuration, puis lancer, arrêter ou reprendre, avec vitesse, budget ou poursuite sans plafond. Ouvrir la map manuellement avant tout contrôle ; ne pas lancer d'autre contrôleur.
- **Modèles & conduite** : sélectionner un run et son checkpoint, puis « Charger et voir conduire ». Défaut : une course, politique figée, temps réel, ×1. Après une arrivée en mode « arrivée non empêchée », relancer la map manuellement. Voir les résumés des évaluations et lancer TensorBoard local.
- **Comparaison** : sélectionner les runs, choisir la fraction finale et afficher le budget commun, les seeds, les différences et le statut `controlled` (diagnostic, non D28).
- **Configurations** : cloner une configuration sous un **nouveau** nom. Les champs simples couvrent budget, seed, vitesse, codec et récompense. L'éditeur JSON complet donne accès aux autres paramètres SAC, learner, pont et enregistrement. La sauvegarde valide la configuration et n'écrase jamais un modèle existant. Le fichier du run reste figé ; pour modifier SAC ou récompense, créer une nouvelle expérience plutôt que reprendre un ancien run.

La protection de contrôleur par verrou entre processus s'applique à `tm.py train`, `resume` et `eval`, y compris hors interface. Un run démarré avant l'ajout de ce verrou est détecté par son PID et sa commande actifs : l'interface refuse alors de lancer un second pilote. `stop` reste disponible sur ce run. TensorBoard déjà ouvert sur 127.0.0.1:6006 est réutilisé sans démarrer une seconde instance ; le bouton « Arrêter » ne cible que celui lancé par cette interface.

**Vérification réelle, 30 septembre 2026** : depuis l'interface, évaluation figée à ×1 du checkpoint `00953949` du run `20260930-104918-a01_sac_hybrid4_v2_ent05` : une course, une arrivée mesurée à 29,520 s (`evals/20260930-144245-00953949-realtime-x1/eval_summary.json`). Le jeu rapporte cette arrivée, mais pas un temps officiel comparable à un classement. Run de fumée séparé `20260930-145137-a01_sac_hybrid4_v2_ent05-5ab1e4` : démarrage 100 transitions, reprise à 200, seconde reprise avec STOP propre à 415 transitions et checkpoint `00000415` ; zéro transition invalide. Essais courts autorisés par l'utilisateur, non preuve d'apprentissage ou d'entraînement long.

## Test de contrôle v2 (J4-07, 30 septembre 2026) — à faire avant tout long run

Le run de nuit du 30 septembre n’a rien appris : l’entropie hybride gardait la politique aléatoire et la récompense v1 poussait à s’arrêter (DECISIONS J4-07). La configuration suivante corrige les deux (récompense v2, une température d’entropie par tête) :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_v2_test30.json
```

300 000 transitions, environ 30 min à ×10. Pendant et après le run, dans un autre terminal :

```bash
uv run python scripts/tm.py trend --run runs/j4/<run_id>
```

Lecture : une conduite aléatoire donne `cmd_max` ~0,25 et `|steer|` ~0,50 (valeurs du run de nuit sur 4 M de transitions). On attend une `prog_med` qui monte d’une tranche à l’autre et un `cmd_max` au-dessus de 0,4. Dans TensorBoard, `train/entropy_cmd` doit descendre vers ~0,42 et `train/ent_coef_*` ne doit pas grimper sans fin.

- Verdict `signs of learning` : prolonger le même run, sans le relancer de zéro :

```bash
uv run python scripts/tm.py resume --run runs/j4/<run_id> --budget 4000000
```

- Verdict `no sign of learning` à la fin des 300 000 : arrêter et envoyer le chemin du run pour diagnostic ; ne pas lancer de nuit.
- `mixed` : relancer `trend` plus tard, ou prolonger à 600 000.

Si `status` affiche la phase `diverged`, une perte est devenue infinie : le run s’est arrêté sans sauvegarder de modèle cassé ; envoyer le chemin du run. Le verdict est indicatif (épisodes d’entraînement stochastiques) ; la preuve de performance reste l’évaluation figée D28.

## Lancer

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_threshold_v1.json
```

Le terminal affiche le chemin `runs/j4/<run_id>`. Conserver ce chemin. Pour tester l’autre encodage, après arrêt du premier run :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_argmax4_v1.json
```

Pour le bras hybride D25 (direction gaussienne + tête catégorielle sur les quatre couples gaz/frein) :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_v1.json
```

Comparaison D25 à budget commun (seules les transitions jusqu’au plus petit total comptent) :

```bash
uv run python scripts/tm.py compare runs/j4/<run_threshold> runs/j4/<run_hybrid4> --out runs/j4/<fichier>.json
```

`controlled` ne vaut `true` que si seul le codec diffère et si chaque bras a au moins deux seeds. Pour cela, lancer chaque configuration avec deux seeds en changeant `seed` dans une copie de la configuration. Les épisodes d’entraînement restent stochastiques : conclure ensuite par une évaluation figée.

`argmax4_v1` est une relaxation continue à quatre scores, pas un SAC hybride catégoriel. Les deux configurations restent des propositions. Récompense et seuils du tracker restent également des propositions. Ne pas comparer les petits runs de fumée comme une expérience contrôlée.

### Affinage horizon 0,95 et pont 0.4.1 (J4-11, 30 septembre 2026)

1. Arrêter le run en cours (`tm.py stop --run …`) et attendre sa sauvegarde.
2. Installer le pont 0.4.1 (correctif des mini-épisodes après arrivée), puis recharger le plugin dans TMInterface ou relancer le jeu :

```bash
cp plugins/TrackmaniaRLBridge.as "$HOME/.local/share/Steam/steamapps/compatdata/11020/pfx/drive_c/users/steamuser/Documents/TMInterface/Plugins/TrackmaniaRLBridge.as"
```

3. Ouvrir A01, puis lancer l’affinage depuis le dernier checkpoint du run `20260930-104918-a01_sac_hybrid4_v2_ent05` :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_v3_h095.json --until-stopped
```

Vérifier : `hello` annonce `bridge_version` 0.4.1 ; `invalid_transitions` reste proche de 0 ; `incidents.jsonl` contient `init_from` avec le checkpoint repris ; comparer `episode/finish_s` et `totals/best_finish_s` avec le run source. Les transitions repartent de 0. Le retour actualisé n’est pas comparable à celui du run source (discount différent).

## Suivre

```bash
uv run python scripts/tm.py status
uv run python scripts/tm.py status --run runs/j4/<run_id>
uv run python scripts/tm.py dashboard --logdir runs/j4
```

Ouvrir `http://localhost:6006`. Le serveur écoute localement par défaut ; ne pas utiliser `--bind-all` sans besoin explicite. Regarder `episode/finished`, `episode/progress_max`, les retours, les termes de récompense, les commandes, les latences et les pertes SAC. Une perte décroissante ne prouve pas un progrès en course.

Les configurations utilisent `torch_threads = 8`, le plus rapide mesuré sur ce laptop (16 threads est 3 à 4 fois plus lent). Garder la même valeur pour les runs comparés.

### Accélérer (propositions J4-04 à J4-06, 30 septembre 2026)

Deux configurations hybrides plus rapides :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_q4_async_r1.json
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_q4_async_r05.json
```

Elles combinent trois réglages, utilisables séparément dans toute configuration :

- `"sac": {"hybrid_critic": "q4"}` (hybride seulement) : critiques `[s, steer] → 4 valeurs Q`, une passe au lieu de quatre pour l’espérance sur les commandes. Mêmes pertes que `hybrid4_v1`. Sans cette clé, l’ancien critique est utilisé ; les anciens runs se rechargent tels quels.
- `"learner": {"mode": "async", ...}` : le jeu est piloté avec une copie figée de l’acteur pendant qu’un thread fait les gradients. Si l’apprenant prend plus de `max_update_lag` mises à jour de retard, la collecte attend au plus `max_wait_ms` (sous le délai d’action du pont).
- `"learner": {"updates_per_transition": r}` : gradients par transition (1 = historique). Aussi utilisable en `"mode": "sync"`, pour tout `r > 0`. Remplace `sac.train_freq` et `sac.gradient_steps`, qui doivent alors être absents.

Mesure hors jeu, jeu **synthétique** avec 5 ms par pas (émulation du ×10), vrai calcul SAC, 8 threads, laptop chargé (`runs/j4/logs/learner-bench-20260930.json`) : hybride historique 31 trans/s ; q4 synchrone r=1 50 ; q4 async r=1 68 ; q4 async r=0,5 126 ; q4 async r=0,25 133 (le jeu émulé devient la limite). Threshold : 57 historique, 81 async r=1, 133 async r=0,5. Non mesuré dans le vrai jeu.

À surveiller dans TensorBoard : `learner/updates_per_transition` (ratio réellement atteint), `learner/lag_updates`, `learner/update_ms_mean`, `learner/collector_wait_s`, `learner/collector_wait_timeouts`. Si le ratio réel reste sous la cible, l’apprenant ne suit pas : baisser `updates_per_transition` ou la vitesse.

Limites : un run async n’est pas reproductible bit à bit depuis sa seed (ordre gradients/transitions dépendant du temps). La politique qui conduit a au plus quelques mises à jour de retard. Changer le critique, le ratio ou le mode crée une nouvelle expérience : `compare` compte `learner` et `sac` parmi les facteurs, et ces runs ne forment pas un bras contrôlé D25 face aux runs hybrides historiques. Un ratio plus faible peut demander plus de transitions pour apprendre autant.

Banc hors jeu :

```bash
uv run python scripts/j4_learner_bench.py --game-ms 5 --transitions 1500
```

Les pertes apparaissent après `learning_starts=2000` et lors d’une émission de métriques. Le débit et l’ETA sont des diagnostics, pas une promesse. La première mesure de fenêtre du run threshold à 17:41 est erronée après reprise ; le compteur initial de fenêtre a été corrigé ensuite et couvert par la suite hors jeu, mais pas remesuré en jeu.

## Arrêter et reprendre

```bash
uv run python scripts/tm.py stop --run runs/j4/<run_id>
uv run python scripts/tm.py resume --run runs/j4/<run_id>
```

Pour poursuivre le run `20260930-104918-a01_sac_hybrid4_v2_ent05` au-delà de ses 300 000 transitions, sans plafond de transitions :

```bash
uv run python scripts/tm.py resume --run runs/j4/20260930-104918-a01_sac_hybrid4_v2_ent05 --until-stopped
```

Lancer cette commande soi-même après avoir ouvert A01 ; ne pas avoir un autre `train`, `resume` ou `eval` connecté. L’option s’applique à cette session : pour continuer sans plafond après un arrêt et une nouvelle reprise, la redonner. `status` indique alors `budget_transitions: null` et n’affiche pas d’ETA. Les checkpoints automatiques restent actifs à la fin d’un épisode après l’intervalle configuré (50 000 transitions pour ce run). Le disque continue de se remplir : chaque checkpoint garde son replay buffer. Une divergence ou une erreur peut également arrêter le run ; `--until-stopped` ne masque pas ces arrêts.

STOP termine la transition, sauvegarde puis sort. Un Ctrl+C dans le terminal d’entraînement demande le même arrêt propre. Un deuxième Ctrl+C force l’arrêt sans nouvelle sauvegarde. Arrêter également TensorBoard par Ctrl+C.

`resume --budget N` désigne le nouveau total de transitions, pas un nombre à ajouter. Il reste limité par `cap_transitions` de la configuration du run. Une reprise d’un run déjà au total demandé ne réalise aucun apprentissage supplémentaire.

La reprise recharge poids, critiques cibles, optimiseurs, coefficient d’entropie, replay buffer, compteurs et, depuis la reprise J4 du 29 septembre, les états des générateurs aléatoires (`rng_state.pkl`). Elle repart au départ normal et ne restaure pas l’épisode interrompu ni l’état du jeu. Elle n’est donc pas bit à bit équivalente à un entraînement continu. Les anciens checkpoints sans `rng_state.pkl` restent reprenables ; `incidents.jsonl` indique `rng_state_available`.

## Évaluer séparément

```bash
uv run python scripts/tm.py eval --run runs/j4/<run_id> --episodes 20 --mode realtime --speed 1
```

Cette commande a été exercée sur 20 tentatives par checkpoint existant : 20 abandons pour chacun, aucune arrivée. Les preuves figurent au rapport J4 §6 bis.

Arrivée officielle (pont ≥ 0.4.0) : ajouter `--official-finish`. Le pont ne bloque plus la fin de course : TMNF ouvre son écran de fin normal. Après une arrivée, l’évaluation s’arrête ; relancer A01 manuellement puis relancer `eval` avec `--first-episode` suivant. Les échecs (abandon, limite) continuent d’enchaîner seuls. Sonde réelle : rapport J4 §9. Le nombre d’essais et le gel sont vérifiés ; la validation officielle d’une arrivée reste non démontrée. Pour cibler le modèle threshold déjà évalué : ajouter `--checkpoint 00003200` au run `20260929-smoke-threshold`.

L’évaluateur charge une politique déterministe et vérifie le hash de normalisation. Aucune mise à jour des poids. Les échecs restent au dénominateur. Limite importante : le pont empêche la validation officielle de l’arrivée pour permettre les resets ; ces chronos ne sont pas comparables à un classement, même à ×1. Ne pas annoncer D28 entièrement validé ni de rang mondial.

## Données et dépannage

Dans `runs/j4/<run_id>/` :

- `config.json`, `versions.json`, `versions_resume_*.json` : paramètres, versions, empreintes et commandes ;
- `status.json` : phase et compteurs ; vérifier l’horodatage, pas seulement `running` ;
- `episodes.jsonl`, `transitions.jsonl`, `incidents.jsonl` : diagnostics et raisons d’arrêt ;
- `sb3/` : événements TensorBoard et CSV ; les nouvelles reprises ont un CSV distinct ;
- `checkpoints/latest.json` : dernier checkpoint ; son dossier contient `model.zip`, `trainer_state.json`, `replay_buffer.pkl` ;
- `checkpoints/best.json` : record d'entraînement ; chaque nouveau meilleur temps d'arrivée écrit `checkpoints/best-<ms>ms-<transitions>/` (`model.zip` + `trainer_state.json`, sans replay buffer, non reprenable). Évaluer avec `tm.py eval --run <run> --checkpoint best`. Le record a été roulé par la politique stochastique d'entraînement : seule l'évaluation figée donne le temps du modèle. Courbe TensorBoard : `totals/best_finish_s`. `episode/return` n'inclut plus les épisodes invalides (erreurs de protocole) ;
- `evals/<id>/` : `eval_summary.json`, `eval_episodes.jsonl`, `eval_transitions.jsonl`.

Depuis J4-10, les nouvelles lignes de `eval_transitions.jsonl` contiennent aussi `display_speed`, `wheel_contact`, `wheel_sliding`, `applied_inputs`, `lateral_m`, `vertical_m`, `same_tick_finish` et `finish_before_action`. Ces champs servent au diagnostic ; ils ne changent pas les observations du modèle. Pour examiner le freinage final, évaluer le checkpoint figé `00953949` du run `20260930-104918-a01_sac_hybrid4_v2_ent05` à ×1, puis comparer les lignes où `progress` vaut 0,80–1,00. L’utilisateur lance l’évaluation après avoir ouvert A01 et vérifié qu’aucun autre contrôleur ne pilote le jeu. Le correctif d’arrivée J4-10 doit encore être vérifié en jeu : compter les arrivées et les erreurs `finish` dans le nouveau dossier `evals/`.

Chaque checkpoint conserve son replay buffer ; surveiller l’espace disque sur les longs runs. Un checkpoint est écrit dans `checkpoints/.pending-*`, synchronisé sur disque, puis renommé ; `latest.json` ne pointe que vers un checkpoint complet. Un dossier `.pending-*` restant signale une sauvegarde interrompue : le conserver pour diagnostic, il n’est jamais repris. Ne pas supprimer d’autres artefacts.

Si le pont est trop ancien ou A01 n’est pas chargée, corriger la préparation avant de relancer. Après timeout ou déconnexion, consulter `incidents.jsonl` ; les transitions invalides sont exclues du replay buffer. Ne jamais lancer un second contrôleur pour dépanner le premier encore actif.

Tests hors jeu :

```bash
PYTHONPATH=src:tests uv run python -m unittest discover -s tests
uv run python scripts/j4_dashboard_smoke.py --port 6008
```

Le second test démarre brièvement le tableau de bord puis demande son arrêt. Il ne pilote pas le jeu.

### Pont 0.4.2 : reset en course par rembobinage (J4-12a, 1er octobre 2026)

À faire au prochain arrêt du run (`tm.py stop --run …`), jamais pendant un run :

```bash
cp plugins/TrackmaniaRLBridge.as "$HOME/.local/share/Steam/steamapps/compatdata/11020/pfx/drive_c/users/steamuser/Documents/TMInterface/Plugins/TrackmaniaRLBridge.as"
```

Puis recharger le plugin dans TMInterface ou relancer le jeu ; la console doit afficher `RL bridge 0.4.2 listening`. Reprendre ensuite avec `resume --run … --until-stopped`. Retour arrière : recopier `runs/j4/backup/TrackmaniaRLBridge-0.4.1.as` au même endroit.

### v3c : buffer 1M, learning rate 1e-4 (J4-13, 1er octobre 2026)

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_v3c_h095.json --until-stopped
```

Surveiller `train/critic_loss` avec le taux d'arrivée et la progression. Le seuil initialement proposé de ~0,2 ne suffit pas à diagnostiquer la santé du critique : un minibatch peut manquer les échecs rares, et une bonne médiane peut masquer de fortes surestimations. Le [diagnostic du 1er octobre](reports/J4-critic-diagnostic-20261001.md) montre que v3c hérite déjà de ce problème et que l'augmentation du buffer et la baisse du LR ne l'ont pas résolu. Il décrit également le warmup aléatoire de 2 000 actions réintroduit par `init_from`, corrigé ensuite en J4-15 (voir v4 ci-dessous). Reprendre le même checkpoint sans correction ne constitue pas une solution démontrée.

Arrêter avec `tm.py stop --run …` si la conduite s'effondre durablement et conserver les artefacts pour diagnostic. Checkpoints tous les 250 000 transitions, plus un à chaque arrêt propre. Disque : jusqu’à ~230 Mo par checkpoint avec un buffer plein, plus `transitions.jsonl` (~470 Mo par million de transitions).

## v4 : correction du critique et observations v2 (J4-15)

Cette configuration remplace v3c comme point de départ recommandé pour vérifier les corrections. Elle est testée hors jeu ; elle ne garantit pas encore une stabilité durable. Ouvrir A01 et vérifier que le précédent contrôleur est arrêté, puis lancer depuis la racine :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_v4_obs2.json --run-id a01-v4-obs2
```

Le nouveau run migre le checkpoint v3 `00660037` : acteur, critiques, critiques cibles et températures sont conservés. Deux entrées décrivent le contexte d'abandon. Les anciens fichiers restent intacts. Les optimiseurs et le replay repartent à neuf : les anciens exemples ne contiennent pas ce contexte. **La conduite utilise immédiatement l'acteur entraîné**, avec son exploration SAC ; les 2 000 premières transitions remplissent le replay avant les gradients. Le compteur du nouveau run part à zéro ; les poids ne repartent pas de zéro.

Le budget initial est de 100 000 nouvelles transitions. Checkpoints tous les 25 000 et à l'arrêt propre. Ce nom de run ne s'utilise qu'une fois avec `train` ; pour continuer, utiliser `resume`.

Suivi, dans un autre terminal :

```bash
uv run python scripts/tm.py dashboard --logdir runs/j4/a01-v4-obs2
uv run python scripts/tm.py status --run runs/j4/a01-v4-obs2
```

Dans TensorBoard (`http://127.0.0.1:6006`), surveiller ensemble :

- `episode/finish_rate_50` et `episode/finish_window_size` : arrivées sur les 50 derniers épisodes au maximum, erreurs techniques incluses dans le dénominateur ;
- `diagnostics/fixed_uniform_mse` : erreur sur un échantillon fixe du replay ;
- `diagnostics/fixed_abandon_td_abs_max` et `diagnostics/fixed_abandon_mse` : erreur sur les abandons terminaux ;
- les métriques `fixed_finish_*`, la progression, les incidents et le retard du learner.

Les sondes sont calculées tous les 1 000 updates, avec 2 048 exemples uniformes et jusqu'à 64 exemples par type terminal. Un groupe apparaît lorsqu'il existe dans le replay, puis reste fixe, y compris après reprise. Les groupes peuvent donc commencer à des moments différents. Une hausse durable de l'erreur terminale accompagnée d'une chute des arrivées justifie un arrêt et un audit ; une loss de minibatch isolée à 0,2 ne suffit pas. Ces sondes utilisent les données d'entraînement, pas une évaluation indépendante.

Arrêter proprement (ou Ctrl+C dans le terminal d'entraînement), puis auditer le checkpoint complet :

```bash
uv run python scripts/tm.py stop --run runs/j4/a01-v4-obs2
uv run python scripts/tm.py audit-critic --run runs/j4/a01-v4-obs2 --samples 10000 --out runs/j4/a01-v4-obs2/audit-critic-1.json
```

Attendre que le statut indique l'arrêt avant cet audit final. L'audit ne contrôle pas le jeu. Il examine tous les terminaux du buffer et un échantillon uniforme (`--samples 0` pour tout le buffer), ainsi que les sondes fixes conservées. `--checkpoint 00025000` permet de choisir un checkpoint précis ; `best` ne convient pas, car il ne contient pas de replay. Les types terminaux sont inférés de la formule de récompense ; un bonus d'arrivée indiscernable produit un groupe terminal unique. `--out` refuse d'écraser un fichier existant : utiliser un nouveau nom pour chaque rapport.

Après examen des résultats, poursuivre avec les poids et le replay v2 du même run :

```bash
uv run python scripts/tm.py resume --run runs/j4/a01-v4-obs2 --budget 200000
```

`200000` désigne le total du nouveau run. `--until-stopped` reste disponible pour une poursuite explicitement sans plafond. Pour évaluer la conduite, arrêter l'entraînement puis lancer :

```bash
uv run python scripts/tm.py eval --run runs/j4/a01-v4-obs2 --episodes 20 --mode realtime --speed 1
```

Politique figée, échecs inclus. Ce mode ne certifie pas un chrono officiel (voir D28 plus haut). Tous les paramètres, incidents et résultats restent dans `runs/j4/a01-v4-obs2/`. Preuves de correction et limites : [rapport J4-15](reports/J4-critic-corrections-20261001.md).

## v5 : récompense v3, chrono près du record (J4-16)

Configuration préparée, **non lancée**. Elle repart du checkpoint `03092363` de `a01-v4-obs2b`. Les poids, les optimiseurs et les températures sont conservés. Le replay repart vide (`fresh_replay`), car les anciennes récompenses suivent v2. Arrêter tout autre contrôleur, ouvrir A01, puis :

```bash
uv run python scripts/tm.py train --config configs/training/a01_sac_hybrid4_v5_lap.json --run-id a01-v5-lap
uv run python scripts/tm.py dashboard --logdir runs/j4/a01-v5-lap
uv run python scripts/tm.py status --run runs/j4/a01-v5-lap
```

Arrêt et reprise comme pour v4 (`stop`, puis `resume --run runs/j4/a01-v5-lap --budget …`). Points à surveiller :

- taux d'arrivée et meilleur chrono : la conduite ne doit pas régresser par rapport à v4 pendant que le critique se recale ;
- `fixed_abandon_*` : un abandon vaut désormais environ −60 sur le terme lap, contre ≈ 0 avant ;
- `eta_s` dans les transitions : c'est le chrono projeté au rythme du record (23,77 s au départ) ;
- les retours ne sont pas comparables avec v2, car il s'agit d'une autre récompense. Comparer les chronos D28.

Formule et chiffres : [REWARDS §7](REWARDS.md) et DECISIONS J4-16.

