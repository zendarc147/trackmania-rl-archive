# J5 — Terminer A01 régulièrement (2 octobre 2026)

## Résultat

**J5 validé selon le protocole préenregistré.** Le checkpoint figé `runs/j4/a01-v4-obs2b/checkpoints/00100000` (SAC hybride, observations v2, récompense v2) satisfait D33 dans deux campagnes indépendantes de 20 tentatives à ×1 en temps réel, depuis le départ normal :

| Campagne | Arrivées | Meilleur | Médiane | Écart-type | Échecs |
| --- | ---: | ---: | ---: | ---: | --- |
| B (sélection) | 20/20 | 26,98 s | 27,05 s | 56 ms | aucun |
| B confirmation | 19/20 | 26,97 s | 27,07 s | 42 ms | 1 erreur technique |
| B cumulé | 39/40 (97,5 %) | 26,97 s | 27,06 s | 50 ms | 1 erreur technique |

Ces chronos sont les `RaceTime` du jeu à l'arrivée confirmée par `RaceFinished` et 3/3 checkpoints. Ils ne sont **pas** des records officiels vérifiés (`comparable_to_leaderboard=false`) ; aucun rang n'est annoncé. J6 demande encore le relevé daté D30.

## Protocole fixé avant la campagne

`runs/j5/protocol.json`, écrit à 03:53:27 +09:00, avant le lancement de la première campagne (03:53:35). Le protocole fixe :

- 20 tentatives par politique, `eval --mode realtime --speed 1`, politique déterministe figée et départ normal remis à zéro par l'environnement ;
- critère D33 : au moins 18 arrivées sur 20. Abandons, limites de temps et erreurs techniques restent au dénominateur ;
- trois candidats : A = v3 `00660037` (source avant corrections J4-15), B = v4 `00100000`, C = v4 `best-027110ms-02432296` ;
- règle de sélection : le candidat qui respecte D33 avec la médiane la plus basse ;
- confirmation : le candidat retenu est rechargé depuis le disque, puis évalué dans une seconde campagne de 20 tentatives ;
- gel : SHA-256 de `model.zip`, `trainer_state.json`, du profil de map et de la normalisation avant et après. `runs/j5/hashes-before.txt` et `hashes-after.txt` sont **identiques**.

## Comparaison contrôlée

Même évaluateur, même map, même pont 0.4.2, même vitesse, même nombre d'essais. Seul le checkpoint figé change.

| Candidat | Arrivées | Meilleur | Médiane | Écart-type | Échecs |
| --- | ---: | ---: | ---: | ---: | --- |
| A v3 `00660037` | 6/20 (30 %) | 28,36 s | 28,44 s | 41 ms | 11 abandons, 3 limites de temps |
| **B v4 `00100000`** | **20/20** | **26,98 s** | **27,05 s** | 56 ms | aucun |
| C v4 `best-027110ms-02432296` | 19/20 (95 %) | 26,26 s | 28,96 s | 990 ms | 1 abandon à 97,9 % |

- **A** : les 14 échecs restent au départ (progression ≤ 0,2 %). La politique déterministe n'accélère pas (`accelerate=false` sur 123 à 179 des 200 premières actions) et la voiture s'arrête. A échoue au critère D33.
- **C** : distribution bimodale avec 3 courses vers 26,3 s et 16 vers 28,8–29,2 s. Il respecte D33, mais sa médiane est plus lente de 1,9 s. C'est le meilleur chrono isolé observé (26,26 s) ; il n'est pas retenu selon la règle préenregistrée.
- **B est retenu.** La comparaison A/B justifie de conserver la branche v4, avec les corrections J4-15 et la poursuite de l'entraînement. A et B diffèrent par plusieurs facteurs : schéma v2, warmup corrigé, replay neuf et 100 000 transitions supplémentaires. Elle ne permet donc pas d'attribuer le gain à un facteur isolé. Ce n'est pas une ablation d'entraînement à plusieurs seeds, et D25 reste ouvert en J4.

## Échecs et incidents

- Confirmation, tentative 540001 : `state: stale or skipped: tick delta 150 != 50` à la première action. Transition invalidée par l'environnement et commandes relâchées, puis épisode suivant normal. Comptée comme échec. Même famille que l'incident de 110 ms de l'évaluation J4-15. Cause non isolée (ordonnancement, pont ou jeu).
- Frontières tardives : 21 sur 10 829 transitions dans la campagne B, 186 sur 10 255 dans la confirmation. Retard maximal accepté : 50 ms. Décision médiane : 1,09 et 1,27 ms ; maximum : 2,4 et 5,4 ms.
- Aucun essai n'est retiré des statistiques.

## Preuves

| Campagne | Artefacts (`eval_summary.json`, `eval_episodes.jsonl`, `eval_transitions.jsonl`) | Log |
| --- | --- | --- |
| B | `runs/j4/a01-v4-obs2b/evals/20261002-035335-00100000-realtime-x1/` | `runs/j5/campaign-B.log` |
| A | `runs/j4/20260930-204802-a01_sac_hybrid4_v3_h095/evals/20261002-040256-00660037-realtime-x1/` | `runs/j5/campaign-A.log` |
| C | `runs/j4/a01-v4-obs2b/evals/20261002-041006-best-027110ms-02432296-realtime-x1/` | `runs/j5/campaign-C.log` |
| B confirmation | `runs/j4/a01-v4-obs2b/evals/20261002-131751-00100000-realtime-x1/` | `runs/j5/campaign-B-confirm.log` |

Commande (épisodes de départ 510001, 520001, 530001, 540001) :

```bash
uv run python scripts/tm.py eval --run <run> --checkpoint <ck> --episodes 20 --mode realtime --speed 1 --first-episode <n>
```

Empreinte du modèle retenu : `model.zip` `c8a38247d423f8f47b4c819b8075b6978499dea7dba6d89a8888f6d7308ab453`, `trainer_state.json` `7cb15ab176cd37ace2e2488be04e063cbfa93376576b683dd37f09b33701a76e`. Aucun code, pont, observation, récompense ou modèle n'a été modifié. Aucun entraînement n'a été lancé.

## Limites et suite

- L'arrivée en mode `--official-finish` de ce checkpoint (27,08 s, écran normal) date de J4-15. Elle n'a pas été rejouée ici et ne figure pas dans la statistique D33. La persistance d'un record dans le jeu n'est pas vérifiée.
- La meilleure arrivée observée de C (26,26 s) montre qu'une trajectoire plus rapide existe dans la branche v4. La rendre régulière relève de J6 et J7.
- Prochain blocage J6 : relevé daté du seuil top 1 000 (D30) et conditions comparables (D34). Le replay TMX de 23,77 s noté en J4-16 reste un ancrage de récompense, pas ce relevé.
