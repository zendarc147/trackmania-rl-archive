# Rapport J1 — Intégration TMInterface sous Linux

Date : 2026-09-29, de 13:24 à 14:05 +09:00. Machine : laptop local (Ryzen AI 7 350, 30 Gio de RAM), Python 3.13.9, uv 0.9.5.
Statut : **J1 atteint pour la boucle de contrôle**, avec des limites listées au §8. Aucun entraînement n'a été lancé.

## 1. Installation et versions réelles

Titre de la fenêtre du jeu en cours d'exécution : `TrackMania Modded Forever (2.12.0) [default]: TMInterface (2.2.1), CoreMod (1.0.11)`.

- **Lancement réellement utilisé :** TMLoader (Steam, appid non-Steam `3393753619`, Proton Hotfix). Il lance `TmForever.exe` 2.12.0 depuis sa base `database/TmForever/products/TmForever/2.12.0`. Le profil TMLoader `default` active le mod `TMInterface`.
- **TMInterface chargé :** 2.2.1. Les versions 2.1.0 à 2.2.1 sont présentes dans la base.
- **Dossier TMInterface :** `compatdata/11020/.../Documents/TMInterface`, avec un lien symbolique depuis le préfixe `3393753619`.
- **Map :** A01-Race. UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, remonté par `GetCurrentChallenge().Uid`. SHA-256 du fichier de campagne : `f0a87080…25dc3`.
- **API consultée :** https://donadigo.com/tminterface/plugins/api/all et `/plugins/callbacks`, relues le 2026-09-29. Aucun champ n'a été supposé : le premier chargement a échoué à la compilation (`const array<int>@`), puis a été corrigé.

Incident : `steam -applaunch 11020` a lancé une deuxième instance Proton non moddée. L'instance moddée tournait déjà. La nouvelle instance a été arrêtée en moins d'une minute, avant toute commande. L'instance moddée n'a pas été touchée.

## 2. Livrables

| Fichier | Rôle |
| --- | --- |
| `plugins/TrackmaniaRLBridge.as` | Pont J1 : serveur TCP local `127.0.0.1:8479`, états JSON, commandes, reset, watchdog |
| `src/trackmania_rl/bridge.py` | Client Python (stdlib) : connexion, association état/action, erreurs |
| `src/trackmania_rl/protocol.py` | Existant, inchangé : validation et encodage des actions |
| `tests/test_bridge.py` | Tests synthétiques du client avec un faux serveur, sans valeur d'intégration |
| `scripts/j1_live_probe.py` | Sonde en jeu : contrôleur de test en boucle ouverte, pas une politique |
| `runs/j1/<horodatage>/` | Traces `trace.jsonl`, `summary.json`, `control_rows.json` (1,1 Mio au total) |
| `runs/j1/backup/` | Copie de `builtin.txt` et empreintes relevées avant installation |

Installation : `TrackmaniaRLBridge.as` a été copié dans `Documents/TMInterface/Plugins`. TMInterface a ajouté lui-même `set "plugin_trackmaniarlbridge_enabled" true;` à `builtin.txt` ; c'est la seule différence avec la sauvegarde. `TelemetrieVoiture.as` reste identique (SHA-256 `d414cd34…aff3`), ainsi que `telemetrie.py` et `main.py`. Aucun binaire ni mod n'a été modifié.

## 3. Commandes exécutées

```text
PYTHONPATH=src uv run python -m unittest discover -s tests      # 7 tests OK
uv run python scripts/j1_live_probe.py hello ping               # runs/j1/20260929-134341
uv run python scripts/j1_live_probe.py hello control            # runs/j1/20260929-135449
uv run python scripts/j1_live_probe.py timeout disconnect async # runs/j1/20260929-135525
uv run python scripts/j1_live_probe.py midhold                  # runs/j1/20260929-135600
uv run python scripts/j1_live_probe.py stream --seconds 60      # runs/j1/20260929-135642 (conduite humaine)
```

## 4. Observations : sources et conventions constatées

Le pas physique vaut 10 ms : `TickTime` et `RaceTime` avancent par multiples de 10 dans `OnRunStep`.

| Libellé demandé | Champ du pont | Source TMInterface | Constat en jeu |
| --- | --- | --- | --- |
| Velocity X/Y/Z | `velocity` | `Dyna.CurrentState.LinearSpeed` | Repère monde, m/s. À 8,37 m/s en local, `DisplaySpeed` vaut 30 km/h, soit 30,1 km/h. |
| (repère voiture) | `local_velocity` | `SceneVehicleCar.CurrentLocalSpeed` | Composante z vers l'avant, en m/s. Diagnostic, non ajouté au modèle. |
| Rotation X/Y/Z | `rotation_ypr`, `rotation_matrix`, `quat_wxyz` | `Location.Rotation.GetYawPitchRoll`, `Quat` | Radians. Au départ d'A01 : lacet 1,5708 et quaternion (0,707 ; 0 ; 0,707 ; 0). Discontinuités non traitées ; encodage renvoyé à J2. |
| Angular Velocity X/Y/Z | `angular_velocity` | `Dyna.CurrentState.AngularSpeed` | Probablement en rad/s dans le repère monde. En virage à droite, la composante y < 0 et le lacet diminue. Le repère reste à confirmer en J2. |
| Gear | `gear` | `CarEngine.Gear` | Valeurs observées : 0, 1 et 2 ; 0 à l'arrêt après freinage. `RearGear` est conservé en diagnostic. |
| Turning Rate | `turning_rate` | `SceneVehicleCar.TurningRate` | Normalisé dans [−1, 1]. Il rejoint la commande en quelques pas mais la suit avec retard, par exemple −0,30 alors que la commande vaut −1,0. C'est donc un état de direction lissé, distinct de l'input. |
| Centerline Lateral / Vertical | — | — | **Indisponible en J1**, faute de référence ; prévu en J2. `position` est fourni pour ce calcul. |
| Progress | — | — | **Indisponible en J1**, faute de référence ; prévu en J2. `checkpoints` ne le remplace pas. |
| Wheels Contact 1–4 | `wheel_contact` | `Wheels[i].RTState.HasGroundContact` | Valeur individuelle par roue. Sous forte accélération : `[F, F, T, T]`, avant délesté. |
| Wheels Sliding 1–4 | `wheel_sliding` | `Wheels[i].RTState.IsSliding` | Valeur individuelle par roue, vraie sous freinage. `IsSliding` global conservé à part. |

**Ordre des roues** vérifié par identité des objets (`wheels[i] is wheels.FrontLeft`, etc.) : `FL, FR, BR, BL`. Offsets relevés dans le repère voiture :

- FL = (+0,86 ; 0,35 ; +1,78) ;
- BR = (−0,885 ; 0,35 ; −1,21).

La voiture a donc +z vers l'avant et +x à gauche. Le sens de x reste à reconfirmer en J2 avec un cas connu.

Diagnostics non destinés au modèle : `rpm`, `display_speed`, `position`, `car_inputs`, `inputs`, `commanded`, `game_state`, `checkpoint_states`, `map_uid`. Aucun ajout au modèle n'est proposé ici.

## 5. Actions

Commande envoyée : `SetInputState(Steer, −65536..65536)`, `Up` et `Down` binaires, gauche et droite forcés à 0. Les commandes sont réappliquées à chaque pas physique pendant la durée demandée.

| Essai (run 135449) | Commande | Retour du jeu (`car.Input*`) | Effet |
| --- | --- | --- | --- |
| Direction 0,5 | `32768` | `InputSteer` = 0,5 | Le lacet passe de 1,569 à 1,269 rad en 0,5 s. |
| Direction −1 | `−65536` | −1,0 | Rotation en sens inverse (ω_y > 0). |
| Rampe −1 à +1 par 0,25 | 9 valeurs | −1 ; −0,75 ; … ; +1, identiques à la commande | La direction progressive est bien appliquée. |
| Accélération | Up = 1 | `InputGas` = 1,0 | 0 à 88 km/h en 1,5 s ; passage en rapport 2. |
| Roue libre | 0 / 0 | 0 / 0 | Décélération douce : 140 à 119 km/h. |
| Accélération et frein simultanés | 1 / 1 | Gas 1, Brake 1 | Décélération : 119 à 89 km/h ; glisse sur les quatre roues. |
| Frein | Down = 1 | `InputBrake` = 1,0 | 89 à 14 km/h en 1 s. |

Accélération et frein sont **binaires** dans TMNF. La documentation de la commande `gas` l'indique, et le retour 0/1 a été observé. La direction est **analogique** sur 65 536 pas par côté. La plage étendue n'est pas utilisée.

## 6. Synchronisation, cadence et latence

**Mode synchrone** (`CFG 1 …`). À la fin de chaque maintien de N pas, le plugin envoie un état `boundary`. Il attend ensuite dans `OnRunStep` l'action suivante, simulation bloquée, jusqu'au délai fixé.

- Contrôle, 99 pas de 5 ticks : chaque état suivant avance d'exactement **50 ms de simulation** (`tick_deltas = [50]`). `seq` augmente de 1 à chaque pas. `action_id` correspond à l'action et `applied_tick_ms` vaut le tick de l'état précédent.
- **La simulation reste gelée pendant l'attente.** Lors du test de délai, le tick reste à 50 pendant 299 ms murales, puis le plugin relâche les commandes (`action_timeout`).
- Latence murale, de l'envoi de l'action à la réception de l'état suivant : médiane 49,7 ms, p95 55,2 ms, maximum 56,5 ms. Ce temps correspond aux 50 ms simulées en vitesse 1 ; le surcoût du pont est faible.
- Aller-retour transport (`PING`, traité à chaque image) : médiane 4,4 ms, p95 8,1 ms.

**Mode temps réel** (`CFG 0 …`, run 135525, 60 pas). Le jeu n'attend pas. Écarts réels entre états : 50 ms dans 55 cas et **60 ms dans 5 cas**. L'action a été appliquée 0, 5 ou 10 ms après l'état source. Le mode temps réel fait donc varier la durée des actions ; le mode synchrone l'évite.

Temps de simulation (`tick_ms`, `race_ms`) et temps mural (`wall_ms` du jeu, `_rx_mono` côté client) restent distincts dans chaque message.

Stratégie retenue en proposition : mode synchrone pour l'entraînement. Le mode temps réel reste à mesurer pour l'évaluation finale ; la contrainte d'évaluation en temps réel est rappelée en ARCHITECTURE §4.

## 7. Checkpoints, arrivée, reset, arrêt et déconnexion

- **Reset** : la commande `R <épisode>` relâche les commandes puis appelle `SimulationManager.GiveUp()`. Le plugin renvoie le premier état à `race_ms = 0` après le compte à rebours négatif. Mesure : 0,55 s mural en vitesse 1, avec `countdown_speed = 5`.
- **Checkpoints et arrivée** (run 135642, conduite humaine, pont passif) : callbacks `OnCheckpointCountChanged` reçus. A01 compte `target = 3`, arrivée incluse :
  - CP1 à 16,53 s ;
  - CP2 à 21,08 s ;
  - arrivée à 25,89 s, avec `RaceFinished = true`, l'événement `finish` et `checkpoint_states = [1,1,1]`.

  L'état de jeu passe ensuite à 1024 (`LocalRaceEndDialog`), puis revient à 512 au redémarrage. Le compteur est remis à 0 après le reset. Ce chrono est humain et ne sert pas de référence de performance.
- **Hors course** : `in_race = false` et `game_state = 32` (`Menus`) ont été observés dans le menu. Les actions sont alors refusées avec `action_rejected/not_in_race`.
- **Relâchement des commandes** :
  - délai d'action dépassé en mode synchrone : relâchement à 299 ms, puis commandes et `car.Input*` à 0 ;
  - socket coupée sans `REL`, en mode synchrone et en mode temps réel : après reconnexion, commandes à `[0,0,0]` et `armed = false` ;
  - coupure au milieu d'un maintien de 25 ticks, direction à fond et accélération : commandes à 0 dès le premier état observé à 60 ms, puis sur les 60 états suivants ;
  - `REL` explicite : événement `released/client_request` ;
  - sortie de course et désactivation du plugin : `Release` est appelé dans `OnGameStateChanged` et `OnDisabled`. Ces deux chemins ne sont **pas testés en jeu**.
- Côté Python, un relâchement par le jeu, un refus, un délai dépassé ou une coupure lève `BridgeError`. La transition est alors invalide ; les tests synthétiques de `tests/test_bridge.py` le couvrent.

## 8. Limites et points ouverts

- La commande `map` de TMInterface, appelée par `MAP Campaigns\…\A01-Race.Challenge.Gbx` ou avec le seul nom du fichier, n'a pas chargé A01. L'utilisateur a ouvert la map depuis le menu. Le chargement automatique de la map reste ouvert.
- Le rattachement d'un client unique remplace la connexion précédente. Une connexion morte est détectée par l'échec d'écriture, grâce au heartbeat de 500 ms.
- En mode synchrone, l'attente bloque aussi le rendu. Un client lent gèle donc l'image jusqu'au délai (1 s par défaut dans la sonde).
- Repère de `angular_velocity`, sens de l'axe x, discontinuités d'orientation : à valider en J2 sur des cas connus.
- Vitesse de simulation supérieure à 1 et plusieurs instances : non testées. P10 reste ouverte.
- Plage de valeurs de `gear` : valeurs observées seulement, marche arrière non testée.
- Arrêt du jeu pendant le contrôle : non testé, le jeu étant l'instance de l'utilisateur.
- Tests Python : `PYTHONPATH=src` est nécessaire, car le projet uv ne déclare pas de backend de build. Ce point n'a pas été modifié.

## 9. Budget consommé

- Mission : 13:24 à ~14:05, environ 41 min sur 2 h.
- Jeu ouvert sous contrôle ou en essais : 13:42 à 13:57, environ 15 min sur 20.
- Traces : 1,1 Mio sur 250 Mio.
- Aucun assistant, aucune dépense, aucun processus laissé actif. Le plugin reste installé, conformément à la permission accordée.

## 10. Prochain blocage

J2 : enregistrer une référence A01 complète pour calculer `Centerline Lateral/Vertical Distance` et `Progress`. Il faut aussi valider les repères restants. Ce passage demande l'accord de l'utilisateur.
