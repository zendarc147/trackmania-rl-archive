# Rapport J2 — Référence A01 et observations

Date : 2026-09-29, de 14:04 à ~14:45 +09:00. Machine : laptop local, Python 3.13.9, uv 0.9.5, bibliothèque standard uniquement.
Statut : **J2 atteint**, sous réserve des limites du §9. Le schéma d'observation v1 et sa normalisation restent des **propositions** à approuver avant J3/J4. Aucun entraînement n'a été lancé.

## 1. Livrables

| Fichier | Rôle |
| --- | --- |
| `configs/maps/a01.json` | Profil de map : nom, UID, nombre de checkpoints, fichier et empreinte, chemins et hash des artefacts. Seul endroit où A01 apparaît. |
| `src/trackmania_rl/vec.py` | Vecteurs 3D (stdlib). |
| `src/trackmania_rl/reference.py` | Découpage des tentatives, validation d'une course, référence brute, préparation (schémas `…reference.raw/1` et `…reference.prepared/1`). |
| `src/trackmania_rl/geometry.py` | `ReferenceLine`, `ProgressTracker` : projection par secteur et continuité, Progress, écarts signés (`…geometry/1`). |
| `src/trackmania_rl/observation.py` | Schéma d'observation v1, encodeur, normalisation versionnée (`…observation/1`, `…normalization/1`). |
| `tests/test_geometry.py` | 20 tests hors jeu, **fixtures entièrement synthétiques**. |
| `scripts/j2_record_reference.py` | Enregistreur passif : `CFG 0 1000 1`, aucun input ni reset envoyé. |
| `scripts/j2_convention_probe.py` | Contrôleur de test en boucle ouverte (6,75 s simulées), **pas une politique**. |
| `scripts/j2_build_reference.py` | Construit référence brute/préparée, projection de contrôle, normalisation, figures. |
| `scripts/j2_conventions.py` | Analyse des conventions sur les traces réelles. |
| `data/maps/a01/` | `reference_raw.json` (625 Kio), `reference_prepared.json` (302 Kio), `normalization_v1.json` (4 Kio). |
| `docs/reports/j2/*.svg` | Visualisations (§6). |
| `runs/j2/` (non suivi par Git) | Traces brutes et résumés. |

Préservés, empreintes inchangées : `TelemetrieVoiture.as` (`d414cd34…`), `telemetrie.py`, `main.py`, `plugins/TrackmaniaRLBridge.as`, `bridge.py`, `protocol.py`, `j1_live_probe.py`. Le plugin installé n'a pas été modifié (permission : NON).

## 2. Commandes exécutées

```text
uv run python scripts/j2_record_reference.py --map configs/maps/a01.json --seconds 300 --finishes 2 --tag human
    # 14:13 → runs/j2/20260929-141326-human : REJETÉ (aucune conduite, voir §3)
    # 14:20 → runs/j2/20260929-142031-human : 2 courses valides
uv run python scripts/j2_convention_probe.py            # 14:25 → runs/j2/20260929-142538-conventions
uv run python scripts/j2_build_reference.py --map configs/maps/a01.json \
    --trace runs/j2/20260929-142031-human/trace.jsonl   # → runs/j2/20260929-143521-build
uv run python scripts/j2_conventions.py --map configs/maps/a01.json \
    --human runs/j2/20260929-142031-human/trace.jsonl \
    --probe runs/j2/20260929-142538-conventions/rows.json \
    --prepared data/maps/a01/reference_prepared.json \
    --out runs/j2/20260929-142538-conventions/conventions.json
PYTHONPATH=src uv run python -m unittest discover -s tests   # Ran 27 tests … OK
```

## 3. Enregistrement de la course humaine

Pont passif, état envoyé à chaque pas physique (10 ms). L'utilisateur conduit et redémarre lui-même.

| Tentative | Résultat | Détail |
| --- | --- | --- |
| run 141326 | **Rejetée** | 300 s sans conduite ni redémarrage (voiture immobile, `race_ms` 958 s → 1 258 s). Lancement sans prévenir l'utilisateur ; erreur de procédure corrigée ensuite. |
| run 142031, tentative 0 | **Rejetée** | Fin de la course précédente, sans compte à rebours ni arrivée. |
| run 142031, tentative 1 | **Valide — référence** | 27,11 s ; CP1 17,80 s, CP2 22,36 s, arrivée 27,11 s. 3 273 états. |
| run 142031, tentative 2 | **Valide — course de contrôle** | 24,92 s ; CP1 16,19 s, CP2 20,50 s, arrivée 24,92 s. 2 972 états. |

Critères de `validate_run`, appliqués automatiquement : UID attendu ; compte à rebours observé (départ normal) ; premier état à `race_ms = 0` ; `race_ms` contigu par pas de 10 ms ; aucun saut de position incompatible avec la vitesse (respawn) ; compteur de checkpoints croissant de 1 ; 3/3 atteints ; arrivée confirmée par le jeu (`RaceFinished` dans l'état, et callback `OnCheckpointCountChanged` 3/3 avec `finished = true` au même `race_ms`).

Constats en jeu :

- L'événement `finish` du pont n'est émis qu'une fois par commande `R` (`g_finishReported`). En mode passif il n'apparaît pas ; la confirmation repose sur les deux signaux du jeu ci-dessus. Aucune modification du plugin n'a été nécessaire.
- L'état au `race_ms` du callback montre encore l'ancien compteur ; le suivant, le nouveau. L'échantillon de passage est pris au temps du callback.
- Après l'arrivée, `race_ms` reste figé et `tick_ms` continue ; la référence s'arrête au premier état `finished`.

Chronos humains : ils ne constituent pas une référence de performance.

## 4. Référence brute et préparée

- **Brute** (`reference_raw.json`, schéma `raw/1`) : 2 713 échantillons de `race_ms = 0` à l'arrivée. Chaque échantillon contient `race_ms`, `tick_ms`, position monde, axes voiture `up`/`forward` en monde, quaternion, compteur de checkpoints et `finished`. On y trouve aussi l'UID, la source (trace et index de tentative) et les checkpoints. Hash de contenu : `06cdb0ec…b037`.
- **Préparée** (`reference_prepared.json`, schéma `prepared/1`), paramètres `dedup_min_step_m = 0.05`, `spacing_m = 1.0`, `smoothing = none` :
  - dédoublonnage : 2 693 points conservés sur 2 713. Les échantillons de checkpoint sont toujours conservés ;
  - rééchantillonnage linéaire tous les 1,000 m : 2 229 points. Longueur : 2 228,15 m, contre 2 228,25 m pour la ligne brute ;
  - normales `up` interpolées puis normalisées ;
  - secteurs : [0 ; 1 187,96 ; 1 740,30 ; 2 228,15] m ;
  - écart maximal de la ligne brute à la ligne préparée : **0,167 m**. Aucun lissage, donc aucune coupe à travers un obstacle.
  - Hash de contenu : `940143ce…702e`, raw_sha256 lié.
- Les hash sont calculés sur le JSON canonique sans le champ `sha256`. `load_prepared` et `Encoder` les revérifient au chargement. L'identité et les chemins sont dans `configs/maps/a01.json`.

## 5. Conventions validées sur cas mesurés

| Question | Preuve | Conclusion |
| --- | --- | --- |
| Colonnes de `rotation_matrix` | `‖Rᵀ·velocity − local_velocity‖` sur 5 725 états J2 : médiane 0,026 m/s, p95 0,18, max 4,0 (pics isolés aux chocs ; `CurrentLocalSpeed` n'est vraisemblablement pas échantillonné au même instant). `Rv` au lieu de `Rᵀv` : écarts de dizaines de m/s. `det = 1 ± 2·10⁻⁶` | Colonnes = axes voiture (x, y, z) exprimés en monde ; base orthonormée directe. |
| Sens de l'axe x | Touche gauche (1 090 éch., > 10 m/s, 4 roues au sol) : accélération centripète projetée sur x = **+78,5 m/s²** en médiane, positive dans 99,5 % des cas. Touche droite (271 éch.) : **−24,6 m/s²**, positive dans 7,7 %. Offsets FL x = +0,86, FR x = −0,86. | **+x = gauche**, +y = haut, +z = avant. |
| Direction et lacet | Sonde : `steer = −1` donne ω_y médian +1,58 rad/s et lacet +0,46 rad ; `steer = +1` donne −1,25 rad/s et −0,54 rad. Touche gauche = `InputSteer −1`. | `steer < 0` = gauche ; ω_y > 0 = rotation vers la gauche. |
| Repère d'`angular_velocity` | Différence finie `vee(R(t+10 ms)·R(t)ᵀ)/dt` vs ω mesuré, 2 483 éch. : erreur médiane **0,006 rad/s** en repère monde contre 0,226 rad/s en repère voiture (RMS 0,093 contre 1,084). | ω en **repère monde**, rad/s. L'observation v1 l'exprime en repère voiture par `Rᵀω`. |
| Discontinuités d'orientation | Sur 5 203 pas consécutifs : 2 sauts de lacet de ±π (wrap), 0 changement de signe du quaternion, pas maximal du vecteur avant 0,094. `atan2(F.x, F.z)` diffère du lacet `GetYawPitchRoll` jusqu'à 0,06 rad. | Lacet/tangage/roulis : diagnostic seulement. Encodage retenu : vecteurs avant et haut, continus, sans wrap. |
| Gear | Humain : valeurs 1 à 5. Sonde, marche arrière (62 éch., vitesse avant jusqu'à −20,2 m/s) : `gear = 0`, `rear_gear = 1`. À l'arrêt aussi `gear = 0`. | `Gear` ne distingue pas neutre et marche arrière. `rear_gear` n'est **pas** ajouté (non approuvé) ; le signe de `velocity_car.z` porte déjà l'information. |

## 6. Géométrie, progression et visualisations

Repère local au point projeté q :

- T : tangente du segment ;
- N : `up` de la référence interpolé et orthogonalisé à T ;
- L = N × T, orienté à **gauche**, comme l'axe x de la voiture.

`lateral = (p − q)·L` (> 0 à gauche), `vertical = (p − q)·N` (> 0 au-dessus, selon la normale locale ; valable en pente et en devers). `Progress = s(q) / longueur`, dans [0, 1]. Il peut reculer. Le maximum historique `max_s_m` est conservé à part, uniquement pour le diagnostic.

Recherche du segment :

1. Fenêtre de continuité : ±(280 m/s × dt + 8 m) autour de la projection précédente ; 30 m au départ.
2. Intersection avec le secteur autorisé par le compteur de checkpoints **du jeu**, marge 15 m.
3. Relocalisation dans ce seul secteur si la meilleure distance dépasse 40 m.

Le point globalement le plus proche n'est jamais utilisé. Progress ne peut donc pas franchir un checkpoint non validé par le jeu.

Résultats réels (run `143521-build`) :

| Course | Relocalisations | Pas où s recule > 5 cm | Progress final | s aux checkpoints (m) |
| --- | --- | --- | --- | --- |
| Référence (auto-projection) | 0 | 0 | 1,0 | 1 187,96 / 1 740,30 / 2 227,12 |
| Contrôle, 24,92 s | 0 | 0 | 1,0 | 1 186,77 / 1 740,88 / 2 227,52 |
| Sonde (avant puis marche arrière) | 0 | recul voulu | pic 51,1 m puis **13,0 m** | — |

- Pour la course de contrôle, l'écart latéral va de −19,97 à +12,54 m (p95 |·| 15,9 m) et l'écart vertical de −0,70 à +22,27 m. Le maximum vertical correspond au saut final : 4 roues en l'air, 844 échantillons sans contact.
- Pendant ce saut, s avance une fois de 8,2 m en 10 ms (t = 23,50 s, à 21 m au-dessus de la ligne). La projection glisse le long d'une ligne courbe sous la voiture. Ce n'est pas un respawn, et la progression reste croissante.

Figures :

- [vue de dessus brute vs préparée](j2/reference_top.svg), avec CP et départ ;
- [altitude le long de la référence](j2/reference_altitude.svg) ;
- [distance brut → préparé](j2/raw_vs_prepared_deviation.svg) ;
- [écarts signés de la course de contrôle](j2/control_offsets.svg) ;
- [progression vs temps, contrôle et référence](j2/control_progress.svg).

## 7. Schéma d'observation v1 (proposition)

Ordre du vecteur, 25 valeurs `float` : exactement celui du tableau. Fréquence réelle : un état par pas physique (10 ms) en flux passif ; en mode synchrone, un état `boundary` par action de N pas. Plages observées : deux courses humaines valides (5 207 échantillons, données **réelles humaines**).

| # | Nom interne | Libellé approuvé | Source | Unité, repère | Plage observée | Transformation | Normalisation v1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0–2 | `velocity_car.x/y/z` | Velocity X/Y/Z | `Rᵀ·Dyna.CurrentState.LinearSpeed` | m/s, voiture (x gauche, y haut, z avant) | x −2,3…9,4 ; y −40,6…24,2 ; z 0…139,4 | changement de repère | z-score |
| 3–5 | `rotation_forward.x/y/z` | Rotation X/Y/Z | colonne 2 de `Location.Rotation` | vecteur unitaire, monde | [−1, 1] | matrice → axe avant | identité |
| 6–8 | `rotation_up.x/y/z` | Rotation X/Y/Z | colonne 1 de `Location.Rotation` | vecteur unitaire, monde | y 0,785…1 | matrice → axe haut | identité |
| 9–11 | `angular_velocity_car.x/y/z` | Angular Velocity X/Y/Z | `Rᵀ·Dyna.CurrentState.AngularSpeed` (monde) | rad/s, voiture | x −9,5…3,5 ; y −1,2…1,1 ; z −1,3…6,4 | changement de repère | z-score |
| 12 | `gear` | Gear | `CarEngine.Gear` | entier, 0 = arrêt ou marche arrière | 1…5 | int → float | z-score |
| 13 | `turning_rate` | Turning Rate | `SceneVehicleCar.TurningRate` | [−1, 1], < 0 = gauche | [−1, 1] | aucune | identité |
| 14 | `centerline_lateral` | Centerline Lateral Distance | `ProgressTracker` | m, + gauche | −20,0…12,5 | projection | z-score |
| 15 | `centerline_vertical` | Centerline Vertical Distance | `ProgressTracker` | m, + selon la normale locale | −0,7…22,3 | projection | z-score |
| 16 | `progress` | Progress | `ProgressTracker` | fraction de 2 228,15 m | [0, 1] | s / longueur | identité |
| 17–20 | `wheel_contact.FL/FR/BR/BL` | Wheels Contact 1–4 | `Wheels[i].RTState.HasGroundContact` | 0/1, ordre API FL, FR, BR, BL | {0, 1} | bool → float | identité |
| 21–24 | `wheel_sliding.FL/FR/BR/BL` | Wheels Sliding 1–4 | `Wheels[i].RTState.IsSliding` | 0/1, même ordre | {0, 1} | bool → float | identité |

Règles d'erreur (`ObservationError`, la transition doit être invalidée ; jamais de zéro de remplacement) :

- champ absent, mal typé (par ex. `gear` non entier, liste de roues ≠ 4) ou non fini ;
- projection non finie ;
- état périmé : `tick_ms` différent du tick attendu, passé par l'environnement ;
- UID de map différent ;
- normalisation d'un autre schéma, d'une autre map, dans un autre ordre ou au hash altéré.

Côté projection (`ProjectionError`) : `update` sans `reset`, temps qui recule sans reset, compteur de checkpoints hors bornes, position non finie.

Normalisation `normalization_v1.json` (hash `348e9de2…1ed9`) :

- z-score `(x − moyenne)/écart-type`, puis clip à ±5 ;
- identité pour les grandeurs déjà bornées ;
- `data_kind = real_human`, sources = trace et index des 2 tentatives, UID, hash de la référence préparée.

Sur ces mêmes données, 143 valeurs sur 62 350 atteignent le clip. En majorité : `centerline_vertical` pendant le saut (86), `velocity_car.x` en glisse (67).

L'encodage est déterministe : même état, même projection et même normalisation figée donnent un vecteur identique (test synthétique et échantillon réel). Ne sont pas fournis au modèle : position, rpm, vitesse affichée, `rear_gear`, lacet/tangage/roulis, quaternion, inputs, checkpoints et temps. Ce sont des données internes ou de diagnostic.

## 8. Tests hors jeu (fixtures synthétiques)

`PYTHONPATH=src uv run python -m unittest discover -s tests` → **27 tests OK** (7 J1 + 20 J2). Couverture J2 :

- ligne droite (offsets signés, progression) ;
- virage à gauche (intérieur = gauche) ;
- rampe à 20 % (normale locale ≠ verticale monde) ;
- croisement et passage supérieur (continuité et secteur) ;
- cas où le point le plus proche sauterait de plus de 400 m, sans que le tracker ne saute ;
- saut parabolique ;
- recul (Progress diminue, `max_s_m` séparé) ;
- reset sans report de progression ;
- temps qui recule, `update` sans reset, NaN, compteur hors bornes ;
- conduite jusqu'au bout sans checkpoint validé : Progress plafonné au secteur 0 ;
- validation et rejet de courses (respawn, sans compte à rebours, mauvaise map, sans arrivée), découpage des tentatives, dédoublonnage à l'arrêt ;
- ordre et repères de l'encodage, continuité au wrap de lacet, erreurs d'observation, encodage identique avec normalisation figée, statistiques sans `data_kind`.

Ces tests valident les calculs, pas l'intégration : les preuves réelles sont aux §3 à §6.

## 9. Limites

- Une seule course de référence et une seule course de contrôle, humaines et lentes, sur une seule map. A01 ne comporte aucun croisement réel : ce cas n'est couvert que par des tests synthétiques.
- La normalisation v1 repose sur 5 207 états humains. La distribution d'une politique sera différente ; les statistiques devront être recalculées sur des données réelles et versionnées avant J4. Le clip ±5 sature pendant le saut.
- La relocalisation n'a jamais été déclenchée en conditions réelles. Les seuils (280 m/s, 8 m, 15 m, 40 m) sont des propositions.
- Les secteurs reposent sur la position du passage humain : un raccourci qui franchit un checkpoint loin de la ligne reste accepté, à la marge de 15 m près, avant validation du jeu.
- La projection glisse de 8 m en un pas pendant le saut final ; sans conséquence sur la validité, mais la granularité de Progress en l'air est plus grossière.
- `Gear = 0` ne distingue pas l'arrêt de la marche arrière ; l'ajout de `rear_gear` demanderait une décision.
- Le mode synchrone n'a pas été réexercé en J2 pour l'encodage « à la frontière d'action » : la règle de péremption est testée hors jeu seulement.
- `data/maps/a01/` (~0,9 Mio) n'est pas ignoré par Git, contrairement à `runs/` ; à confirmer.

## 10. Budget

- Mission : 14:04 à ~14:45, environ 41 min sur 2 h.
- Interactions en jeu : 14:12 à 14:26, environ 14 min sur 30. Le jeu reste ouvert par l'utilisateur ; plus aucune interaction après 14:26.
- Traces : 45 Mio dans `runs/j2`, dont 35 Mio pour la tentative rejetée, plus 0,9 Mio dans `data/`, sur 500 Mio.
- Aucun assistant, aucune dépense, aucun processus laissé actif, aucune modification du plugin installé.

## 11. Prochain blocage

Approbation du schéma v1 : repère voiture pour les vecteurs, orientation sous forme de 6 composantes, z-score avec clip ±5. Décision sur `rear_gear`. Ensuite, J3 : contrat de transition en mode synchrone, qui utilise `ProgressTracker` et `Encoder` à chaque état `boundary`.
