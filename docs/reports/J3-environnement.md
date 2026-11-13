# Rapport J3 — Environnement et récompense testables

Date : 2026-09-29, de 15:37 à ~16:05 +09:00. Machine : laptop local, Python 3.13.9, uv 0.9.5, bibliothèque standard uniquement.
Statut : **J3 atteint** pour ses critères, sous réserve des limites du §8. Le pont 0.1.0 ne relançait pas la course après une arrivée (§6) ; levé par le pont 0.2.1 (§6 bis). Aucun entraînement n'a été lancé. Les épisodes réels sont pilotés par des **contrôleurs de test scriptés, non appris** ; leurs transitions ne sont ni des données d'apprentissage ni une preuve de performance.

## 1. Livrables

| Fichier | Rôle |
| --- | --- |
| `src/trackmania_rl/env.py` | `TrackmaniaEnv` : contrat de reset et de transition sur le pont en mode synchrone, statuts, invalidation (`trackmania_rl.env/1`). Sans bibliothèque RL. |
| `src/trackmania_rl/reward.py` | Récompense v1 décomposée et versionnée (`trackmania_rl.reward/1`), retour actualisé, contrôle de calibration. |
| `src/trackmania_rl/scripted_controllers.py` | Contrôleurs de test **non appris** (`LEARNED = False`) : `idle_v1`, `full_gas_straight_v1`, `reference_pursuit_v1`. |
| `configs/maps/a01.json` | Section `episode` ajoutée : limite 54 220 ms et abandon après 5 000 ms sans progrès (D27). Seul endroit où ces valeurs d'A01 figurent. |
| `tests/test_env.py` | 24 tests hors jeu, **fixtures entièrement synthétiques** (`SyntheticGame` : voiture 1-D inventée, format de messages du pont). |
| `scripts/j3_reward_sensitivity.py` | Rejeu hors jeu des épisodes réels J3 sous plusieurs variantes de récompense (§4). |
| `scripts/j3_live_env.py` | Épisodes réels courts, par scénario ; écrit `runs/j3/<horodatage>-env/{trace.jsonl, transitions.jsonl, summary.json}`. |
| `docs/EXPERIMENTS.md` §7 | Fiche J3-ENV-01 (test d'intégration réel, pas une expérience RL). |
| `runs/j3/` (non suivi par Git) | Traces, transitions marquées `data_kind = real_scripted_test`, `learning_data = false`. 3,9 Mio. |

Préservés, empreintes inchangées : `TelemetrieVoiture.as` (`d414cd34…`), `telemetrie.py`, `main.py`, `plugins/TrackmaniaRLBridge.as` (`b821d44a…`, identique à la copie installée), `bridge.py`, `protocol.py`, `geometry.py`, `observation.py`, `reference.py`. Plugin installé non modifié (permission : NON) ; aucun fichier du dossier `Plugins` modifié après 15:37.

## 2. Commandes exécutées

```text
PYTHONPATH=src:tests uv run python -m unittest discover -s tests       # Ran 51 tests … OK
uv run python scripts/j3_live_env.py --map configs/maps/a01.json pursuit
    # 15:52 → runs/j3/20260929-155217-env : arrivée 30,12 s
uv run python scripts/j3_live_env.py --map configs/maps/a01.json --first-episode 311 idle
    # 15:53 → runs/j3/20260929-155315-env : abandon à 5,15 s
uv run python scripts/j3_live_env.py --map configs/maps/a01.json --first-episode 321 \
    --pursuit-episodes 2 pursuit truncate stall disconnect
    # 15:53 → runs/j3/20260929-155330-env : arrivée 30,47 s, puis reset impossible (§6)
uv run python scripts/j3_live_env.py --map configs/maps/a01.json --first-episode 331 \
    truncate stall disconnect
    # 15:57, après relance manuelle par l'utilisateur → runs/j3/20260929-155711-env
uv run python scripts/j3_reward_sensitivity.py --map configs/maps/a01.json
    # 16:02 → runs/j3/20260929-160244-reward-sensitivity.json (hors jeu)
```

`runs/j3/20260929-155254-env` : lancement refusé par le script, rien envoyé (jeu sur l'écran de fin). `runs/j3/20260929-reset-probe` : sonde `R 390` depuis l'écran de fin (§6).

Contrôle hors jeu préalable du contrôleur `reference_pursuit_v1` sur la course humaine réelle J2 : signe de la direction calculée identique à celui de l'humain sur 1 039 échantillons où les deux dépassent |0,3|. Ce contrôle vérifie seulement la convention de signe.

## 3. Contrat de reset et de transition

**Reset** (`env.reset()`) : `REL`, purge des messages en attente, `R <épisode>` (→ `GiveUp()` dans le plugin), attente de l'état `start`. Refus (`BridgeError`, épisode non prêt) si l'UID diffère, si `race_ms ≠ 0`, si les checkpoints ou le drapeau d'arrivée ne sont pas remis à zéro, ou si la projection ou l'encodage échoue. Un reset **ne produit jamais de transition** : il rend la première observation d'un nouvel épisode, avec un nouvel identifiant.

**Transition** (`env.step(action)`) : état source s (tick t₀) → action maintenue `action_ticks = 5` pas (50 ms, D26) → état s' du même épisode et du même `action_id`, avec :

- `boundary` : `tick = t₀ + 50` exactement et `Δrace = Δtick` ;
- `finish` : 0 < Δtick ≤ 50, 0 ≤ Δrace ≤ Δtick, `RaceFinished` vrai et 3/3 checkpoints ;
- `seq` croissant, UID attendu, compteur de checkpoints jamais décroissant ni supérieur à la cible ;
- observation v1 encodée avec le tick attendu (règle de péremption J2).

Chaque `Transition` porte `obs`, `next_obs`, action, `reward`, composantes, `terminated`, `truncated`, `discount`, `dt_ms`, `race_ms`, statut et diagnostics (Progress, écarts, relocalisation, latence).

**Statuts**

| Statut | Condition | Traitement |
| --- | --- | --- |
| `finished` | `RaceFinished` et tous les checkpoints, confirmés par le jeu | terminal, bonus d'arrivée, `discount = 0` |
| `abandoned` | maximum de Progress de l'épisode non dépassé de 1 cm pendant 5 s simulées (D27) | terminal (échec), `discount = 0`, `REL` |
| `time_limit` | `race_ms ≥ time_limit_ms` (D27) | **troncature** : `truncated`, `discount = γ^dt`, l'apprenant bootstrappe ; `REL` |
| `running` | aucun des cas précédents | — |
| `error` | transport, délai, relâchement par le jeu, action refusée, état périmé ou incohérent, erreur de projection ou d'observation | `valid = False`, `reward = None`, `next_obs = None`, `REL`, épisode arrêté ; `step()` interdit jusqu'au prochain `reset()` |

Priorité : arrivée, puis abandon, puis limite de temps.

## 4. Récompense v1 (`trackmania_rl.reward/1`, hash `7db1d3d8…88f3`)

Par transition de durée dt (s) :

- γ_dt = 0,98^dt ; même actualisation par seconde quelle que soit la cadence ;
- Φ(s) = 100 × Progress(s), et Φ(état terminal) = 0 ;
- progression = γ_dt·Φ(s') − Φ(s) ;
- temps = −1,0 × dt ;
- arrivée = +150 si le jeu confirme l'arrivée valide ;
- total = somme des trois.

Avec Φ(terminal) = 0, la progression télescope à −Φ(s₀) sur tout épisode terminé. Elle ne peut donc pas être accumulée par boucles ou par abandon. Il reste comme objectif le coût du temps et le bonus d'arrivée. Aucune composante ne lit le contact, la glisse, la direction, l'écart latéral ou la vitesse.

Calibration pour A01 (`check_calibration`) : le bonus doit dépasser 84,3 pour qu'une arrivée à la limite de 54,22 s reste préférable à un abandon en 5 s ; 150 laisse une marge de 65,7. La valeur initiale de 100 **échouait** ce test (bonus minimal 100,87 avec l'horizon de 60 s de la fixture) : elle a été relevée avant tout essai en jeu. Coefficients : **proposition** J3, non approuvée.

Mesure sur épisodes réels (retour actualisé depuis s₀) :

| Épisode (contrôleur) | Statut | Progression | Temps | Arrivée | Retour actualisé |
| --- | --- | --- | --- | --- | --- |
| 301 (pursuit) | finished 30,12 s | −26,53 | −30,13 | +150 | **59,08** |
| 321 (pursuit) | finished 30,47 s | −27,00 | −30,48 | +150 | **58,31** |
| 311 (idle) | abandoned 5,15 s | −0,0002 | −5,15 | 0 | **−4,89** |
| 331 (full gas, limite 3 s de test) | time_limit 3,00 s | +2,66 | −3,00 | 0 | −0,35, sans valeur terminale |

La course la plus rapide obtient le retour le plus élevé ; l'abandon rapporte moins. Retour de progression actualisé, recalculé depuis `transitions.jsonl` : −0,0000 pour les deux arrivées et 0,0000 pour l'abandon. Le télescopage est vérifié sur données réelles. Les sommes non actualisées de progression (−26,5) proviennent de l'actualisation par pas, pas d'une fuite.

À la transition d'arrivée, le terme de progression vaut −Φ(s) ≈ −100 : l'apprenant voit donc un gain net d'environ +50 sur ce pas. Un abandon perd le même Φ(s). La différence entre arrivée et abandon, depuis n'importe quel état, se réduit au bonus et au coût du temps.

### Justification des valeurs proposées

| Paramètre | Valeur | Raison | Test |
| --- | --- | --- | --- |
| Φ(terminal) | 0 | Seule convention qui rend la progression neutre sur un épisode terminé (théorème de mise en forme par potentiel, Ng et al. 1999, appliqué avec le γ réel de chaque pas). Avec Φ(terminal) = Φ(s'), un abandon garderait la progression acquise, et l'arrêt deviendrait une façon d'encaisser le potentiel. | `test_shaping_telescopes_…` ; réel : retour de progression = 0 |
| Limite de temps | troncature, `discount = γ_dt` | La limite est administrative (D27), pas un échec de conduite : REWARDS §2 interdit de la traiter comme terminale. L'apprenant bootstrappe V(s'), qui contient Φ de façon cohérente. | `test_time_limit_…` ; réel : épisode 331 |
| Abandon (5 s sans progrès) | terminal | Règle de fin de conduite de D27 ; comme Φ(terminal) = 0, il ne rapporte que −coût du temps. | `test_early_abandon_…`, `test_prolonged_immobility_…` |
| Actualisation | 0,98 par seconde | Horizon effectif 1/(−ln 0,98) ≈ 49,5 s, du même ordre que la limite de 54,22 s : l'arrivée reste visible depuis le départ. Défini par seconde, donc invariant à la cadence (γ par pas de 50 ms = 0,99899). 0,95 par seconde exigerait un bonus minimal de 223,9. | `test_cadence_change_…`, sensibilité ci-dessous |
| Coût du temps | 1,0 par seconde simulée | Donne l'objectif chrono : pour une arrivée au temps T, B·γ^T − (1 − γ^T)/k décroît strictement avec T, quel que soit B ≥ 0. Une échelle de 1 par seconde laisse les retours dans quelques dizaines d'unités. | `test_faster_valid_run_is_preferred` ; réel : 59,08 > 58,31 |
| Bonus d'arrivée | 150 | Au-dessus du minimum 84,3 pour A01 (arrivée à la limite préférée à un abandon en 5 s), avec 78 % de marge. 100 passe pour A01 (minimum 84,3), mais échouait la fixture à 60 s (100,87). | `check_calibration`, `test_early_abandon_…` |
| Échelle de Φ | 100 | Signal dense : à 70 m/s, un pas de 50 ms avance d'environ 0,16 unité, plus que le coût de 0,05 par pas. L'échelle ne change pas le retour d'un épisode terminé depuis s₀. | Sensibilité : retours identiques avec 10 |

Sensibilité (`scripts/j3_reward_sensitivity.py`, artefact `runs/j3/20260929-160244-reward-sensitivity.json`), sur les trois épisodes réels terminés sans erreur, rejoués hors jeu :

| Variante | Arrivée 30,12 s | Abandon | Arrivée 30,47 s | Ordre conservé | Calibration A01 |
| --- | --- | --- | --- | --- | --- |
| v1 proposée | 59,08 | −4,89 | 58,31 | oui | oui (min 84,3) |
| bonus 100 | 31,86 | −4,89 | 31,28 | oui | oui (min 84,3) |
| discount 0,95/s | 16,67 | −4,53 | 16,03 | oui | **non** (min 223,9) |
| discount 0,99/s | 84,84 | −5,02 | 84,19 | oui | oui (min 63,7) |
| discount 1,0 | 119,87 | −5,15 | 119,52 | oui | oui (min 49,2) |
| échelle Φ 10 | 59,08 | −4,89 | 58,31 | oui | oui |
| coût du temps 0,1/s | 79,40 | −0,49 | 78,81 | oui | oui (min 8,4) |

Le rejeu de v1 reproduit exactement les retours enregistrés en jeu. Toutes les variantes conservent l'ordre « arrivée rapide > arrivée lente > abandon » ; seule la variante à 0,95 par seconde échoue la calibration. Il s'agit de trois épisodes d'un contrôleur scripté : cela ne prédit pas la dynamique d'apprentissage. Le choix final reste une décision J4 et, si besoin, une comparaison contrôlée.

## 5. Tests anti-exploitation (REWARDS §5)

`tests/test_env.py`, fixtures synthétiques ; les confirmations réelles du §4 et du §6 sont indiquées entre parenthèses.

| Cas | Test | Résultat |
| --- | --- | --- |
| Deux courses valides : la plus rapide préférée | `test_faster_valid_run_is_preferred` | OK (réel : 59,08 > 58,31) |
| Aller-retour sans gain | `test_back_and_forth_gives_no_exploitable_gain` | OK : retour < 0 et < course directe ; cycle avant/arrière ≤ 0 |
| Oscillation autour d'un checkpoint | `test_oscillating_around_a_checkpoint_pays_nothing_repeatedly` | OK, aucun bonus |
| Croisement : pas d'avancement fictif | `test_crossing_projection_cannot_jump_to_a_future_portion`, `test_relocalization_is_bounded_by_the_game_checkpoint_sector` | OK (A01 sans croisement) |
| Checkpoint manqué : pas d'arrivée | `test_missed_checkpoint_gives_no_valid_finish` | OK, y compris drapeau d'arrivée sans 3/3 → `error` |
| Reset non récompensé | `test_reset_is_never_a_rewarded_transition` | OK (réel : `action_id` repart à 1, Progress près de 0) |
| Abandon ≤ réussite lente | `test_early_abandon_never_beats_a_slow_admissible_finish` + calibration | OK |
| Immobilité sans gain | `test_prolonged_immobility_does_not_pay` | OK (réel : épisode 311) |
| Pas de pénalité de contact ni de glisse | `test_contacts_and_sliding_are_never_penalized` | OK : récompenses identiques, observations différentes |
| Changement de cadence | `test_cadence_change_keeps_time_cost_and_per_second_discount` | OK : 5 et 10 ticks, même coût du temps, γ par seconde |
| Déconnexion : transition rejetée | `test_disconnect_rejects_the_transition`, `test_technical_errors_…` | OK (réel : §6) |
| Limite temporelle explicite | `test_time_limit_status_and_future_value_are_explicit`, `test_time_limit_is_truncation_not_terminal` | OK (réel : épisode 331) |

Tests de contrat en plus : reset, usage interdit, chaînage `obs`/`next_obs`, et 9 incidents injectés (silence, relâchement, état périmé, NaN, UID, recul du compteur, fausse arrivée, mauvais `action_id`, déconnexion), chacun suivi d'une reprise par reset.

Total : `Ran 51 tests … OK` (7 J1, 20 J2, 24 J3).

## 6. Intégration réelle

Mode synchrone (`CFG 1 1000 0`), vitesse ×1, départ normal par `GiveUp`, A01 ouverte par l'utilisateur.

- **Transitions** : 603 + 610 transitions d'arrivée, 103 d'abandon, 60 de troncature, toutes valides. `dt` = 50 ms, sauf la dernière transition des arrivées (30 ms : l'arrivée tombe au milieu du maintien, état `finish`). Chaînage `next_obs = obs` suivant vérifié, compteur de checkpoints monotone.
- **Arrivée** : checkpoints 1, 2, 3 puis événement `finish` (`race_time_ms = 30120`), `RaceFinished`, relâchement `finish` par le plugin. Chronos du jeu 30,12 s et 30,47 s : chronos d'un contrôleur de test scripté, **pas une performance**.
- **Latence** (envoi de l'action → état suivant, 50 ms simulées) : médiane 49,2 à 49,5 ms, p95 53,4 à 55,4 ms, maximum 64,9 ms.
- **Retard du client** (épisode 332) : le client attend 1,5 s avant l'action 21, au-delà du délai de 1 000 ms. Le plugin émet `released/action_timeout` avec la simulation gelée au tick 1 000. L'environnement renvoie `status = error`, `reward = None`, `next_obs = None` et envoie `REL`. L'épisode suivant (333) repart par reset : 10 transitions valides.
- **Déconnexion** (épisode 334) : action de 25 ticks (direction −1, accélération), puis socket fermée sans `REL`, au milieu du maintien. Après reconnexion, sur 61 états : `commanded = [0,0,0]`, `car_inputs = [0,0,0]`, `armed = false`. L'épisode 335 repart : 10 transitions valides. Cette déconnexion est provoquée en dehors de `env.step()` ; l'invalidation par l'environnement est couverte hors jeu.
- **Reset après une arrivée : échec observé.** Après l'arrivée de l'épisode 321, `R 322` émet `reset_requested`. Le jeu passe ensuite à l'écran de fin (`game_state = 1024`, `in_race = false`) au lieu de relancer. Aucun état `start` n'arrive. L'environnement lève `BridgeError: reset failed: timeout` et relâche les commandes. La sonde `R 390` depuis l'écran de fin ne produit rien non plus. L'utilisateur a relancé la course à la main. L'arrivée est donc détectée proprement, mais **l'enchaînement automatique après une arrivée n'est pas possible avec le pont 0.1.0**. Le reset fonctionne après un abandon, une troncature ou un incident (épisodes 311→321, 331→335).
- **Tracker (J2-09, proposition)** sur les épisodes réels : 0 relocalisation ; distance maximale à la ligne 22,8 m (seuil de relocalisation 40 m) ; Δs maximal par transition de 50 ms : 5,43 m, pour une fenêtre de 280 × 0,05 + 8 = 22 m. Les seuils n'ont jamais été déclenchés, ce qui ne les valide pas. La marge de secteur (15 m) n'a pas été sollicitée.
- **Normalisation v1** sur 1 213 observations réelles du contrôleur : valeurs au clip ±5 pour `velocity_car.x` (157), `velocity_car.y` (57), `angular_velocity_car.z` (31), `centerline_vertical` (28). La distribution d'un contrôleur diffère de la conduite humaine (J2 §9).

## 6 bis. Correctif du reset après arrivée (pont 0.2.1)

Modification du plugin autorisée par l'utilisateur le 2026-09-29 (≈16:05). Sauvegardes : `runs/j3b/backup/` (pont 0.1.0 `b821d44a…`, `builtin.txt` inchangé). `TelemetrieVoiture.as` non modifié.

- **Cause** : après une arrivée, `GiveUp()` est ignoré ; ~3 s plus tard le jeu ouvre l'écran de fin (`LocalRaceEndDialog`, 1024), où `OnRunStep` ne tourne plus.
- **Essai 0.2.0** (`runs/j3/20260929-161157-env`) : rembobinage `RewindToState` vers l'état du compte à rebours (sauvegardé par `SaveState()` au premier tick négatif). L'épisode 402 démarre, mais l'écran de fin s'ouvre quand même 2,4 s après (`released/left_race`). Insuffisant.
- **Pont 0.2.1** : l'arrivée contrôlée est traitée dans `OnCheckpointCountChanged` (état `finish`, relâchement), puis `PreventSimulationFinish()` (API 2.2.1, procédé utilisé par Linesight). `R` après arrivée rembobine vers le compte à rebours sauvegardé (`method = rewind_start`) ; `CFG <sync> <timeout> <stream> 1` active `auto_restart` (rembobinage immédiat). `R` hors course renvoie `method = none_not_in_race` : le client échoue aussitôt au lieu d'attendre 15 s.
- **Preuve** : `uv run python scripts/j3_live_env.py --map configs/maps/a01.json --first-episode 411 --pursuit-episodes 3 pursuit` → `runs/j3/20260929-162527-env` : épisodes 411, 412, 413 `finished` à 30,47 s, 610 transitions valides chacun, aucune intervention. Chemins couverts : `R` après arrivée (411→412, `rewind_start`) et auto_restart (412→413, `rewound/auto_restart` puis `GiveUp`). Après la fin du script : `in_race = true`, commandes et `car_inputs` à 0.
- **Déterminisme** : trois retours identiques (58,3177) ; la simulation depuis l'état sauvegardé est reproductible pour un contrôleur déterministe.
- **Limites** : une course contrôlée terminée n'est plus validée par le jeu (pas de chrono officiel, pas de replay). L'évaluation finale (D28) devra désactiver ce mécanisme. Le rembobinage dépend d'un état sauvegardé sur la même map (UID vérifié) ; sans lui, `rewind_failed`. Tests hors jeu : `Ran 54 tests … OK` (3 nouveaux tests de protocole synthétiques).

## 7. Données invalides et neutralisation

- Une transition `error` n'a ni récompense ni observation suivante. Le script l'enregistre marquée `valid = false` : un apprenant doit l'exclure. Toutes les transitions J3 portent `learning_data = false`.
- Commandes neutralisées : `REL` à chaque reset, erreur, abandon et troncature ; relâchement par le plugin à l'arrivée, au délai et à la déconnexion (constaté en jeu, §6).
- Messages d'un épisode précédent purgés au reset ; les événements `released` ou `action_rejected` d'un autre épisode sont ignorés.

## 8. Limites

- **Reset après arrivée** impossible avec le pont 0.1.0 (§6) ; levé par le pont 0.2.1 (§6 bis).
- Coefficients de récompense (100 / 1,0 / 150 / 0,98 par seconde) : proposition calibrée par un calcul et par des tests, non approuvée et non comparée en apprentissage.
- `abandoned` est traité comme terminal (D27 : « traitement de l'abandon à tester en J3 »). Il est testé ici contre l'exploitation, pas comparé à une troncature en apprentissage.
- Seuils du tracker (J2-09) : mesurés sans déclenchement, toujours à l'état de proposition. Aucun croisement réel sur A01.
- La troncature réelle a utilisé une limite de test de 3 s. La limite de 54,22 s n'a pas été atteinte en jeu.
- Sortie de course, désactivation du plugin et arrêt du jeu pendant le contrôle : non testés.
- Un seul contrôleur géométrique, qui roule plein gaz ; pas d'exploration des murs ni des chutes.

## 9. Budget

- Mission : 15:37 à ~16:05, environ 28 min sur 2 h.
- Jeu sous contrôle : 15:52 à 15:57, environ 6 min sur 30, dont une relance manuelle par l'utilisateur.
- Traces : 3,9 Mio sur 500 Mio dans `runs/j3/`.
- Aucun assistant, aucune dépense, aucun processus laissé actif, aucune modification du plugin installé.

## 10. Prochain blocage

Reset après arrivée résolu (§6 bis). Reste l'approbation des coefficients de récompense v1. Ensuite, J4 selon ses propres dépendances : framework SAC, mesure du débit (D22) et budget chiffré (D23).
