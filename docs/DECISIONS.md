# Registre des décisions

## Légende

- **Validé utilisateur** : contrainte issue de la discussion.
- **Proposition** : choix recommandé mais pas encore accepté ou testé.
- **Observé dans les sources locales** : constat statique, pas preuve d'exécution.
- **À vérifier** : information manquante ou capacité non démontrée.

Lorsqu'une décision change, conserver son ancienne justification et ajouter ce qui la remplace. Une expérimentation ne modifie pas tacitement le périmètre produit.

## Décisions validées

| ID | Décision | Conséquence |
| --- | --- | --- |
| D01 | TMNF avec TMInterface sous Linux, sans changement de système | L'intégration Linux constitue un préalable |
| D02 | Jeu et apprentissage initialement sur une même machine ; essais locaux | Pas de service cloud ou jeu en ligne requis |
| D03 | Première map : A01 | Son identité exacte reste à relever |
| D04 | Un pilote spécialisé par map | La généralisation du modèle n'est pas un objectif initial |
| D05 | Procédure d'entraînement réutilisable sur d'autres maps | Séparer profils de map et composants génériques |
| D06 | Décisions pendant la course | Pas de pilote final fondé sur une séquence TAS précalculée |
| D07 | Pas de contrainte de réalisme humain | Pas de pénalités par défaut sur glisse, contacts ou commandes brusques |
| D08 | Observations numériques de la capture, sans images | Suivre le contrat OBSERVATIONS |
| D09 | Direction progressive, accélération, frein | Reset géré par l'environnement, pas par le modèle |
| D10 | Référence humaine ou éventuellement créée via éditeur | Première proposition acceptée : enregistrer une conduite complète |
| D11 | Écarts latéral et vertical signés, avancement géométrique | La référence sert de repère, pas de ligne obligatoire |
| D12 | Ambition top 1 000 puis top 50 mondial, et au-delà | Définir des chronos de référence comparables ; aucune garantie |
| D13 | Recherche sans échéance finale | Chaque mission et chaque expérience restent bornées |
| D14 | Squelette documentaire et skill demandés maintenant | Pas de lancement implicite du développement RL ou des entraînements |
| D15 | Algorithme d'apprentissage : SAC (Soft Actor-Critic), choix de l'utilisateur le 2026-09-29 | Remplace la comparaison PPO/SAC de P02. Direction continue conforme à D09. Framework, traitement de l'accélération et du frein binaires et hyperparamètres restent à décider en J4 |
| D16 | Réseau de départ : petit MLP 2 couches cachées de 256 unités pour l'acteur et les critiques SAC, entrées télémétriques seulement (issu de P01, 2026-09-29) | Toute extension (taille, historique, récurrence) exige une mesure qui la justifie |
| D17 | Récompense de progression par potentiel sur `Progress` (Φ = progression), issu de P06, 2026-09-29 | Tests anti-exploitation de REWARDS §5 obligatoires ; coefficients, discount et traitement terminal restent à fixer en J3 |
| D18 | Pas de points du parcours à venir ni d'historique au départ (issu de P07, 2026-09-29) | Première ablation candidate si un plateau est mesuré, soumise à accord avant ajout aux observations |
| D19 | Pas d'imitation : apprentissage par RL pur, sans préremplissage du replay buffer par la course humaine (P08 rejetée, 2026-09-29) | La référence humaine reste un repère géométrique uniquement |
| D20 | Entraînement en mode synchrone (simulation gelée jusqu'à l'action) et reset par `GiveUp()` contrôlé par l'environnement (J1-06 et J1-07 acceptés, 2026-09-29) | Évaluation finale en temps réel toujours exigée (ARCHITECTURE §4) |
| D21 | Laptop seul pour J4, calcul CPU d'abord (P04 et P05 acceptées, 2026-09-29) | GPU ou serveur seulement après mesure et accord |
| D22 | Mini-mission de mesure du débit (vitesse ×N, K instances) avant J4 (P10 acceptée, 2026-09-29) | Accord distinct avant de lancer plusieurs instances ; vérifier l'identité de la physique en accéléré |
| D23 | Budget exprimé en temps simulé et transitions ; montant fixé après la mesure de débit (P09 acceptée, 2026-09-29) | Aucun entraînement J4 sans budget chiffré approuvé |
| D24 | Aucun outil d'exploration : ni départs intermédiaires ni maps modifiées (P11 rejetée, 2026-09-29) | Entraînement et évaluation depuis le départ normal de la map d'origine |
| D25 | Accélération et frein sous SAC : comparer en J4 le seuillage de sorties continues et une action hybride (P12 acceptée comme expérience, 2026-09-29) | Choix final selon comparaison documentée |
| D26 | Cadence de décision : 50 ms simulées (5 ticks) par action, valeur mesurée en J1 (2026-09-29) | Coût temporel et discount calibrés pour cette cadence ; tout changement crée une nouvelle expérience |
| D27 | Fin d'épisode : limite de temps = 2× le chrono de la course de référence de la map (A01 : 2 × 27,11 s ≈ 54,2 s) ; abandon si `Progress` ne dépasse pas son maximum de l'épisode pendant 5 s simulées (2026-09-29) | Valeurs dans le profil de map, pas dans le code générique. Limite de temps = troncature, pas état terminal ; traitement de l'abandon à tester en J3 |
| D28 | Évaluation : 20 courses complètes par politique figée ; rapporter meilleur temps valide, médiane, dispersion et taux de réussite (2026-09-29) | Échecs gardés au dénominateur. Si la politique déterministe donne des courses identiques, le documenter |
| D29 | Organisation Hermes : un coordinateur et un `/goal` borné par jalon, sans bots permanents (P03 acceptée, 2026-09-29) | Assistants ponctuels seulement pour tâches indépendantes |
| D30 | Source des chronos mondiaux : Dedimania et TMX (tmnf.exchange), relevé daté avant J6 (2026-09-29) | Catégorie, seuils top 1 000 et top 50 relevés à ce moment, sans valeur inventée |
| D31 | Schéma d'observation v1 de J2 approuvé tel quel : 25 valeurs, vitesses linéaire et angulaire en repère voiture, orientation par vecteurs avant et haut, z-score clip ±5 (J2-08, 2026-09-29) | Toute modification crée une nouvelle version de schéma et une nouvelle expérience |
| D32 | ~~Seuils du tracker de progression de J2 approuvés (J2-09, 2026-09-29)~~ — **retirée** le 2026-09-29 par l'utilisateur (contrat J3) : J2-09 reste une proposition, à mesurer en J3 | Les seuils restent des valeurs par défaut de `geometry.DEFAULT_PARAMS`, non validées ; mesures de J3 dans le rapport J3 |
| D33 | Fiabilité minimale : au moins 90 % de courses terminées sur les 20 d'une évaluation (D28), en plus du meilleur chrono (2026-09-29) | S'applique aux paliers J5 et J6 |
| D34 | Conditions comparables : évaluation à vitesse ×1, physique normale, TMNF 2.12.0 non modifié, départ normal ; catégorie TMNF Nations/United standard (2026-09-29) | L'entraînement accéléré reste permis s'il ne sert pas au chrono comparé |
| D35 | `rear_gear` n'est pas ajouté aux observations du modèle (J2-10, 2026-09-29) | Reste un diagnostic dans l'état brut. Le signe de `velocity_car.z` porte déjà la marche arrière ; tout ajout futur exige une nouvelle version de schéma |
| D36 | Autorisation permanente de modifier le pont `plugins/TrackmaniaRLBridge.as` et sa copie installée dans `Documents/TMInterface/Plugins` lorsque c'est nécessaire (utilisateur, 2026-09-29) | Remplace le « Plugin installé : NON » des contrats J2 et J3. Conditions : sauvegarder la version précédente et `builtin.txt` sous `runs/` ; incrémenter `BRIDGE_VERSION` ; garder copie du dépôt et copie installée identiques (SHA-256 relevé) ; tests hors jeu passés ; rapport de la modification et de sa preuve en jeu. Ne couvre pas `TelemetrieVoiture.as`, les autres plugins, les binaires, les mods ni les réglages TMInterface ; lancer le jeu ou prendre ses commandes exige toujours l'accord de la session |
| D37 | Les entraînements réels sont lancés, suivis et arrêtés par l'utilisateur, pas par l'agent pendant un `/goal` (utilisateur, 2026-09-29) | Le goal livre l'outillage : commandes CLI documentées, configurations, tableau de bord (TensorBoard ou équivalent, éventuellement petit site local), logs et artefacts faciles à récupérer. L'agent peut lancer de courts essais de fumée pour prouver que l'outillage fonctionne. Il ne lance pas de longue collecte en attendant le résultat. Le rapport final dit quoi lancer, comment suivre, arrêter, reprendre et récupérer les données. L'analyse des runs de l'utilisateur fait l'objet d'une mission suivante |
| D38 | Schéma d'observation v3 = v2 + 6 points de la ligne de référence devant la voiture (10, 25, 50, 100, 150 et 200 m), exprimés dans le repère voiture et divisés par la distance. Ajout approuvé par l'utilisateur le 2026-10-02 (« la obs v3 ») | Extension D18 après le plateau mesuré. Géométrie du parcours seulement. Migration v2 → v3 explicite (`observation_v3`) : nouvelles colonnes à zéro, replay et optimiseurs neufs. v1 et v2 restent inchangés |
| D39 | Replays TMX publics téléchargés pour le diagnostic J6 (utilisateur, 2026-10-02 : « et aussi les replay ») | Lus hors projet avec `uv run --no-project --with pygbx`. Aucune imitation (D19 inchangée), aucun ajout au replay ni au modèle |
| D40 | Pendant J6, l'agent lance et arrête lui-même les entraînements (utilisateur, 2026-10-02 : « ne me demande pas l'autorisation pour lancer des entrainement ») | Remplace D37 pour la durée de J6. Chaque run garde configuration, logs et checkpoints |
| D41 | **Rejetée** le 2026-10-04 après le run `j6-v12-lowcmd` : politique figée à 25,53 s contre 25,14 s, frein en vol conservé. Proposition initiale : cible d'entropie de la tête pédales SAC hybride abaissée de 0,3·ln 4 (0,4159 nat) à 0,1·ln 4 (0,1386 nat) pour les runs v12 | Motif mesuré sur la rampe finale d'A01 : le hasard imposé aux pédales se place là où une commande de 50 ms coûte peu (rampe, vol, plateforme), ce qui fait perdre environ 0,4 s. Rapport J6, section « Rampe finale ». Ni récompense, ni observation, ni action forcée. `init_from` applique désormais la cible de la configuration. À conserver seulement si v12 ou v12s bat v11/v10 en évaluation figée |
| D42 | **Proposition** (2026-10-04, demandée par l'utilisateur : « vasy applique ca ») : rafales d'exploration « gaz sans frein » de 60 à 150 pas, probabilité de départ de 0,004 par pas, collecte seulement (run v13) | Motif : aucun vol sans frein en 1 482 tours v12. Ni constante de map, ni récompense, ni observation modifiées. La politique évaluée est figée et sans rafale. À conserver seulement si v13 bat v11 en évaluation figée |

D12 désigne ici une comparaison de chronos locaux. Aucun mandat de soumission à un classement officiel n'a été donné. L'interprétation « tout autorisé » concerne la conduite non humaine ; elle ne valide pas des altérations de physique pour la comparaison.

## Complément J4 — 29 septembre 2026

- **Validé utilisateur, amendement de GOAL.md** : les plafonds chiffrés J4 (mission, jeu, stockage, entraînement et fumée) sont levés. D23 conserve le suivi en transitions et temps simulé, mais son ancien plafond global ne s’applique plus à J4. Chaque exécution reste explicitement bornée. D37 et les limites non budgétaires restent inchangés.
- **J4-01 — Proposition** : Stable-Baselines3 SAC avec PyTorch CPU, Gymnasium et TensorBoard. Dépendances autorisées, compatibilité Python 3.13 démontrée par les exécutions ; justification et versions dans le rapport J4. Les hyperparamètres ne sont pas validés par les fumées.
- **J4-02 — Proposition, D25 non satisfait** : threshold à 3 sorties contre argmax4 à 5 sorties. Ce dernier est une relaxation continue, pas un SAC hybride catégoriel. Budgets de fumée inégaux, aucun choix final démontré. Un vrai bras hybride ou une modification explicite de D25 reste nécessaire.
- **Capacités démontrées** : collecte réelle, checkpoints, arrêt STOP/SIGINT, reprise, évaluations figées courtes, tableau de bord HTTP. Voir [rapport J4](reports/J4-apprentissage.md).
- **J4-02 mis à jour (reprise §9)** : bras hybride `hybrid4_v1` implémenté (direction gaussienne reparamétrée, tête catégorielle à quatre couples gaz/frein, espérance exacte dans la cible et la perte de l'acteur, entropie cible 1 + ½ ln 4 nats). Proposition d'hyperparamètres, non validée. Comparaison contrôlée D25 encore absente ; l'outil `tm.py compare` exige un seul facteur différent et au moins deux seeds par bras pour déclarer `controlled`.
- **J4-03 — Observé en jeu** : pont 0.4.0, `CFG … 0 1` laisse TMNF terminer la course contrôlée et ouvrir son écran de fin (contrôleur scripté non appris, 30 580 ms). Aucun replay autosauvegardé observé ; enregistrement d'un chrono officiel non démontré. Une évaluation en mode officiel s'arrête après chaque arrivée et exige une relance manuelle.
- **Validé utilisateur (29 septembre 2026)** : pas de plafond de principe sur `torch_threads` ni sur le nombre d'instances du jeu. Le nombre réel est choisi par mesure. Mesure CPU d'une mise à jour SAC (`runs/j4/logs/sac-update-bench-resume-t*.json`) : 1 thread 15,5 ms, 4 threads 10,3 ms, **8 threads 9,1 ms**, 16 threads 33,7 ms (threshold) ; hybride 9,2 ms à 8 threads, 42,2 ms à 16. Configurations passées à 8 threads. Plusieurs instances : autorisées dans le principe (lève l'accord distinct de D22), mais non prises en charge par le code actuel (port unique, un seul environnement) ; mission séparée avec mesure du gain.
- **D28 partiellement démontré** : 20 tentatives par politique figée à ×1 en temps réel, 20 abandons pour chacune ; hashes modèle/normalisation inchangés. Arrivée officielle toujours empêchée par le pont et non exercée. Aucun chrono comparable ni progrès en course annoncé.

## Complément vitesse d’apprentissage — 30 septembre 2026

- **Correction de mesure** : le « hybride 9,2 ms à 8 threads » ci-dessus provenait d’un SAC standard à 5 sorties (`scripts/j4_sac_update_bench.py`), pas de `HybridSAC`. Mesure de `HybridSAC` réel, données synthétiques, batch 256 : 22,5 ms à 8 threads, 25,0 ms à 4, 26,2 ms à 2 ; threshold 8,6 / 9,5 / 9,7 ms. L’espérance sur quatre commandes évaluait les critiques sur un batch ×4. Ce coût explique les ~42-48 trans/s des runs hybrides contre ~96-99 pour threshold.
- **GPU du laptop mesuré, non retenu** : Radeon 860M (gfx1152) fonctionne sous ROCm (`torch 2.11.0+rocm7.13.0` de `repo.amd.com/rocm/whl/gfx1152`, environnement temporaire hors projet). Mise à jour batch 256 : threshold 14,2 ms, hybride 26,3 ms, plus lent que le CPU ; `predict` 0,6-1,2 ms contre 0,12 ms. Seul gain : hybride batch 1024, 65,9 ms contre 82,0 ms au CPU. D21 (CPU) reste en vigueur. Pas de dépendance GPU ajoutée au projet.
- **J4-04 — Proposition, demandée par l’utilisateur** : critique hybride `q4` (`sac.hybrid_critic`), deux réseaux `[s, steer] → 4 Q`, une passe pour l’espérance exacte. Mêmes cibles et pertes que `hybrid4_v1` ; paramétrage du critique différent, donc nouvelle expérience. Défaut inchangé (`action_input`).
- **J4-05 — Proposition, demandée par l’utilisateur** : apprenant asynchrone (`learner.mode = "async"`). Collecte avec copie figée de l’acteur, gradients dans un thread, buffer et logger verrouillés, sauvegarde sans gradient en cours, attente bornée de la collecte (`max_wait_ms` < délai d’action du pont). Non reproductible bit à bit.
- **J4-06 — Proposition, demandée par l’utilisateur** : ratio `learner.updates_per_transition` (sync ou async), budget de transitions exact. Aucune valeur validée par un résultat d’apprentissage ; configurations livrées à 1 et 0,5.
- **Preuves hors jeu** : 83 tests OK (`PYTHONPATH=src:tests uv run python -m unittest discover -s tests`), dont 12 nouveaux (`tests/test_learner.py`). Banc sur jeu synthétique à 5 ms par pas (`runs/j4/logs/learner-bench-20260930.json`) : hybride historique 31 trans/s, q4 async r=1 68, q4 async r=0,5 126. Aucun essai dans le vrai jeu ; aucune preuve d’effet sur l’apprentissage. Sauvegarde des fichiers modifiés : `runs/j4/backup-learner-20260930-002617/`.
- **Run de nuit utilisateur (D37), observé** : `runs/j4/20260930-005112-a01_sac_hybrid4_q4_async_r05_night`, q4 + async + ratio 0,5, ×10. 4 000 000 transitions (55,6 h simulées) en 6,18 h murales, ~180 trans/s (×4 environ contre les runs hybrides J4) ; ratio réel 0,49999 ; 1 transition invalide ; 0 reset échoué ; la collecte a attendu l’apprenant 4 888 s au total. **Aucun apprentissage de conduite** : 0 arrivée sur 3 859 épisodes ; médiane de `progress_max` par tranche de 250 000 transitions entre 0,11 et 0,17 du début à la fin, meilleur 0,385. Diagnostic hors jeu sur les checkpoints : l’entropie de la politique reste calée sur la cible `1 + ½ ln 4 = 1,69` nats (mesurée 1,73-1,75), soit ~83 % du maximum possible (ln 2 + ln 4 = 2,08) : politique quasi aléatoire (parts des quatre commandes ~25 % chacune). Le coefficient d’entropie monte de 0,10 à ~9-10 et Q de 30 à ~11 000 : le bonus d’entropie (~16 par pas) écrase la récompense de progression (~0,16 par pas à l’allure de référence). Cause principale retenue : la cible d’entropie de J4-02, pas l’accélération. Correction non appliquée : elle change un hyperparamètre et attend l’accord de l’utilisateur.
- **Second défaut, récompense v1** : avec Φ(terminal) = 0, toute la progression est reprise lors d’un abandon ; pour un agent qui ne finit jamais, il ne reste que le coût du temps, donc « terminer l’épisode plus vite » (rester immobile jusqu’à l’abandon, ≈ −5) vaut mieux que rouler (≈ −28 sur la nuit). `threshold_v1_seed2` l’a appris (médiane de progression 0 sur la fin du run, retour −4,8). Le test J3 comparait arrivée lente et abandon, jamais rouler sans finir et s’arrêter.

## Complément J4-07 — corrections demandées par l’utilisateur, 30 septembre 2026

Accord de l’utilisateur : « oui vasy fait ce que tu m’as dit » ; pour la récompense : « plus il avance par rapport à mon trajet plus il gagne, plus une pénalité constante par seconde ; pondère moi ça bien ».

- **J4-07a — Entropie hybride par tête (correction de J4-02)** : deux températures `[direction, commande]` dans `log_ent_coef`, chacune réglée vers sa cible : direction −1 nat (convention SB3 −dim), commande 0,3 ln 4 ≈ 0,416 nat (~90 % sur une commande). Réglable par `sac.hybrid_target_entropy` ; une cible au-delà de l’entropie uniforme (ln 2, ln 4) est refusée. Journaux `train/ent_coef_steer|cmd` et `train/entropy_steer|cmd`. Tous les runs hybrides futurs utilisent ce schéma ; les checkpoints hybrides antérieurs restent évaluables mais leur entraînement est refusé (température unique).
- **J4-07b — Récompense v2 `trackmania_rl.reward/2` (`progress_mode = "delta"`), proposition calibrée** : progression payée directement, `100 × Δprogress` le long de la référence à chaque transition, abandon compris (aucune reprise) ; coût constant −1 par seconde simulée ; bonus d’arrivée confirmée par le jeu +20 ; actualisation 0,905 par seconde (≈ 0,995 par pas de 50 ms, horizon ~10 s au lieu de ~50 s). v1 reste le défaut et son hash est inchangé.
  - Pondération : un tour complet vaut 100 ; à l’allure de référence (27,11 s) la progression rapporte 3,7/s contre 1/s de coût. 1 s gagnée à l’arrivée vaut 1 point (1 % du parcours), plus l’effet de l’actualisation (9,5 %/s), qui pousse surtout à la vitesse.
  - Rouler bat s’arrêter dès 0,61 %/s de progression (`reward.break_even_pace` : c·d^T/S avec T = 5 s d’abandon), soit un tour en 165 s : toute conduite réelle est préférée à l’immobilité.
  - Reculer coûte ce qu’avancer a payé : allers-retours et boucles ne rapportent rien. La progression est bornée par la ligne : retarder l’arrivée ne rapporte rien. Le bonus de 20 marque la validation du jeu sans dominer (vu à 10 s de l’arrivée : ≈ 7). Il peut être mis à 0.
  - Toujours aucune pénalité de glisse, de contact, de braquage ou d’écart (§3 de REWARDS).
- **J4-07c — Outil `tm.py trend --run`** : tendance par tranches d’un run en cours ou fini (progression, parts des commandes, |direction|) avec un verdict indicatif ; conduite aléatoire = commandes ~0,25, |direction| ~0,5. Indicatif, pas une évaluation D28.
- **J4-07d — Correction de bug, observé en jeu** : premier test v2 (`runs/j4/20260930-095814-a01_sac_hybrid4_v2_test30`) sain jusqu’à ~63 000 transitions (médiane 0,38, meilleur 0,54, entropies sur leurs cibles), puis effondrement : braquage à fond, gaz 100 %, `critic_loss = inf`, entropie de direction estimée 3·10²⁶. Cause : `HybridActor.sample_heads` calculait la log-densité en inversant le tanh de la direction ; à saturation, SB3 borne l’atanh et renvoie −10⁶ à −10¹⁶ (reproduit hors jeu), soit une fausse entropie énorme que la perte de l’acteur récompense : la moyenne s’emballe. Défaut présent depuis J4-02, masqué par l’ancienne cible d’entropie élevée. Correction : log-densité tirée de l’échantillon gaussien (`log_prob_from_params`, comme l’acteur SB3). Garde : une perte non finie arrête le run en phase `diverged` sans écrire de checkpoint (le dernier checkpoint sain reste `latest`).
- **Configuration de contrôle** : `configs/training/a01_sac_hybrid4_v2_test30.json`, identique au run de nuit (q4, async, ratio 0,5, ×10, seed 1) hors récompense v2, entropie par tête, `ent_coef = auto_0.1` et actualisation. 300 000 transitions (~30 min murales), plafond 4 000 000 pour prolonger par `resume --budget`. Non lancée dans le jeu.
- **J4-08 — Demande utilisateur du 30 septembre 2026, outillage** : après l’arrêt à 300 000 transitions du run `20260930-104918-a01_sac_hybrid4_v2_ent05` (406 épisodes, zéro arrivée), permettre une reprise sans plafond de transitions jusqu’à `STOP` ou `Ctrl+C`. `resume --until-stopped` désactive le plafond pour la session choisie ; checkpoints et compteurs continuent, les erreurs et divergences arrêtent toujours le run. L’utilisateur lance et contrôle lui-même l’entraînement (D37). Cette demande ne démontre aucun apprentissage supplémentaire.
- **J4-07e — Plafond au checkpoint 1, observé** : `runs/j4/20260930-101431-a01_sac_hybrid4_v2_test30`, ~100 000 transitions, 143 épisodes, 0 checkpoint 1 validé. `progress_max` bloqué à 0,53993 = checkpoint 1 (1 188 m) + `sector_margin_m` (15 m) : la voiture tape un mur vers 830-900 m, longe le mur 15-25 m à droite de la référence et passe à côté du portique ; abandon 5 s plus tard. Entropies sur leurs cibles (direction −1,0 ≈ bruit ±0,09 ; commande 0,41). Essai demandé par l'utilisateur, une seule variable : `configs/training/a01_sac_hybrid4_v2_ent05.json`, cible d'entropie de direction −1,0 → −0,5. Non lancé. Pistes en attente d'accord : marge de secteur ~5 m, bonus par checkpoint validé par le jeu, pénalité de contact latéral (`SceneVehicleCar.HasAnyLateralContact` présent dans la DLL TMInterface 2.2.1, sémantique non vérifiée en jeu ; contraire au défaut D07).
- **Preuves hors jeu** : 92 tests OK ; contrôle sur jeu synthétique 1-D : v2 apprend (177 arrivées sur 40 000 transitions contre 135 pour la config de nuit), mais ce jeu est trop simple pour reproduire l’échec réel. Rapport J4 §10. Aucun essai dans le vrai jeu ; aucune performance de conduite démontrée.

## Outillage web J4 — 30 septembre 2026

- **J4-09 — Demande utilisateur** : interface web locale, simple et complète pour piloter les commandes existantes sans mémoriser les identifiants. Implémentation standard Python sur `127.0.0.1` : runs, modèles/checkpoints, lancement/arrêt/reprise, évaluation figée à ×1, comparaison, tendance, TensorBoard et configurations clonées avec édition JSON intégrale. Cette interface ne change ni le pilote RL ni les décisions D25/D28 ; l'utilisateur déclenche les commandes (D37). Après arrêt du run actif par l'utilisateur, celui-ci a autorisé des essais courts en jeu depuis l'interface.
- **J4-10 — Correction demandée par l’utilisateur** : sur le run `20260930-104918-a01_sac_hybrid4_v2_ent05`, 108 épisodes proches de l’arrivée ont été invalidés par `finish tick delta 0` et des évaluations à ×1 par `inputs released by game: finish`. Le premier essai réel du correctif a donné 3/5 arrivées ; les deux erreurs restantes ont révélé que le callback peut déplacer la position d’environ 0,55 m tout en conservant le même tick. `env.py` accepte désormais ce déplacement borné par un tick physique, avec séquence, chrono et checkpoints cohérents ; la transition terminale ne paie ni temps ni progrès supplémentaire et conserve le bonus d’arrivée. Les commandes sont relâchées après l’arrivée. 115 tests hors jeu réussis ; second essai en jeu encore requis. Les traces d’évaluation enregistrent vitesse affichée, contacts des roues et commandes appliquées, sans changer les entrées du modèle. Le frein est appliqué pendant 89 % des décisions entre 80 et 90 % du parcours, surtout avec quatre roues en l’air ; sa nécessité physique reste ouverte, aucune pénalité de frein ajoutée. Le verrou CLI ignore désormais le parent `uv`, qui ne contrôle pas le jeu.
- **Protection et preuves** : verrou de contrôle partagé entre CLI et interface ; détection des runs et évaluations antérieurs au verrou par PID et commande ; aucun second contrôleur pendant le run utilisateur actif. Tests hors jeu et HTTP : 109 réussis ; chargement réel du site, lecture du run, tendance et comparaison vérifiés. Essai réel : checkpoint `00953949` évalué à ×1, une arrivée à 29,520 s (`runs/j4/20260930-104918-a01_sac_hybrid4_v2_ent05/evals/20260930-144245-00953949-realtime-x1/eval_summary.json`) ; chrono non officiel. Run distinct lancé à 100 transitions puis repris à 200 et arrêté proprement par STOP à 415 avec checkpoint `00000415`, sans transition invalide (`runs/j4/20260930-145137-a01_sac_hybrid4_v2_ent05-5ab1e4/status.json`). Ces essais ne démontrent ni apprentissage prolongé, ni classement. TensorBoard déjà actif est réutilisé, jamais arrêté par l'interface si lancé ailleurs.

## Plateau du chrono — 30 septembre 2026

Accord de l’utilisateur : « je veux bien que tu mettes l’horizon à 0,95 et aussi que tu corriges les mini-épisodes ».

- **J4-11 — Diagnostic, observé sur `runs/j4/20260930-104918-a01_sac_hybrid4_v2_ent05`** : temps médian d’arrivée par tranche de 250 000 transitions : 32,30 → 30,17 → 29,45 → 29,31 → 29,21 s ; meilleur 28,46 s (politique stochastique d’entraînement). Progrès lent, pas nul. Environ 40 % des épisodes depuis 0,75 M sont des erreurs techniques courtes (10 à 50 transitions, `stale or skipped: tick delta -4960 != 50`), presque toujours juste après une arrivée ; leur retour ≈ −0,6 était tracé dans `episode/return`, d’où l’aspect chaotique de la courbe. Les erreurs `finish tick delta 0` s’arrêtent à 340 937 transitions (correctif J4-10 effectif en entraînement).
- **J4-11a — Actualisation 0,95 par seconde (accord utilisateur)** : horizon ~10 s → ~20 s ; le chrono ne pesait presque rien à 0,905/s au-delà de 10 s. Rouler bat s’arrêter dès 0,77 %/s de progression (`break_even_pace`) ; bonus d’arrivée vu à 10 s ≈ 12. Autres termes inchangés. Configuration `configs/training/a01_sac_hybrid4_v3_h095.json` : affinage (`init_from`) depuis le dernier checkpoint du run ci-dessus, poids, optimiseurs, entropies et replay buffer repris ; seul le discount change. Les récompenses stockées ne dépendent pas du discount ; `init_from` refuse une différence sur un autre terme. Proposition non validée par un résultat.
- **J4-11b — Mini-épisodes, pont 0.4.1 (D36)** : cause déduite (non observée par trace à ×10) : `R` reçu pendant le compte à rebours, juste après le rembobinage `auto_restart`, appelait `GiveUp()`. Le compte à rebours courant atteignait 0, l’état `start` partait, puis le redémarrage tardif de `GiveUp` ramenait l’épisode au compte à rebours (états d’erreur à `race_ms` ≈ −2 580, cohérent avec −2 600 + reste du maintien). Correctif : pendant le compte à rebours, `R` rembobine vers l’état de départ sauvegardé (`reset_in_countdown`, méthode `rewind_start`), immédiat comme après une arrivée ; `GiveUp` reste utilisé en course. Sauvegarde `runs/j4/backup/TrackmaniaRLBridge-0.4.0.as`. Copie installée non remplacée pendant le run utilisateur actif : à copier par l’utilisateur à l’arrêt (voir le guide). À vérifier en jeu : `invalid_transitions` doit quasi disparaître.
- **J4-11c — Outillage** : sauvegarde automatique du modèle à chaque nouveau meilleur temps d’entraînement (`checkpoints/best-*`, `best.json`, `eval --checkpoint best`) ; `episode/return` n’inclut plus les épisodes invalides. Tests hors jeu : 118 réussis. Aucun essai en jeu de ces changements.
- **J4-12 — Effondrement du run v3, observé sur `runs/j4/20260930-204802-a01_sac_hybrid4_v3_h095`** : arrivées par 100 épisodes 82–98 jusqu’à ~700 000 transitions, puis 5, 1, 0. Perte du critique (médiane par 25 000) 0,07 → 0,14 (700 k) → 1,1 (775 k) → 1,6 ; perte de l’acteur −30 → +3. Le `resume` reprend fidèlement cet état effondré (métriques continues). Arrêt final à 1 187 954 : `none_not_in_race` (arrivée non contrôlée pendant un `GiveUp` après `time_limit` à 99,6 % du parcours ; non corrigé). Cause de l’effondrement non établie ; le discount 0,95/s est un suspect, non prouvé. Accord utilisateur du 2026-10-01 : garder l’horizon ~20 s. Configuration `configs/training/a01_sac_hybrid4_v3b_h095.json` : nouveau run `init_from` le checkpoint `00660037` (perte critique ~0,07, 954 arrivées sur 1 095 épisodes), seule la source change. Proposition non validée ; surveiller `train/critic_loss`.
- **J4-12a — Pont 0.4.2 (D36), demande utilisateur du 2026-10-01** : `R` en course rembobine désormais vers l’état de départ sauvegardé (`reset_in_race`, méthode `rewind_start`) au lieu d’appeler `GiveUp`, qui ne sert plus que de repli sans état de départ. Si une arrivée non contrôlée survient entre `R` et le rembobinage en attente, `PreventSimulationFinish` garde la course vivante (événement `finish_prevented`, cause `pending_rewind`), sauf en `official_finish`. Sauvegarde `runs/j4/backup/TrackmaniaRLBridge-0.4.1.as`. Côté Python, rien ne dépend de la méthode de reset. Tests hors jeu : 118 réussis (ils ne compilent pas le plugin). Copie installée par l’utilisateur le 2026-10-01 après l’arrêt de v3b ; copies identiques (SHA-256 `a257edad…a41ef0`). À vérifier en jeu : compilation, `reset_requested` avec `rewind_start` en course, plus aucun `none_not_in_race`.
- **J4-13 — Divergence récurrente du critique ; buffer 1M et learning rate 1e-4 (accord utilisateur du 2026-10-01)** : v3b (`runs/j4/20261001-130312-a01_sac_hybrid4_v3b_h095`, parti de `00660037`) a reproduit la divergence ~55 000 transitions après son départ (perte critique 0,09 → 0,40 ; arrivées 20/20 → 8/15). Le run v2 (discount 0,905/s) avait déjà divergé à 500–700 k (perte jusqu’à 1,1, pic 14,9 ; arrivées 86 → 12 par ~145 épisodes) et à 1,9 M, puis récupéré seul : le discount n’est donc pas la seule cause. Hypothèse non prouvée : le replay buffer de 100 000 transitions (≈ 140 derniers épisodes, ≈ 12 min réelles) ne contient plus que de bons tours, le critique oublie les erreurs et surestime. Deux changements simultanés acceptés pour aller vite (leur effet respectif ne sera pas séparable) : `buffer_size` 100 000 → 1 000 000 et `learning_rate` 3e-4 → 1e-4. `init_from` applique désormais `learning_rate` et `buffer_size` de la config (auparavant ceux du checkpoint) et recopie le buffer source dans l’ordre chronologique (`copy_replay_buffer`). Checkpoints tous les 250 000 transitions pour limiter le disque (jusqu’à ~230 Mo par checkpoint avec un buffer plein). Configuration `configs/training/a01_sac_hybrid4_v3c_h095.json`, `init_from` v3b `00050195`, discount 0,95/s conservé. Tests hors jeu : 119 réussis ; chargement réel du checkpoint vérifié hors jeu (capacité 1 M, 100 000 transitions copiées, lr 1e-4). Proposition non validée en jeu.

## Diagnostic du critique — 1er octobre 2026

- **J4-14 — Mesuré hors jeu sur les checkpoints réels, sans modification de l'entraînement** : v3c reprend v3b `00050195`, dont le critique surestime déjà des échecs rares. Treize abandons terminaux sur 100 000 transitions représentent 51,1 % de la MSE recalculée. Pour un abandon confirmé avec récompense −0,0498872, Q moyen des deux critiques vaut 94,18 à la source, 183,76 au checkpoint record v3c 31 201, puis 245,67 au checkpoint final 100 871. LR 1e-4 et capacité 1M réellement appliqués ; aucun incident de protocole enregistré dans v3c. La description « checkpoint sain » fondée sur une faible loss médiane doit être nuancée. Voir le [diagnostic et ses artefacts](reports/J4-critic-diagnostic-20261001.md).
- **J4-14a — Défaut de reprise confirmé, non corrigé dans cette mission de diagnostic** : `init_from` remet le compteur à zéro et conserve `learning_starts=2000`. Le pilote entraîné est remplacé par 2 000 actions uniformément aléatoires au démarrage du nouveau run. Le code et les commandes enregistrées dans v3c concordent. Corriger ce warmup est recommandé ; son rôle dans l'effondrement complet n'est pas isolé.
- **J4-14b — Proposition, pas une décision validée** : expérimenter une priorisation des erreurs TD du critique avec correction du biais et mesures sur un échantillon uniforme. Un essai borné de 1 000 updates sur replay réel fait baisser Q erroné de 94 à 7 en forçant 8 abandons par batch, mais dégrade la MSE globale de 0,2115 à 0,6365 : cette sonde brute n'est pas une recette à déployer. La règle d'abandon dépend aussi d'un compteur absent des observations ; toute extension du schéma D31 ou modification de la sémantique terminale reste à approuver. Aucune preuve de correction durable en jeu, aucun critère J4 supplémentaire coché.
- **J4-14b, contrôle complémentaire** : avec acteur figé et pondération d'importance complète, 1 000 updates donnent Q = 98,08 sur l'échec témoin contre 98,40 en uniforme (départ 94,18). La priorisation seule ne répare pas ce cas dans l'essai court. La piste structurelle proposée devient la cohérence entre le compteur d'abandon et les observations ; elle n'est ni approuvée ni validée en jeu. Les résultats négatifs figurent dans le rapport et les artefacts.

## Correction du critique — 1er octobre 2026

### J4-15 — Corrections approuvées et implémentées, validation en jeu ouverte (1er octobre 2026)

Accord utilisateur après J4-14 : « fait toute les correction que tu me recommande ». Le warmup d'une politique déjà entraînée est corrigé : `init_from` utilise son acteur dès le départ. Avec un replay compatible suffisamment rempli, les gradients peuvent reprendre immédiatement ; avec un replay neuf, le remplissage utilise cet acteur avant les premières mises à jour.

Extension D31 approuvée : schéma v2 de 27 entrées, comprenant les 25 entrées v1 inchangées, le temps restant avant abandon et l'écart au record qui commande ce délai. Formules dans [OBSERVATIONS](OBSERVATIONS.md). La migration `observation_v2` conserve acteur, critiques, critiques cibles et températures, ajoute des colonnes nulles, et démarre des optimiseurs et un replay neufs. Aucun contexte manquant n'est inventé dans l'ancien replay. Les fichiers sources sont préservés.

Configuration préparée : `a01_sac_hybrid4_v4_obs2.json`, source v3 `00660037`, LR 1e-4, capacité 1M, discount 0,95/s conservés. Premier budget utilisateur de 100 000 transitions, checkpoints tous les 25 000 ; ce budget est un point de contrôle, pas une preuve de convergence. Le checkpoint source reste imparfait : TD terminal maximal mesuré 21,32. Les diagnostics ajoutent des sondes fixes uniformes/terminales, un taux d'arrivée sur 50 épisodes et `audit-critic` hors jeu. La priorisation du replay n'est pas déployée après les contrôles négatifs J4-14b.

Preuves et limites : [rapport de correction](reports/J4-critic-corrections-20261001.md). L'implémentation est vérifiée hors jeu ; ni stabilité durable, ni amélioration des chronos, ni fin de J4 ne sont annoncées.

## Récompense v3 — 1er octobre 2026

### J4-16 — Récompense v3 `trackmania_rl.reward/3`, implémentée, non lancée (1er octobre 2026)

Demande utilisateur : une récompense qui garde l'apprentissage actuel mais pousse à gagner des dixièmes près du record, avec un coût non linéaire du chrono. Accord : « vasy cree ton V3 et ne lance pas de run ».

- **Implémenté (proposition de coefficients, non validée par un apprentissage)** : v3 = v2 inchangée + terme `lap` = `Φ_lap(eta') − Φ_lap(eta)`, avec `Φ_lap = −K·ln(1 + g/m)` pour `g = eta − T_cible ≥ 0`, et `−K·g/m` en dessous. `eta` est le chrono projeté si la suite du tour se fait au rythme cible : temps de course plus le temps restant de la référence humaine à la progression courante, multiplié par `T_cible / 27,11`. À l'arrivée, `eta` vaut exactement le chrono. Un abandon est compté comme une arrivée à la limite de temps : `eta' = max(eta', 54,22 s)`. Paramètres : `lap_scale` K = 12,5, `lap_margin_s` m = 0,25 s, `target_time_s` = 23,77 s.
- **Cible** : 23,77 s, meilleur replay TMX de la piste 2233 (UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, identique au profil), Axell, 2025-09-16, relevé le 2026-10-01 via l'API TMX. C'est seulement un ancrage de récompense, fixe pour l'expérience. Il ne remplace pas le relevé comparable D30.
- **Effet calculé** : 0,1 s vaut 5,0 points au record ou en dessous, 1,04 à 1 s du record et 0,20 à 6 s du record. v2 seul donne environ 0,15 à 0,18 point. Le terme lap d'un abandon vaut toujours `Φ(54,22) − Φ(23,77)` ≈ −60, quelle que soit la progression. Aucune pénalité de glisse, de contact, de braquage ou d'écart n'est ajoutée (D07).
- **Hashes** : ceux de v1 et v2 sont inchangés, et des tests le vérifient. Les composantes des anciens runs se rechargent (`lap` vaut 0 par défaut).
- **Reprise** : nouvelle migration `init_from.migration = "fresh_replay"`. Elle conserve acteur, critiques, optimiseurs et températures, mais démarre un replay vide, car les récompenses stockées suivent v2. La collecte utilise l'acteur chargé ; les gradients attendent `learning_starts`.
- **Configuration** : `configs/training/a01_sac_hybrid4_v5_lap.json`, source `runs/j4/a01-v4-obs2b` checkpoint `03092363`. Non lancée.
- **Preuves hors jeu** : 140 tests réussis, dont les 10 de `tests/test_reward_v3.py` et le cas `fresh_replay` ajouté à `InitFrom`. Les scénarios sont synthétiques ; seule la projection du fantôme A01 est vérifiée sur la vraie référence.
- **Risques ouverts** : le critique hérité de v2 doit réapprendre l'échelle des valeurs, et le terminal d'abandon devient fortement négatif (cf. J4-14). L'entropie automatique peut absorber une partie du changement d'échelle. Une baisse de la cible d'entropie en fin d'entraînement reste une décision séparée. Comparaison contrôlée contre v2 non faite.

## J5 — 2 octobre 2026

### J5-01 — Protocole et politique retenue (2 octobre 2026)

L'utilisateur demande l'exécution de J5 jusqu'à validation et autorise le contrôle du jeu pour la session. Le seuil de fiabilité est D33 : au moins 18 arrivées sur 20 tentatives, à ×1 en temps réel, avec politique déterministe figée et départ normal. Il est fixé avant la campagne dans `runs/j5/protocol.json`. Règle de sélection : médiane la plus basse parmi les candidats conformes, puis confirmation rechargée.

**Retenu : `runs/j4/a01-v4-obs2b/checkpoints/00100000`.** Résultats : 20/20, puis 19/20 en confirmation. La branche v3 `00660037` échoue avec 6/20 ; `best-027110ms-02432296` est conforme mais plus lent en médiane, 28,96 s contre 27,05 s. Preuves : [rapport J5](reports/J5-fiabilite.md). D25 reste ouvert en J4. Aucun chrono officiel ni rang n'est déclaré.

## Conception retenue à préciser (historique)

- Récompense : progression par potentiel (D17), coût temporel, arrivée valide, gestion des échecs ; coefficients ouverts.
- Référence : conduite complète sans respawn, puis préparation et projection par secteur.
- Le schéma exact des vecteurs, roues et rotations doit être validé dans le jeu.
- `Turning Rate` reste ambigu tant que sa définition et sa source ne sont pas vérifiées.

## Propositions non encore décidées

| ID | Proposition | Condition de décision |
| --- | --- | --- |
| P01 | ~~Petit réseau numérique avant toute architecture plus complexe~~ — acceptée, voir D16 | Benchmark de latence toujours à mesurer en J4 |
| P02 | ~~Comparer PPO et SAC comme premiers candidats~~ — remplacée par D15 (SAC retenu) | Justification conservée : espace d'action, débit du jeu et compatibilité logicielle |
| P03 | ~~Un coordinateur Hermes et des goals bornés~~ — acceptée, voir D29 | — |
| P04 | ~~Démarrer les vérifications sur le laptop~~ — acceptée, voir D21 | — |
| P05 | ~~Tests CPU avant accélération GPU~~ — acceptée, voir D21 | Référence exacte du GPU et support réel à vérifier avant usage |
| P06 | ~~Utiliser une récompense par potentiel~~ — acceptée, voir D17 | Étude des hypothèses et tests des retours en J3 |
| P07 | ~~Historique, récurrence ou points du parcours à venir~~ — non au départ, voir D18 | Seulement si un besoin mesuré justifie l'extension |
| P08 | ~~Préentraînement par imitation~~ — rejetée, voir D19 | Réexamen seulement sur nouvelle demande de l'utilisateur |
| P09 | ~~Mesurer le budget d'entraînement en temps simulé et en transitions, le nombre d'épisodes étant seulement rapporté~~ — acceptée, voir D23 | Cadence et durée des actions fixées en J1/J3 ; budget chiffré approuvé avant J4 |
| P10 | ~~Fixer un débit de collecte cible : vitesse de simulation × nombre d'instances du jeu~~ — acceptée, voir D22 | Mesure en J1 de la vitesse accélérée, de la fidélité physique et de la charge machine ; accord avant plusieurs instances ou toute autre machine |
| P11 | ~~Prévoir des outils d'exploration marqués comme tels : départs depuis des états intermédiaires issus de courses de référence, variantes de map modifiées pour l'entraînement~~ — rejetée, voir D24 | Seulement si un plateau est mesuré ; accord par outil ; évaluation toujours sur la map d'origine depuis le départ normal (EXPERIMENTS §4) |
| P12 | ~~Accélération et frein binaires sous SAC : sortie continue seuillée à 0 pour chacun, direction continue convertie en `−65536..65536`~~ — comparaison retenue, voir D25 | Tests en J4 contre une action hybride continue + discrète |

Référence externe motivant P09–P11, non vérifiée par nos soins : vidéo Yosh « I Trained an AI to Beat This Absurd World Record » (TMNF, A06, publiée le 2026-03-11, https://www.youtube.com/watch?v=1AGVABna3xQ). Selon son récit : environ 40 h de conduite pour le top 300, plus de 2 000 h au total ; murs ajoutés pour forcer la coupe des rampes ; départs depuis des positions de runs de référence ; imitation tentée sans succès ; record obtenu avec une politique figée rejouée de nombreuses fois. Ces chiffres dépendent de son matériel et de son infrastructure ; ils ne constituent pas un budget pour ce projet. Une capture de la vidéo fournie par l'utilisateur affiche « 1743h (In-game time, simulated in ~43h) », soit un rapport d'environ 40× entre temps de jeu et temps mural ; le matériel et le nombre d'instances correspondants ne sont pas connus.

## État observé du dépôt

- Projet uv, Python `>=3.13`, aucune dépendance déclarée.
- `main.py` contient uniquement un message d'accueil.
- `telemetrie.py` reçoit `WAIT` ou cinq éléments dont le préfixe `DATA`.
- `TelemetrieVoiture.as` utilise une socket locale et produit les mesures depuis `Render()`.
- Le plugin transmet un état global de glisse ; les états individuels des roues ne figurent pas dans ce protocole.
- Aucun contrôle de conduite, contrat d'épisode ou entraîneur RL n'est démontré par ces fichiers.

Ces constats proviennent de la lecture des fichiers. Le jeu n'a pas été lancé pour cette phase documentaire.

## Questions bloquantes pour le premier jalon

- [x] Quelle version de TMInterface est réellement chargée et quels plugins sont actifs ? TMInterface 2.2.1 avec CoreMod 1.0.11, via TMLoader et TmForever 2.12.0. Plugins actifs : `TelemetrieVoiture` et `TrackmaniaRLBridge`.
- [x] Quelle installation Linux lance le jeu, avec quelles contraintes de contrôle ? TMLoader dans Steam, avec Proton Hotfix. Un seul contrôleur à la fois : une nouvelle connexion remplace l'ancienne.
- [x] L'utilisateur autorise-t-il une courte session de contrôle automatique du jeu ? Oui, pour J1 le 2026-09-29.
- [x] Quelle machine est retenue pour cette session ? Le laptop local.
- [x] Quel plafond de durée et quelles modifications locales sont autorisés ? Voir le contrat actif de GOAL.

## Constats J1 (preuves : [rapport J1](reports/J1-integration.md))

| ID | Statut | Constat ou proposition |
| --- | --- | --- |
| J1-01 | Observé en jeu | Pas physique de 10 ms ; `TickTime` et `RaceTime` exprimés en ms. |
| J1-02 | Observé en jeu | Direction analogique sur [−65536, 65536]. Accélération et frein binaires ; combinaison acceptée par le jeu. |
| J1-03 | Observé en jeu | `TurningRate` est un état de direction lissé dans [−1, 1], distinct de l'input `InputSteer`. |
| J1-04 | Observé en jeu | Ordre des roues de l'API : FL, FR, BR, BL. Contact et glisse sont disponibles pour chaque roue. |
| J1-05 | Observé en jeu | A01 : trois checkpoints comptés par `OnCheckpointCountChanged`, arrivée incluse. L'arrivée est signalée par `RaceFinished`. |
| J1-06 | Accepté (D20) | Mode synchrone pour l'entraînement : simulation gelée jusqu'à l'action, durée exacte. Le mode temps réel a produit 5 pas de 60 ms sur 60. |
| J1-07 | Accepté (D20) | Reset par `GiveUp()`, contrôlé par l'environnement ; premier état à `race_ms = 0`. |
| J1-08 | Ouvert | Chargement automatique de la map : la commande `map` n'a pas chargé A01. Repère de la vitesse angulaire et sens de l'axe x : validés en J2 (voir J2-01, J2-02). |

## Constats J2 (preuves : [rapport J2](reports/J2-observations.md))

| ID | Statut | Constat ou proposition |
| --- | --- | --- |
| J2-01 | Observé en jeu | Colonnes de `rotation_matrix` = axes voiture en monde ; voiture **+x gauche**, +y haut, +z avant (accélération centripète signée sur 1 361 échantillons, offsets des roues). `steer < 0` = gauche. |
| J2-02 | Observé en jeu | `AngularSpeed` est en rad/s, **repère monde** (différence finie des rotations : erreur médiane 0,006 rad/s contre 0,226 en repère voiture). ω_y > 0 = rotation vers la gauche. |
| J2-03 | Observé en jeu | Lacet ±π : wraps observés ; quaternion sans changement de signe ; matrice orthonormée directe. |
| J2-04 | Observé en jeu | `Gear = 0` à l'arrêt et en marche arrière (`rear_gear = 1`) ; 1 à 5 en marche avant. |
| J2-05 | Observé en jeu | En pont passif, l'arrivée est confirmée par `RaceFinished` + callback checkpoint 3/3 ; l'événement `finish` du pont n'existe qu'après une commande `R`. `race_ms` se fige à l'arrivée. |
| J2-06 | Réalisé | Référence A01 : course humaine valide de 27,11 s, 2 713 échantillons bruts, ligne préparée à 1 m sans lissage (2 228,15 m, écart max 0,167 m). Identité et hash dans `configs/maps/a01.json`. |
| J2-07 | Réalisé | Géométrie : repère (T, N = up de référence orthogonalisé, L = N × T à gauche). Recherche dans la fenêtre de continuité ∩ secteur autorisé par le compteur du jeu ; jamais le plus proche global. Progress peut reculer ; aucun checkpoint n'est validé par Progress. |
| J2-08 | Accepté (D31) | Schéma d'observation v1 (25 valeurs) : vitesses linéaire et angulaire en repère voiture, orientation = vecteurs avant et haut en monde, z-score clip ±5 pour les grandeurs non bornées. Approuvé par l'utilisateur le 2026-09-29. |
| J2-09 | Proposition (D32 retirée) | Seuils du tracker : 280 m/s, fenêtre +8 m, départ 30 m, marge de secteur 15 m, relocalisation 40 m. Jamais déclenchés en réel en J2 ; à mesurer en J3. |
| J2-10 | Tranché pour `rear_gear` (D35) ; ouvert pour Git | `rear_gear` non ajouté au modèle. Versionnage Git de `data/maps/` : à confirmer. |

## Constats J3 (preuves : [rapport J3](reports/J3-environnement.md))

| ID | Statut | Constat ou proposition |
| --- | --- | --- |
| J3-01 | Réalisé | Contrat `trackmania_rl.env/1` : reset sans transition ; transition = même épisode et même `action_id`, Δtick = 50 ms exactement (ou arrivée en cours de maintien), `seq` croissant, UID, checkpoints monotones. Statuts `finished`, `abandoned`, `time_limit`, `running`, `error`. |
| J3-02 | Proposition | Récompense v1 : Φ = 100 × Progress, Φ(terminal) = 0 ; coût −1 par seconde simulée ; bonus d'arrivée +150 ; actualisation 0,98 par seconde (γ = 0,98^dt). Calibration A01 : bonus minimal 84,3. Sensibilité hors jeu sur les épisodes réels : ordre des retours conservé pour les 7 variantes testées ; 0,98 par seconde retenu (0,95 échoue la calibration). Abandon terminal, limite de temps en troncature avec bootstrap. À approuver avant J4. |
| J3-03 | Résolu en jeu (pont 0.2.1, modification autorisée par l'utilisateur le 2026-09-29) | Constat 0.1.0 : après une arrivée, `GiveUp()` est ignoré et le jeu ouvre l'écran de fin (`game_state = 1024`) ~3 s plus tard ; plus aucun `OnRunStep`, reset impossible. Un simple `RewindToState` au compte à rebours ne suffit pas : l'écran de fin s'ouvre quand même (essai 0.2.0, `runs/j3/20260929-161157-env`). Correctif 0.2.1 : arrivée contrôlée traitée dans `OnCheckpointCountChanged` (état `finish`, relâchement), puis `PreventSimulationFinish()` ; `R` après arrivée rembobine vers l'état sauvegardé au premier tick du compte à rebours ; `CFG … 1` (auto_restart) rembobine aussitôt. Preuve : 3 arrivées enchaînées sans intervention, 1 830 transitions valides (`runs/j3/20260929-162527-env`). Le chrono officiel de la course n'est plus enregistré par le jeu pour une course contrôlée (sans objet à l'entraînement ; l'évaluation D28 devra utiliser une course non empêchée). |
| J3-04 | Observé en jeu | Retard client > délai d'action : `released/action_timeout` avec simulation gelée, transition `error` sans récompense ; reprise par reset. Déconnexion au milieu d'un maintien : commandes à 0 et `armed = false` après reconnexion. |
| J3-05 | Mesuré | Tracker (J2-09) sur 1 436 transitions réelles valides : 0 relocalisation, distance maximale 22,8 m, Δs maximal 5,4 m par 50 ms. Seuils non déclenchés ; ils restent une proposition. |

## Questions bloquantes avant entraînement

- [x] Toutes les observations demandées sont-elles disponibles avec des conventions établies ? Oui, conventions mesurées en J2 et schéma v1 approuvé (D31).
- [x] Comment appliquer et maintenir la direction progressive ? `SetInputState(Steer)` réappliqué à chaque tick pendant le maintien (J1-02, rapport J1 §5).
- [x] Accélération et frein sont-ils binaires ou progressifs ? Binaires (J1-02).
- [x] Quelle cadence et quelle stratégie de synchronisation sont validées ? Stratégie synchrone (D20) et cadence de 50 ms (D26).
- [x] Comment reconnaître arrivée, checkpoints et reset ? J1-05, J1-07, J2-05.
- [x] Quels seuils définissent timeout, absence de progression et échec ? D27.
- [ ] Quel algorithme, framework et encodage sont retenus ? Algorithme SAC (D15) et réseau MLP 2×256 (D16) décidés ; encodage v1 approuvé (D31) ; framework ouvert, à choisir en J4.
- [ ] Quelle RAM, quel GPU exact, quelle VRAM et quel environnement logiciel sont disponibles ?
- [ ] Quel budget de calcul, de stockage et d'utilisation des modèles Hermes ?
- [x] Quel protocole d'évaluation et combien d'essais ? D28.

## Questions pour les objectifs de classement

- [x] Quelle map A01 exacte : édition, fichier, identifiant et version ? A01-Race de la campagne Nations (White), UID `BeySZdnfuSh4nHY5xztiXLmlrXe`, TmForever 2.12.0 ; hash dans `configs/maps/a01.json` (rapport J1 §1).
- [x] Quelle source fait autorité pour les temps mondiaux retenus ? Dedimania et TMX (D30).
- [x] Quelle catégorie, quelles règles et quelles conditions physiques sont comparables ? D34.
- [ ] Quels seuils top 1 000 et top 50, relevés à quelle date ?
- [x] Quelle fiabilité minimale accompagnera l'objectif de meilleur temps ? D33.

Ne pas inventer un seuil en attendant une source. Un objectif de classement reste « non évalué » tant que ces champs ne sont pas résolus.

## Fiche pour une nouvelle décision

```text
ID :
Statut : proposition / accepté / rejeté / remplacé
Question :
Options considérées :
Choix :
Justification :
Preuves ou expérience :
Risques :
Conditions de réexamen :
Validation utilisateur, si nécessaire :
Documents et versions concernés :
```
