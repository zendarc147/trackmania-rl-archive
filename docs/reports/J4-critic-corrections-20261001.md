# J4-15 — Corrections du critique et de la reprise (1er octobre 2026)

## Résultat et limites

Les défauts identifiés et les corrections approuvées après [J4-14](J4-critic-diagnostic-20261001.md) sont traités dans le code. **130 tests hors jeu passent**, dont 11 nouvelles régressions. La migration du vrai checkpoint v3 à 660 037 transitions préserve exactement les sorties initiales des réseaux sur 1 024 observations réelles. Aucun entraînement ni contrôle du jeu n'a été lancé pour cette correction.

Cela ne prouve pas encore la stabilité de l'apprentissage ni une meilleure conduite. Le compteur d'abandon caché est une incohérence corrigée ; son rôle causal exact dans la divergence reste non isolé. Le critique source est moins surestimé sur l'échec témoin que celui de v3c, mais n'est pas « sain » au sens d'une calibration parfaite. J4, D25 et D28 restent ouverts.

## Modifications

- `training.py`, `hybrid_sac.py` : une politique entraînée chargée par `init_from` conduit immédiatement. Les 2 000 actions uniformément aléatoires ne sont plus réintroduites. Le délai avant gradients dépend de la disponibilité du replay ; un modèle réellement non entraîné conserve son warmup restant.
- `observation.py`, `env.py`, `gym_env.py`, `runtime.py`, `evaluation.py` et CLI : observations v2, 27 entrées. Les 25 entrées v1 restent identiques. Les deux ajouts sont le temps restant avant abandon et l'écart au record de progression qui réarme ce temps. Formules et approbation D31 dans [OBSERVATIONS](../OBSERVATIONS.md). Les règles de récompense et de terminaison restent inchangées.
- `checkpoint_migration.py` : migration explicite `observation_v2`. Les deux nouvelles colonnes commencent à zéro ; les colonnes d'action des critiques sont décalées correctement. Acteur, critiques, critiques cibles et températures sont conservés. **Replay et optimiseurs neufs** : aucun historique absent n'est inventé dans les anciennes transitions. Après ce nouveau départ, une reprise ordinaire restaure les optimiseurs et le replay v2.
- `critic_diagnostics.py` : sondes fixes uniformes et terminales, sauvegardées avec le modèle, évaluées sans gradients ni modification des générateurs aléatoires globaux. La CLI `audit-critic` examine un checkpoint sans connexion au jeu. Le taux d'arrivée sur les 50 derniers épisodes est enregistré avec la taille de fenêtre.
- Nouvelle configuration `configs/training/a01_sac_hybrid4_v4_obs2.json`. Source v3 `00660037`, LR 1e-4, buffer de capacité 1M, discount 0,95/s, ratio async 0,5 conservés. Les 2 000 premières transitions viennent de l'acteur entraîné et remplissent le nouveau replay. Premier budget utilisateur 100 000, checkpoints tous les 25 000. Ce budget prépare un contrôle intermédiaire, pas une promesse de convergence.

La priorisation du replay n'est pas ajoutée : les contrôles hors jeu précédents n'ont pas montré une réparation suffisante, et le suréchantillonnage brut dégradait la MSE globale. Les coefficients de récompense, l'entropie et l'horizon ne sont pas modifiés à nouveau.

## Choix du checkpoint source

Audit de trois checkpoints v3, chacun sur 10 000 transitions uniformes (seed 123) et tous les terminaux de son propre replay :

| Checkpoint | MSE uniforme | Abandons | MSE des abandons | Erreur TD maximale des abandons |
| --- | ---: | ---: | ---: | ---: |
| 559 432 | 0,31118 | 30 | 52,04 | 27,80 |
| 609 706 | 0,11739 | 13 | 137,15 | 27,28 |
| 660 037 | 0,06620 | 8 | 90,97 | 21,32 |

Les buffers diffèrent ; ce tableau ne constitue pas une comparaison sur un jeu commun ni une garantie de santé. Le dernier checkpoint est retenu comme point de départ explicite, antérieur aux dérives v3b/v3c, avec l'erreur uniforme et l'erreur terminale maximale les plus faibles de cette sonde. Le diagnostic J4-14 compare aussi les checkpoints sur un même échec témoin. Les anciennes sources restent intactes.

## Preuves reproductibles

Artefacts : `runs/diagnostics/20261001-corrections/`.

```bash
PYTHONPATH=src:tests UV_CACHE_DIR=/tmp/trackmania-uv-cache uv run --offline python -m unittest discover -s tests -q
PYTHONPATH=src UV_CACHE_DIR=/tmp/trackmania-uv-cache uv run --offline python runs/diagnostics/20261001-corrections/verify_real_migration.py
uv run python scripts/tm.py audit-critic --run runs/j4/20260930-204802-a01_sac_hybrid4_v3_h095 --checkpoint 00660037 --samples 10000
```

- `tests.log` : **130 tests, 23,910 s, OK**. Le premier passage en bac à sable a bloqué 17 tests sur la création de sockets localhost. La suite complète a ensuite été exécutée avec cet accès ; les serveurs de test sont synthétiques, sans TMNF.
- `tests/test_critic_corrections.py` : 11 tests couvrent contexte/reset, abandon terminal, troncature avec bootstrap, migration des cinq couches d'entrée, températures, absence de warmup aléatoire pour un modèle entraîné, warmup restant pour un modèle non entraîné, conservation des sondes, reprise async pendant le remplissage du replay et compatibilité de l'évaluation.
- `real-migration.json` : 1 024 observations réelles, contextes supplémentaires artificiels utilisés uniquement pour vérifier l'invariance, jamais introduits dans le replay. Erreur maximale **0,0** pour distributions de l'acteur, critiques, critiques cibles et températures. Schéma 27, replay vide, attente de 2 000 transitions avant gradients, utilisation immédiate de l'acteur, sauvegarde/rechargement réussi. Hash SHA-256 source inchangé : `7ac015bebed554d66bf45353c88bb5e706a6481a3f1f2c09d40062de1f070e93`.
- `audit-00559432.json`, `audit-00609706.json`, `audit-00660037.json` : résultats du tableau. Les types terminaux sont inférés de la formule de récompense ; une configuration sans bonus distinguable regroupe les terminaux. Bruit local fixé à seed 987 pour les cibles non terminales, sans modifier le RNG d'apprentissage.
- Une mesure hors jeu de la sonde de 2 048 transitions plus terminaux prend **34,83 ms sur un thread CPU**. Ce n'est pas une mesure de latence du contrôleur en jeu.
- Versions de la vérification : Python 3.13.9, PyTorch 2.14.0+cpu, SB3 2.9.0, Gymnasium 1.3.0, NumPy 2.5.3. Aucune dépendance ajoutée.

Sauvegarde préalable du code, tests et documents : `runs/j4/backup/critic-fixes-20261001-134923/manifest.json`. Empreintes des fichiers livrés et des preuves : `runs/diagnostics/20261001-corrections/manifest.json`. Aucun checkpoint de référence, ancien replay, plugin ou réglage système n'a été remplacé. Index du code actualisé ; les documents et scripts exclus du graphe ont été vérifiés directement.

## Prochaine validation

L'utilisateur lance le nouveau run et contrôle son évolution selon le [guide J4](../GUIDE-J4.md#v4--correction-du-critique-et-observations-v2-j4-15). Examiner ensemble erreurs TD terminales, MSE uniforme, arrivées, progression et incidents. Les sondes fixes sont des diagnostics du replay, pas des données de validation indépendantes ; un pic isolé de loss ne suffit pas à conclure.

Le prochain point à établir est une stabilité durable sur la nouvelle configuration, suivie de courses complètes avec politique figée. Le budget initial de 100 000 transitions peut révéler un problème, mais ne démontre pas à lui seul une convergence ni une absence de divergence ultérieure. Les commandes de lancement, suivi, arrêt, audit et reprise sont prêtes ; conformément à D37, aucun entraînement long n'est lancé par l'agent.

## Complément — premier run utilisateur v4, 100 000 transitions

L'utilisateur a lancé `runs/j4/a01-v4-obs2b` le 1er octobre 2026. Le premier nom `a01-v4-obs2` avait créé un dossier avant le contrôle de la map ; A01 n'était pas chargée (`map=''`, `game_state=32`) et aucune commande de conduite n'a été envoyée. Ce dossier ne contient ni statut ni checkpoint ; il est préservé. Le run `a01-v4-obs2b` a ensuite terminé son budget de 100 000 transitions, avec 137 arrivées sur 163 épisodes (18 abandons, 8 limites de temps), 0 transition invalide et 0 reset échoué. L'incident `init_from` confirme la source `00660037`, 27 entrées, replay neuf, `learning_starts=2000` et `use_loaded_policy=true`. Le learner a réalisé 48 986 updates pour 49 000 visés, sans attente expirée.

Les 50 derniers épisodes sont tous des arrivées ; leur chrono médian en entraînement est 27,7 s. Le meilleur chrono d'entraînement, 27,25 s, a été produit par la politique stochastique à ×10 ; il ne vaut pas chrono officiel ni preuve de performance d'une politique figée. Le dernier checkpoint complet est `00100000` ; les checkpoints `00025479`, `00051538` et `00077054` restent disponibles.

La `train/critic_loss` atteint ponctuellement 1,202 mais termine à 0,071 ; médiane des dix derniers enregistrements 0,077. La sonde fixe uniforme finit à MSE 0,120 contre 0,153 au départ. La sonde fixe de deux abandons finit à MSE 12,59 contre 104,25 au checkpoint 25 479 ; son erreur TD maximale passe de 10,70 à 4,41. Sur **tous** les abandons du replay, la MSE passe de 48,43 (9 cas à 25 479) à 27,33 (18 cas à 100 000). Les populations diffèrent : un nouvel abandon du replay final atteint encore 18,00 d'erreur TD, contre 10,70 maximum au premier checkpoint. L'échantillon uniforme de 10 000 transitions passe de MSE 0,248 à 0,082. Aucun indicateur ne montre une divergence persistante sur ce premier budget, mais certains échecs restent mal évalués.

Preuves : `runs/j4/a01-v4-obs2b/{status.json,episodes.jsonl,incidents.jsonl,sb3/progress.csv,checkpoints/}` et `runs/diagnostics/20261001-corrections/audit-v4-{00025479,00100000}.json`. Audits hors jeu, seed d'échantillonnage 123, 10 000 transitions uniformes et tous les terminaux de chaque replay. Les sondes fixes sont conservées dans les deux checkpoints. La prochaine preuve requise est l'évaluation de politiques figées à ×1 depuis le départ normal, puis l'observation d'une période d'entraînement plus longue si l'utilisateur la lance. Ne pas attribuer toute l'amélioration à un seul changement : source, schéma, replay et optimiseurs ont changé ensemble.

## Complément — évaluation figée utilisateur à ×1

Le même checkpoint `00100000`, politique déterministe figée, a été évalué depuis le départ normal sur 20 tentatives en mode temps réel à ×1 avec le pont 0.4.2 : **19 arrivées sur 20**, meilleur temps **27,01 s**, médiane des arrivées **27,04 s** (écart-type 36,59 ms). Temps de décision médian 1,167 ms, maximum 4,029 ms. La sixième tentative est une **erreur technique**, pas un abandon du pilote : `state: stale or skipped: tick delta 110 != 50` après 110 ms de course. La transition a été invalidée. Les 19 autres tentatives ont toutes terminé ; le taux complet reste 19/20 = 95 %, sans retirer l'erreur du dénominateur.

80 frontières ont été tardives sur 10 273 transitions, soit 0,78 % ; le retard maximal enregistré parmi les transitions acceptées est 50 ms. Ces mesures ne prouvent pas la cause du saut de 110 ms (ordonnancement, pont ou jeu). Il ne faut pas augmenter silencieusement la tolérance de l'environnement : une transition plus longue change la durée de l'action et le calcul de l'actualisation. La transition incorrecte reste invalide selon le contrat existant.

Preuve : `runs/j4/a01-v4-obs2b/evals/20261001-161426-00100000-realtime-x1/` (`eval_summary.json`, `eval_episodes.jsonl`, `eval_transitions.jsonl`). `official_finish_mode=false`, aucun écran d'arrivée normal observé, `comparable_to_leaderboard=false`. Ces chronos sont ceux du jeu via le pont, mais **pas des records officiels vérifiés**. Le prochain contrôle D28 est une arrivée en mode `--official-finish` suivie de la vérification du record dans le jeu. Une seule campagne de 20 tentatives ne démontre pas la stabilité à long terme ni un rang mondial.

## Complément — arrivée de la politique apprise en mode officiel

L'utilisateur a lancé `eval --run runs/j4/a01-v4-obs2b --episodes 1 --mode realtime --speed 1 --official-finish` sur le checkpoint figé `00100000`. L'épisode 900001 se termine par `finished` à **27 080 ms**, en 541 actions valides, sans erreur ; le pont 0.4.2 observe l'écran normal de fin (`normal_finish_dialogs_observed=1`). Temps médian de décision 1,263 ms ; 5 frontières tardives, retard maximal accepté 10 ms. L'évaluation est complète pour l'unique épisode demandé.

Preuve : `runs/j4/a01-v4-obs2b/evals/20261001-163341-00100000-realtime-x1/` (`eval_summary.json`, `eval_episodes.jsonl`, `eval_transitions.jsonl`). Cette fois, l'arrivée d'une **politique apprise** en mode officiel est démontrée, contrairement à la sonde historique du contrôleur scripté. Le résumé conserve correctement `comparable_to_leaderboard=false`. L'écran normal confirme que le pont n'a pas empêché la fin de simulation ; il ne certifie pas qu'un record local, un replay ou un classement a été écrit. Lors de l'inspection en lecture seule, `Scores/steamuser.Scores.Gbx` était daté du 1er octobre 14:05, `Profiles/steamuser.Profile.Gbx` de 16:00 et l'autosave A01 du 29 septembre. Cela ne prouve pas l'absence d'un record en mémoire ou d'une sauvegarde différée. La vérification du temps affiché par le jeu reste ouverte ; aucun rang ou chrono officiel persistant n'est annoncé.
