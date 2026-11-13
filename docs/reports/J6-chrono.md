# J6 — Chrono comparable au top 1 000 (2 octobre 2026)

## Résultat

**J6 non validé.** Le seuil est relevé et daté. Aucun chrono local ne passe sous ce seuil. Le meilleur pilote figé reste `a01-v4-obs2b/00100000` (J5) : meilleur temps 26,97 s, médiane 27,06 s. Il manque environ **2,7 s**. L'entraînement J6 a été interrompu par un redémarrage de la machine.

## Relevé D30 (critère 1 — validé)

Relevé le 2026-10-02 à 13:32:59 +09:00. Artefacts : `runs/j6/survey/` (`leaderboard_summary.json`, pages brutes `page*.json`, `track.json`, `dedi.html`, `SHA256SUMS`).

- Source : API TMX `tmnf.exchange`, `/api/replays?trackId=2233`, toutes les pages. 5 007 replays, 2 673 joueurs classés (`Position`, rang par joueur).
- Map : TMX 2233 `A01-Race`, UID `BeySZdnfuSh4nHY5xztiXLmlrXe` (identique au profil `configs/maps/a01.json`), Stadium, Nadeo, temps auteur 24,54 s.
- Catégorie : campagne Nations A01, classement des replays hors ligne TMX. Le dépôt sur TMX exige le Competition Patch.
- Seuils :

| Rang | Joueur | Temps | Date du replay |
| --- | --- | ---: | --- |
| 1 | Axell | 23,77 s | 2025-09-16 |
| 50 | Icer | 23,93 s | 2026-02-18 |
| 1 000 | Zhongli_TM | 24,23 s | 2022-02-23 |
| 1 001 | geertjepeertje | 24,23 s | 2022-04-02 |

- Règle retenue : il faut un temps **strictement inférieur à 24,23 s** pour revendiquer le top 1 000, car les rangs 1 000 et 1 001 sont à égalité. Pour le top 50, il faut moins de 23,93 s.
- Dedimania (`dedi.html`) : environ 30 records par mode pour cet UID, avec un meilleur TAttack à 23,81 s. Ce classement ne descend pas jusqu'au rang 1 000. Le seuil est donc pris sur TMX.

## Conditions comparables (critère 2 — non coché)

Le protocole J5 respecte D34 : ×1 en temps réel, TMNF 2.12.0 non modifié (chemin du processus), départ normal et temps `RaceTime` du jeu. Les runs passent toutefois par TMInterface, sans Competition Patch. Ils ne sont pas recevables sur TMX. La comparaison reste locale. Ce critère sera coché avec la campagne qui le prouvera, pas avant.

## Entraînement J6

- Configuration : `configs/training/a01_sac_hybrid4_v6_lap_fromB.json`. Elle reprend la récompense v3 et la configuration `v5_lap`. Seul le point de départ change : checkpoint B `a01-v4-obs2b/00100000`. Le replay est neuf ; les observations v2 et le pont 0.4.2 sont inchangés.
- Run `runs/j4/j6-v6-lap-B` (log `runs/j6/train-v6-lap-B.log`) : lancé à 13:38, dernier état à 14:36. Machine redémarrée à 14:40 (`last -x reboot`).
- Résultat partiel : 525 387 transitions, 908 épisodes, 843 arrivées. Meilleur temps d'entraînement : 26,98 s (`best-026980ms-00245769`). Médiane par tranche de 100 épisodes : 27,95 à 28,65 s. **Aucun progrès mesurable vers 24,23 s.** Le dernier checkpoint est `00505542`.
- Le checkpoint B n'a pas été modifié : SHA-256 dans `runs/j6/hashes-B-before.txt`, identiques à ceux de J5.

- Reprise automatique à 15:07:32, après la réouverture d'A01 par l'utilisateur. Relevé à 15:29 : 674 499 transitions. Sur les tranches de 100 épisodes depuis 506 k transitions : 100 arrivées sur 100 à chaque tranche ; meilleurs temps 27,29, 27,08 et 27,18 s ; médianes de 27,96 à 28,04 s. **Plateau confirmé** : le run est fiable mais pas plus rapide.

## Diagnostic du pilote B (épisode 510001, 27,04 s)

- Environ 5 s de vol sur 27 s : la descente de 8,3 à 10,2 s, puis la montée de 21,9 à 25,0 s. Le freinage observé a lieu surtout en l'air.
- La direction oscille fortement sur les lignes droites (±0,8 d'une action à l'autre). L'effet sur la vitesse n'est pas mesuré.
- De 0,25 à 0,40 de progression, la vitesse reste bloquée vers 315 km/h, en 4e rapport, dans le grand virage.
- Vitesse moyenne le long de la référence : 297 km/h. Il en faut au moins 331 km/h pour passer sous 24,23 s.

## Analyse des replays TMX (D39) et essais du 2 octobre après-midi

Replays dans `runs/j6/replays/` (rangs 1, 2, 3, 11, 50, 501, 999). Analyse : `analyze.py`, `profile.py`, `crest.py`. Les ghosts sont relus avec `uv run --no-project --with pygbx`.

- Temps de passage du top (23,77 s) comparés à B (27,04 s) : -0,41 s à 15 % de progression, -0,36 s à 25 %, -1,46 s à 50 %, -2,11 s à 70 %, -3,26 s à l'arrivée.
- Le top garde l'accélérateur enfoncé toute la course, sauf 100 ms à 7,78 s. Il donne trois coups de frein (10, 10 et 80 ms) à 12,34 s, 15,21 s et 19,61 s, à l'entrée des grands virages et de la montée.
- Sur le plat après la descente (26 à 43 %), le top accélère de 356 à 425 km/h. B reste vers 315 km/h, braque presque à fond (-0,9 à -0,98) et relâche les gaz sur 25 à 33 % des actions.
- Attention : les vitesses des ghosts sont en 3D, alors que `display_speed` ne compte pas la chute verticale. On ne compare donc que les sections plates.

Diagnostics sur B (politique figée et manœuvre scriptée, synchrone ×10 ; pas un pilote) : `scripts/j6_lift_probe.py` et `scripts/j6_crest_probe.py`, sorties dans `runs/j6/lift_probe/` et `runs/j6/crest_probe/`.

- 34 relâchés vers 7,8 s : 27,01 à 27,13 s, aucun gain.
- 45 manœuvres à la crête (relâché × braquage) : le vol est plus bas (hauteur max 0,2 m au lieu de 3,4 m), mais l'atterrissage est plus lent et le chrono ne s'améliore pas.
- Sans frein : 27,00 s. Avec la direction lissée : 27,01 à 27,13 s. Gaz toujours enfoncés : sortie de piste.
- 36 coups de frein et braquages à l'entrée du virage à 35 % : aucun gain.
- Conclusion : B est un optimum local. Une perturbation isolée ne le rapproche pas du style du top.

Runs J6 :

| Run | Changement | Transitions | Meilleur | Médiane finale | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `j6-v6-lap-B` | récompense v3 depuis B | 683 k | 26,98 s | ~28,0 s | plateau |
| `j6-v7-lap-B-d099` | actualisation 0,99/s | 23 k | — | — | arrêté (jeu hors course) |
| `j6-v8b-obs3-bursts` | obs v3 + rafales d'exploration | 256 k | 28,07 s | ~30,5 s | régression |
| `j6-v9-obs3` | obs v3 depuis B | 846 k | 26,86 s | ~27,7 s | gain puis plateau |
| `j6-v10-obs3-scratch` | obs v3 depuis zéro, récompense v2 (0,905/s), lr 3e-4 | 3 814 k | 26,12 s (entraînement) | ~27,3 s | **déterministe 24,84 s** (`03172239`) |

Contrôles déterministes de v10 (synchrone ×10, 1 course, `runs/j6/j6-v10-obs3-scratch-det.jsonl`) : 25,33 s à 0,97 M transitions ; 25,29 ; 24,94 ; 25,09 ; 25,17 ; 25,03 ; 24,89 ; **24,84 s à 3,17 M** ; 24,94 ; 24,88 s à 3,75 M. Plateau vers 24,85–24,95 s. Ces contrôles synchrones à ×10 sont des diagnostics : ils ne remplacent pas l'évaluation D28/D33 à ×1 en temps réel. Le jeu s'est fermé le 3 octobre vers 15:30, à 3,81 M transitions.
Suite : `a01_sac_hybrid4_v11_obs3_lap_from_v10`, qui affine `03172239` avec la récompense v3 (replay neuf, lr 1e-4). Empreintes du checkpoint de départ : `runs/j6/hashes-v10-03172239.txt`.

## Rampe finale : diagnostic du 4 octobre et correctif v12

Constat de l'utilisateur : v11 (`j6-v11-obs3-lap`, 4,85 M transitions) stagne vers 25,1 s. La voiture est en avance au pied de la grande rampe, puis le record en sort beaucoup plus vite.

**Mesure.** Politique figée `04849183`, 25,14 s, comparée au replay TMX de 23,77 s :

- à 0,70 de progression (avant la rampe) : 18,74 s contre 18,4 s, soit 0,34 s de retard ;
- de 0,70 à l'arrivée : 6,40 s contre 5,37 s, soit **1,03 s perdue sur la rampe, le vol et la plateforme** ;
- vitesse au décollage (0,775) : 412 km/h contre environ 491 km/h pour le record. Sur la rampe, la voiture perd 89 km/h, le record 34 km/h.

**Ce que fait la politique sur la rampe** (`eval_transitions.jsonl` de l'évaluation ×1 du 4 octobre à 15:36) : elle relâche les gaz sur 5 à 7 pas de 50 ms au pied de la rampe, puis freine en l'air pendant 0,75 s après le décollage. Elle freine encore sur la plateforme avant la ligne. Tous les checkpoints v10 et v11 évalués relâchent les gaz 3 à 7 fois sur la rampe ; le défaut précède donc la récompense v3.

**Sondes** (`scripts/j6_ramp_probe.py`, synchrone ×10, politique figée, actions remplacées par fenêtre de progression ; diagnostic, pas un pilote ; `runs/j6/ramp_probe/`) :

| Fenêtre gaz forcé, sans frein | Décollage | Passage 0,92 | Arrivée |
| --- | ---: | ---: | --- |
| aucune (politique) | 407 km/h | 23,30 s | 25,14 s |
| 0,70–0,78 (rampe) | 461–469 km/h | 23,10 s | 25,14 s |
| 0,70–0,92 (rampe + vol) | 467 km/h | **22,90 s** | abandon après l'atterrissage |
| 0,70–0,95 | 467 km/h | 22,90 s | 29,98 s (choc, puis reprise) |
| 0,70–1,0 | 469 km/h | 22,90 s | abandon à 0,979 (voiture arrêtée, lat −9 m) |
| 0,775–0,92 (vol seulement) | 410 km/h | 23,30 s | 25,11 s |
| 0,90–1,0 (plateforme) | 411 km/h | 23,30 s | 25,06 s |

- Les relâchés sur la rampe coûtent 55 à 60 km/h au décollage. Le braquage n'est pas en cause : le limiter à ±0,2–0,6 sans forcer les gaz ralentit la course (25,41 à 25,48 s).
- **Le frein agit en l'air** dans TMNF. Avec le même état au décollage, 0,3 s de frein en vol fait perdre 11 m en 1,2 s.
- Gaz plein sur la rampe et en vol : 0,40 s gagnée à 0,92. La politique actuelle n'a jamais connu cet atterrissage plus haut et plus loin, près de l'arche d'arrivée : elle s'y écrase. Gaz forcé sur la rampe seulement : le gain est reperdu, car le vol suivant est freiné.

**Pourquoi la voiture a appris cela.** Le critique (`runs/j6/ramp_probe/qgap/qgap-04849183.json`) donne au gaz sur la rampe, en vol et sur la plateforme un avantage compris entre −0,8 et +0,4, souvent proche de 0. La tête pédales y est très aléatoire : P(gaz) vaut 0,2 à 0,8 sur la rampe, environ 0,4 en vol, et 0,25 à 0,48 sur la plateforme.

- La cible d'entropie des pédales, 0,3·ln 4 = 0,42 nat, impose environ 10 % de commandes aléatoires en moyenne. Le coefficient α_cmd monte à 0,15 pour la tenir (α_steer ≈ 0,006). Le bonus d'entropie, environ 0,2 par pas, dépasse le coût d'un seul relâché ou d'un seul coup de frein de 50 ms à haute vitesse.
- SAC place donc ce hasard là où une seule commande coûte le moins : la rampe, le vol et la plateforme. Additionnés, ces pas font perdre environ 0,4 s.
- Pendant l'entraînement, ce hasard empêche tout décollage rapide. Le vol 0,775–0,85 le plus court dure 1,50 s (7 épisodes sur 9 044), contre environ 1,45 s à plein gaz. Les vols rapides donnent pourtant de meilleurs chronos : médiane 26,17 s contre 26,74 s. Le critique n'a jamais vu d'atterrissage rapide.
- Un vol rapide mal posé finit en abandon, payé très cher par la récompense v3 : environ −60 points contre +4 points pour 0,4 s gagnée. Avec une politique bruitée, le saut court et freiné, posé tôt sur la plateforme, est l'option sûre. C'est un optimum local d'évitement du risque : le chemin sûr appris par un agent bruité, comme dans le problème de la falaise.
- Autre trace dans les données : 113 des 232 échecs d'entraînement v11 (abandons et limites de temps) sont des sorties latérales au décollage (latéral moyen +11,7 m à 0,775, contre +4,8 ± 0,7 m pour les arrivées).

**Correctif (D41, proposition).** La cible d'entropie de la tête pédales passe de 0,4159 à 0,1386 nat (0,1·ln 4). Le vol représente environ 20 % des pas, et la cible peut y être atteinte sans hasard au sol. La récompense, les observations et la ligne de référence ne changent pas, aucune action n'est forcée et aucune constante d'A01 n'est ajoutée. Correction de code associée : `init_from` rechargeait les cibles d'entropie du checkpoint et ignorait celles de la configuration. Il applique maintenant la configuration (`training.py`, test `test_init_from_applies_config_entropy_targets`, 145 tests hors jeu OK).

- `a01_sac_hybrid4_v12_obs3_lap_lowcmd` : poursuite de v11 depuis `04849183`, même récompense v3, même actualisation et même lr, replay de 1 M conservé. **Un seul changement** : la cible d'entropie des pédales.
- `a01_sac_hybrid4_v12s_obs3_scratch_lowcmd` : réglages de v10 (récompense v2, 0,905/s, lr 3e-4) depuis zéro. Même changement unique, pour une comparaison contrôlée avec v10.
- Fumée réelle `runs/j4/j6-v12-smoke` (log `runs/j6/train-j6-v12-smoke.log`) : 6 000 transitions, 11 arrivées sur 11, aucune transition invalide. L'incident `init_from` enregistre la cible `[-0.5, 0.1386]` ; α_cmd passe de 0,257 à 0,187. **Aucun gain de chrono n'est encore démontré.**

**Résultat v12 (4 octobre, run `j6-v12-lowcmd` lancé par l'utilisateur, arrêté à 791 985 transitions) : hypothèse D41 réfutée pour le défaut visé.**

- Entropie des pédales tenue à la cible : 0,13 à 0,16 nat, α_cmd entre 0,02 et 0,05.
- Part des commandes sans gaz inchangée à l'entraînement : environ 17 %.
- Médiane d'entraînement meilleure : 25,6–26,0 s, contre 26,3–26,9 s pour v11.
- Fiabilité d'entraînement plus basse : 1 476 arrivées sur 1 530 épisodes. Nouveaux abandons au pied de la rampe (27 abandons à 0,70 de progression).
- Politique figée `00791985` (sonde ×10) : **25,53 s**, contre 25,14 s pour v11. Décollage à 415 km/h. Frein en vol sur 45 pas sur 64 ; frein sur 9 pas sur 43 sur la plateforme.
- Le freinage en vol est donc un choix appris par la politique, pas un hasard imposé par l'entropie. L'explication par l'évitement du risque tient toujours ; le correctif par l'entropie seule ne suffit pas.
- Sortie de la sonde : `runs/j6/ramp_probe/20261004-190242`.

Critères de lecture de v12 (pour mémoire). La `display_speed` de la sonde n'est pas un repère fiable : en mode synchrone ×10, elle reste figée sur plusieurs pas, et deux sondes du même checkpoint `00791985` ont lu 415 puis 500 km/h. Le repère à suivre est le temps de vol entre 0,775 et 0,92 de progression : 3,25 s pour la politique, 2,90 s à plein gaz. Viser un vol de moins de 3,1 s, sans freinage en vol dans les évaluations figées (`j6_ramp_probe.py --only-base`, ligne « gas: false »), puis chrono déterministe inférieur à 24,84 s, et enfin D28/D33 à ×1.

## v13 : rafales de gaz pendant l'exploration (D42, proposition)

Constat : avec v12, `scripts/j6_jump_stats.py` ne trouve **aucun** vol sans frein sur 1 482 tours d'entraînement. Le critique n'a donc jamais vu un saut rapide ni son atterrissage. Le hasard pas à pas ne peut pas produire environ 90 commandes « gaz » d'affilée (rampe et vol).

Configuration `a01_sac_hybrid4_v13_obs3_lap_gasbursts` : reprise de v11 depuis `04849183`, même récompense v3, même entropie, même lr, replay de 1 M conservé. **Un seul changement**, `exploration.command_bursts`, un mécanisme existant :

- à chaque pas, une rafale démarre avec une probabilité de 0,004 ;
- elle tient « gaz sans frein » pendant 60 à 150 pas ;
- la direction reste celle de la politique ;
- le replay enregistre l'action réellement jouée (SAC est hors politique).

La rafale ne connaît ni la position ni la map, et elle ne sert qu'à la collecte : l'évaluation se fait avec la politique figée, sans rafale. Récompense et observations sont inchangées.

Fumée réelle `runs/j4/j6-v13-smoke2` (16 000 transitions, log `runs/j6/train-j6-v13-smoke2.log`) : 28 arrivées sur 29, aucune transition invalide. 2 tours sur 30 ont la rampe et le vol entièrement à plein gaz, 5 sur 30 ont un vol sans frein. Les deux sauts rapides finissent mal : un abandon, une arrivée en 34,45 s. C'est l'atterrissage que la politique doit apprendre. **Aucun gain n'est démontré.**

À suivre :

- `j6_jump_stats.py` : le taux d'arrivée des vols sans frein doit monter, puis leur médiane passer sous celle des autres tours ;
- la sonde sur un checkpoint figé : vol de 0,775 à 0,92 en moins de 3,1 s (3,25 s pour v11), chrono inférieur à 25,14 s ;
- les médianes d'entraînement sont faussées par les rafales et ne doivent pas servir de critère.

Suivi dans TensorBoard (ajouté le 4 octobre ; actif pour les runs lancés ou repris après ce changement) :

- après chaque checkpoint, l'entraîneur joue **une course déterministe de la politique courante**, synchrone, sans rafale et hors replay ;
- elle apparaît dans `eval/finish_s`, `eval/finished` et `eval/air_brake_share`, et dans `det_evals.jsonl` à la racine du run ;
- pour chaque épisode d'entraînement : `actions/air_brake_share` (part des pas en l'air avec frein), `exploration/burst_steps`, et `episode/finish_s_no_air_brake` ou `episode/finish_s_with_air_brake` (au plus 5 % de pas freinés en l'air pour la première série) ;
- un épisode d'évaluation qui échoue est noté `deterministic_eval_failed` dans les incidents et n'arrête pas le run ;
- tests : `test_train_stop_resume` vérifie `det_evals.jsonl` et les nouveaux champs d'épisode. 145 tests hors jeu passent ;
- ces courses synchrones ×10 sont des diagnostics : elles ne remplacent pas l'évaluation D28/D33 à ×1.

## Blocages et suite

1. **Jeu fermé** par le redémarrage. A01 doit être rouverte depuis le menu par l'utilisateur ; l'agent ne charge pas la map.
2. **Écart de performance.** La v4 plafonne vers 27,1 s depuis environ 2 M transitions, et la première heure du run J6 n'a pas fait mieux. Le levier prévu par D18 (points de parcours à venir) et un diagnostic à partir des replays TMX rapides demandent un accord explicite. Ils n'ont pas été utilisés.
3. Reprise du run, une fois A01 ouverte :

```bash
uv run python scripts/tm.py resume --run runs/j4/j6-v6-lap-B --until-stopped
uv run python scripts/tm.py status --run runs/j4/j6-v6-lap-B
uv run python scripts/tm.py stop --run runs/j4/j6-v6-lap-B
```

Pour évaluer un candidat, appliquer le même protocole que J5 (D28/D33 : 20 tentatives, ×1, au moins 18 arrivées) :

```bash
uv run python scripts/tm.py eval --run runs/j4/j6-v6-lap-B --checkpoint <ck> --episodes 20 --mode realtime --speed 1
```
