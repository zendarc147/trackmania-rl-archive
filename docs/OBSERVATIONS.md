# Contrats des observations et des actions

## 1. Source et statut

La base approuvée est la capture « OBSERVATION » fournie par l'utilisateur dans la conversation de conception. Les libellés sont transcrits ci-dessous. La capture ne précise pas les unités, les repères, les échelles des barres ou le sens exact de `Turning Rate`.

Le fichier image d'origine est dans l'espace de conversation, pas dans le dépôt. Ce document conserve sa transcription ; ne pas dépendre de ce chemin local pour faire fonctionner le projet.

**La liste souhaitée n'est pas une liste de champs TMInterface déjà vérifiés.** Le démonstrateur actuel ne fournit qu'une vitesse d'affichage, un rapport, un régime et un indicateur global de glisse.

## 2. Observations approuvées

| Libellé de la capture | Information demandée | Points à vérifier avant implémentation |
| --- | --- | --- |
| `Velocity X/Y/Z` | Vecteur vitesse | Unités, repère monde ou voiture, conventions d'axes |
| `Rotation X/Y/Z` | Orientation de la voiture | Convention, ordre des rotations, unités et discontinuités |
| `Angular Velocity X/Y/Z` | Vitesse angulaire | Repère, unités et signes |
| `Gear` | Rapport engagé | Valeurs possibles, rapport neutre ou marche arrière |
| `Turning Rate` | Grandeur nommée ainsi dans la capture | Définition physique, source, plage et différence avec l'input de direction |
| `Centerline Lateral Distance` | Écart latéral signé à la référence | Signe et repère local de la piste |
| `Centerline Vertical Distance` | Écart vertical signé à la référence | Verticale monde ou normale locale ; convention explicite |
| `Progress` | Avancement le long du parcours | Unité, origine, checkpoints, reculs et éventuels tours |
| `Wheels Contact 1/2/3/4` | Contact de chaque roue | Ordre des roues et signification exacte du contact |
| `Wheels Sliding 1/2/3/4` | Glisse de chaque roue | Ordre, type de valeur et disponibilité individuelle |

Ne pas assimiler la vitesse scalaire actuelle à un vecteur vitesse. Ne pas recopier l'indicateur global de glisse dans les quatre roues. Un champ absent doit être marqué indisponible, jamais remplacé silencieusement par zéro.

Le régime moteur actuellement affiché n'est pas une entrée approuvée par cette capture. Il peut rester une donnée de diagnostic. L'ajouter au modèle demande une décision distincte.

## 3. État interne de l'environnement, distinct des entrées du modèle

L'environnement pourra avoir besoin de données supplémentaires pour construire les observations et vérifier la course : position monde, temps de simulation, identité de map, checkpoints validés, arrivée, état de course, identifiant d'épisode, action appliquée et santé de connexion.

Ces données ne deviennent pas automatiquement des entrées du réseau. Par exemple, la position monde sert à calculer les écarts, tandis que le modèle peut ne recevoir que ces écarts et l'avancement.

Exception approuvée le 1er octobre 2026 (J4-15) : le schéma v2 expose deux valeurs de l'état d'abandon, décrites ci-dessous. Les autres données internes restent exclues.

Aucun pixel, temps futur, action future d'un replay ou meilleure trajectoire future ne doit être injecté implicitement dans les observations.

## 4. Construction de la référence

### Première méthode retenue

Enregistrer une conduite humaine complète, à une vitesse confortable, sans respawn ni demi-tour volontaire. Le chrono n'a pas besoin d'être performant. Une méthode par éditeur reste une option à étudier, pas une fonction déjà disponible.

### Informations à conserver

- Identité exacte de la map et empreinte du fichier si accessible.
- Positions ordonnées, horodatages et checkpoints franchis.
- Éventuelles données d'orientation nécessaires au repère local.
- Version du schéma d'enregistrement et conventions d'axes.
- Source de la référence et paramètres de préparation.

### Préparation proposée

1. Contrôler que le parcours est complet et valide.
2. Éliminer les doublons et points dégénérés sans effacer les virages utiles.
3. Rééchantillonner selon la distance et tester tout lissage pour ne pas couper à travers des obstacles.
4. Construire une longueur cumulée et des secteurs associés aux checkpoints.
5. Visualiser les écarts entre référence brute et référence préparée.
6. Conserver les deux versions ainsi que les paramètres de transformation.

### Projection pendant la course

Chercher le segment compatible avec le secteur actif et la progression précédente, pas seulement le point globalement le plus proche. Définir le comportement aux croisements, aux sauts, aux retours en arrière et aux boucles.

L'écart latéral sera signé pour distinguer gauche et droite. L'écart vertical sera signé pour distinguer au-dessus et en dessous. Le repère exact doit être choisi et testé, notamment sur les pistes inclinées : ne pas supposer que l'axe vertical du monde suffit partout.

L'avancement suivra la géométrie, pas le temps de la conduite de référence. Il peut reculer ; ne pas transformer l'observation en maximum historique qui masquerait un retour en arrière. Une statistique de progression maximale peut exister séparément pour le diagnostic.

Ne pas lier si étroitement la projection à la référence qu'un raccourci légal devient impossible. Tout détour ou raccourci doit rester compatible avec les checkpoints et la validité du jeu.

## 5. Encodage du modèle

Le schéma devra préciser pour chaque entrée : nom interne, source vérifiée, type, unité, repère, ordre, plage observée, transformation, bornes, règle en cas d'absence et fréquence réelle.

Propositions à évaluer, non encore figées :

- Exprimer les vecteurs dans un repère utile à la voiture ou au parcours.
- Utiliser un encodage d'orientation qui traite explicitement les discontinuités.
- Normaliser les valeurs numériques avec des statistiques enregistrées.
- Conserver le même schéma en entraînement et en évaluation.

Une transformation peut changer le nombre d'entrées du réseau sans ajouter une nouvelle information physique. Documenter ce changement au lieu de déduire une dimension finale des barres de la capture.

L'évaluation doit utiliser les statistiques du modèle sauvegardé, sans les réapprendre sur les courses évaluées. L'historique d'observations, la récurrence et les points de parcours à venir sont des extensions à approuver, pas la base actuelle.

## 6. Actions

Décision validée : direction progressive, accélération et frein uniquement.

- Définir une direction normalisée puis une conversion documentée vers la plage réellement acceptée par TMInterface.
- Vérifier si accélération et frein sont binaires ou progressifs ; ne pas supposer qu'une interface « type manette » rend toutes les commandes analogiques.
- Vérifier le comportement des commandes simultanées sans l'interdire par préférence humaine.
- Définir la durée de maintien, le délai d'application et la cadence.
- Ne pas ajouter un filtre de lissage pour rendre les mouvements humains.
- Relâcher les commandes à l'arrêt du contrôleur, à la déconnexion et pendant un reset.

Le modèle ne dispose pas d'une action de respawn. L'environnement réinitialise l'épisode selon les règles convenues.

## 7. Tests d'acceptation

### Extension v2 : contexte de l'abandon (J4-15)

L'utilisateur a demandé d'appliquer les corrections recommandées après le diagnostic du critique. Cela approuve l'ajout explicite des deux entrées proposées ; leur efficacité en jeu reste à mesurer. La configuration choisit `observation_schema: "trackmania_rl.observation/2"`. Sans cette option, le schéma v1 reste inchangé.

| Index (base zéro) | Entrée v2 | Calcul et sens |
| --- | --- | --- |
| 0–24 | Les 25 entrées v1 | Ordre et normalisation gelée inchangés |
| 25 | `no_progress_remaining_fraction` | `max(0, 1 - (race_ms - best_race_ms) / no_progress_ms)` ; 1 au départ ou après un nouveau record, 0 à l'abandon |
| 26 | `progress_record_gap_fraction` | `(best_s_m - progress_s_m) / longueur_reference` ; distance au record qui arme le compteur, divisée par la longueur du parcours |

Ces deux entrées sont sans unité et sans statistiques apprises. Le second champ reste signé : une avance inférieure au seuil de nouveau record peut donner une petite valeur négative. L'environnement actualise le record avant d'encoder l'observation suivante. Le reset remet le contexte à `[1, 0]`. Aucun temps futur, historique de démonstration ou changement de récompense n'est ajouté.

Le hash de normalisation continue d'identifier les 25 entrées de base. Le contrat complet exige **ce hash et la version du schéma**, enregistrés avec le run et contrôlés à la construction et à l'évaluation. Une migration explicite ajoute des colonnes initialisées à zéro aux réseaux ; l'ancien replay ne contient pas ces champs et ne peut pas être réutilisé tel quel. Tests hors jeu : `tests/test_critic_corrections.py`. La validation en jeu du schéma v2 reste ouverte.

### Extension v3 : points de parcours à venir (J6, D38)

`observation_schema: "trackmania_rl.observation/3"` : les 27 entrées v2, suivies de 18 valeurs. Pour chaque distance d de (10, 25, 50, 100, 150, 200) m, on prend le point de la référence préparée à l'abscisse `min(s + d, longueur)`. On retranche la position de la voiture, on exprime le vecteur dans le repère voiture (x gauche, y haut, z avant), puis on le divise par d. Ces valeurs n'ont pas de statistiques apprises. Elles décrivent la géométrie du parcours, sans temps, ni commande, ni trajectoire de démonstration. Tests hors jeu : `tests/test_observation_v3.py`. Validation en jeu : à mesurer dans le run J6 v8.

### Preuves historiques v1

État après J2 ([rapport](reports/J2-observations.md)) : cases cochées seulement avec preuve réelle ou test hors jeu cité. Schéma v1 approuvé (D31) ; `rear_gear` non ajouté (D35). En J3, l’environnement fournit le tick attendu à chaque transition (rapport J3 §3).

- [x] Chaque observation dispose d'une source et d'une convention vérifiées. (J2 §5 et §7)
- [x] L'ordre des roues est testé, pas deviné. (J1 : identité des objets ; J2 : offsets FL/FR)
- [x] `Turning Rate` est défini et comparé à l'input de direction. (J1)
- [x] Vecteurs, angles, signes et unités passent des tests sur cas connus. (J2 §5 : virages signés, différences finies de rotation)
- [x] La projection traite une ligne droite, un virage, un croisement, un saut et un retour en arrière. (tests synthétiques ; saut et recul aussi en réel ; A01 n'a pas de croisement)
- [x] Un reset n'augmente pas artificiellement la progression.
- [x] La progression ne valide pas à elle seule un checkpoint ou une arrivée.
- [x] Le même état produit le même encodage avec un schéma et une normalisation figés.
- [x] Les valeurs non finies, absentes ou trop anciennes sont détectées. (hors jeu ; la péremption dépend du tick attendu fourni par l'environnement J3)
- [x] Le modèle final ne reçoit aucune image et n'utilise aucune séquence de commandes précalculée. (schéma v1 : 25 valeurs numériques issues de l'état courant)
