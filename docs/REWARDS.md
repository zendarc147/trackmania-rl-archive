# Récompense : conception et validation

## 1. Objectif produit

Terminer une course valide le plus vite possible, sans contrainte de conduite humaine. Le score de récompense n'est pas un rang mondial et ne remplace jamais le chronométrage réel.

La conception retient une aide à la progression, un coût du temps, une arrivée valide et un traitement des échecs. Les coefficients, la durée maximale et la formule exacte ne sont pas encore approuvés. Aucun pourcentage de « répartition » ne doit être choisi sans préciser les unités et tester le retour cumulé.

## 2. Composantes proposées

### Progression

Fournir un signal lié à l'avancement dans le parcours, compatible avec l'ordre des checkpoints. Ne pas récompenser la distance totale parcourue, la vitesse scalaire ou la simple proximité géométrique de l'arrivée.

Ne pas cumuler uniquement les différences positives en ignorant les reculs. Ne pas distribuer à nouveau un bonus de checkpoint déjà obtenu. Ne pas faire passer un reset pour un déplacement favorable.

Une formulation par potentiel sur `Progress` est retenue (D17). Avant de verrouiller une version, vérifier ses hypothèses, le facteur d'actualisation, les potentiels terminaux et le traitement des troncatures. La désigner ainsi ne suffit pas à prouver qu'elle préserve l'objectif final. Les tests du retour effectivement utilisé par l'algorithme sont obligatoires.

### Temps

Appliquer un coût proportionnel au temps de simulation écoulé. Ne pas utiliser le temps mural de calcul ni un coût fixe par paquet reçu sans tenir compte de la durée de transition.

Exception de protocole J4-10 : une arrivée confirmée peut être signalée au même tick que la frontière précédente, avec une petite mise à jour de position dans le callback. Sa transition terminale dure alors 0 ms, coûte 0 point de temps et ne paie aucun progrès supplémentaire ; elle garde le bonus d’arrivée. Les transitions non terminales à durée nulle restent invalides.

La cadence de décisions, la répétition d'action, l'actualisation et l'horizon doivent être définis ensemble. Un changement de cadence ne doit pas transformer silencieusement la tâche d'optimisation.

### Arrivée valide

Prévoir un bonus terminal lorsque le jeu confirme la réussite, avec tous les checkpoints nécessaires. Aucun franchissement géométrique supposé de la ligne n'est suffisant.

Calibrer la réussite par rapport au coût temporel maximal et aux échecs. Tester explicitement qu'une arrivée lente dans l'horizon autorisé est préférable à un abandon volontaire qui accumule des bonus intermédiaires.

### Échec et interruption

Distinguer :

- un échec de conduite selon les règles de l'épisode ;
- une limite de temps ou une troncature administrative ;
- une erreur technique de télémétrie ou de transport.

Ne pas transformer systématiquement une troncature en véritable état terminal dans l'algorithme. Définir le traitement de la valeur future selon la signification réelle de l'arrêt. Une erreur technique invalide les données concernées ; ce n'est pas nécessairement une faute du pilote.

Un abandon précoce ne doit pas devenir rentable parce qu'il évite le coût du temps restant. Choisir le traitement terminal après des tests comparatifs, pas avec une pénalité arbitraire isolée.

## 3. Absences volontaires de pénalités

Par défaut, ne pas pénaliser :

- la direction brusque ou les oscillations de commande ;
- la glisse ou le drift ;
- les contacts avec les murs ;
- l'écart à la ligne de référence ;
- une conduite différente de la démonstration humaine.

Ne pas ajouter de bonus direct de vitesse brute ou d'imitation des commandes humaines. Un mécanisme utile à l'apprentissage reste une proposition à comparer, pas une préférence cachée pour une conduite « propre ».

Les états de glisse et de contact sont des observations. Leur présence n'impose aucune récompense correspondante.

## 4. Calibration avant les longs entraînements

1. Fixer l'unité de progression, l'horizon et la durée des actions.
2. Enregistrer séparément chaque composante sur des courses de référence.
3. Comparer les retours des mêmes scénarios avec les coefficients candidats.
4. Vérifier le classement des comportements désirables et indésirables.
5. Tester les effets du discount et des fins d'épisode.
6. Verrouiller une version de récompense pour une expérience.
7. Faire une ablation si un changement améliore le score sans améliorer le chrono.

Une récompense modifiée produit une nouvelle expérience. Ne pas comparer des scores bruts de versions différentes comme s'ils avaient la même signification.

## 5. Cas de tests obligatoires

État après J3 ([rapport](reports/J3-environnement.md) §5) : récompense v1 `trackmania_rl.reward/1`, coefficients proposés non approuvés. Cases cochées avec test hors jeu synthétique ; confirmations réelles indiquées.

- [x] Deux courses valides comparables : la plus rapide doit rester préférée selon l'objectif choisi. (réel : 30,12 s → 59,08 contre 30,47 s → 58,31)
- [x] Aller-retour au même endroit : aucun gain exploitable en boucle.
- [x] Boucle ou oscillation autour d'un checkpoint : aucun bonus répété.
- [x] Projection sur une portion future à un croisement : aucun avancement fictif. (synthétique seulement ; A01 sans croisement)
- [x] Checkpoint obligatoire manqué : aucune arrivée valide.
- [x] Reset : aucune transition récompensée entre les deux épisodes. (réel)
- [x] Abandon anticipé : ne rapporte pas davantage qu'une réussite lente admissible. (calcul de calibration + tests)
- [x] Immobilité prolongée : pas de gain à attendre indéfiniment. (réel : abandon à 5,15 s, retour −4,89)
- [x] Course plus rapide malgré un contact : pas de pénalité cachée de collision.
- [x] Changement de cadence : cohérence du coût temporel et analyse du discount.
- [x] Déconnexion : transition rejetée et inputs relâchés. (réel : relâchement constaté)
- [x] Limite temporelle : statut et traitement de la valeur future explicites. (réel, limite de test de 3 s)

Les scénarios synthétiques testent les règles. Les captures réelles et courses évaluées valident ensuite leur adéquation au jeu. Aucun test synthétique ne prouve une performance en course.

## 6. Mesures à conserver

Pour chaque épisode : chrono du jeu, réussite, checkpoints, progression, raison de fin, durée simulée, nombre de décisions, composantes de récompense et retour utilisé par l'algorithme.

Pour une évaluation : meilleur temps valide, distribution des temps valides et taux de réussite. Conserver les échecs dans le dénominateur. Ne pas sélectionner un modèle uniquement sur sa récompense ou sur un unique essai exceptionnel.

## 7. Questions restant à décider

Récompense v2 `trackmania_rl.reward/2` (30 septembre 2026, demandée par l'utilisateur, pondération proposée non validée par un résultat d'apprentissage ; DECISIONS J4-07b) : progression payée directement, 100 × Δprogress à chaque transition, abandon compris ; −1 par seconde simulée ; +20 à l'arrivée confirmée par le jeu ; actualisation 0,905 par seconde. Motif : avec v1 (Φ(terminal) = 0), un agent qui ne finit pas n'optimise que la durée de l'épisode et apprend à s'arrêter (run de nuit et `threshold_v1_seed2`). Cas du §5 rejoués pour v2 dans `tests/test_env.py` (`RewardV2Delta`), plus « rouler lentement bat s'arrêter jusqu'à l'abandon » : seuil 0,61 %/s de progression (`reward.break_even_pace`).

Récompense v3 `trackmania_rl.reward/3` (1er octobre 2026, demandée par l'utilisateur, coefficients non validés par un apprentissage ; DECISIONS J4-16) : v2 + terme de chrono non linéaire `Φ_lap(eta') − Φ_lap(eta)`, où `Φ_lap = −K·ln(1 + (eta − T_cible)/m)`. `eta` est le chrono projeté au rythme cible, calculé à partir de la référence ; il est exact à l'arrivée. Un abandon est compté comme une arrivée à la limite de temps. Paramètres : K = 12,5, m = 0,25 s, T_cible = 23,77 s (TMX, relevé du 2026-10-01). Un dixième vaut 5 points près du record contre 0,2 à 6 s. Cas du §5 rejoués dans `tests/test_reward_v3.py` : somme exacte sur un tour fini, abandon jamais meilleur qu'une arrivée dans la limite, aller-retour nul, rouler meilleur que s'arrêter, arrivée plus rapide préférée.

Proposition J3 (`src/trackmania_rl/reward.py`, non approuvée) : Φ = 100 × Progress avec Φ(terminal) = 0, coût −1,0 par seconde simulée, bonus d'arrivée +150, actualisation 0,98 par seconde (γ = 0,98^dt). Abandon terminal, limite de temps en troncature. Voir le rapport J3 §4.

- Durée maximale d'un épisode et règle de non-progression.
- Définition d'une situation irrécupérable sans interdire les récupérations utiles.
- Potentiel, coefficients et convention terminale.
- Stratégie d'actualisation et éventuel ajustement à la cadence.
- Priorité entre meilleur chrono et fiabilité lorsque deux modèles se compensent sur ces critères.
